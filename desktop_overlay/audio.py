"""Native WAV playback for desktop overlays, without third-party packages.

Linux playback uses PulseAudio's simple API, which also covers PipeWire, and
falls back to ALSA. Windows and macOS return None so applications can keep
their existing winsound, MCI, afplay, or compressed-file fallback.

Only 16-bit mono and stereo WAV files are handled. Volume and stereo position
are applied to samples before playback, giving both callers one explicit API.
"""

from __future__ import annotations

import array
import atexit
import ctypes
import ctypes.util
import math
import sys
import threading
import time
import wave
from pathlib import Path

PA_SAMPLE_S16LE = 3
PA_STREAM_PLAYBACK = 1
SND_PCM_STREAM_PLAYBACK = 0
SND_PCM_FORMAT_S16_LE = 2
SND_PCM_ACCESS_RW_INTERLEAVED = 3
SND_LATENCY_US = 200000
EPIPE = 32
MAX_RECOVERIES = 8
CHUNK_FRAMES = 4096
PAN_THRESHOLD = 0.02

_active = set()
_lock = threading.Lock()


class _SampleSpec(ctypes.Structure):
    _fields_ = [
        ("format", ctypes.c_int),
        ("rate", ctypes.c_uint32),
        ("channels", ctypes.c_uint8),
    ]


def _load(name: str, soname: str, prepare):
    """Load and configure one native library once, returning None on failure."""
    if name not in _load.cache:
        library = None
        if sys.platform not in ("win32", "darwin"):
            try:
                library = ctypes.CDLL(ctypes.util.find_library(name) or soname)
                prepare(library)
            except Exception:
                library = None
        _load.cache[name] = library
    return _load.cache[name]


_load.cache = {}


def _prepare_pulse(library):
    library.pa_simple_new.restype = ctypes.c_void_p
    library.pa_simple_new.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.POINTER(_SampleSpec), ctypes.c_void_p,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
    ]
    library.pa_simple_write.restype = ctypes.c_int
    library.pa_simple_write.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_int),
    ]
    library.pa_simple_drain.restype = ctypes.c_int
    library.pa_simple_drain.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
    ]
    library.pa_simple_free.argtypes = [ctypes.c_void_p]


def _prepare_alsa(library):
    library.snd_pcm_open.argtypes = [
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p,
        ctypes.c_int, ctypes.c_int,
    ]
    library.snd_pcm_set_params.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
        ctypes.c_uint, ctypes.c_int, ctypes.c_uint,
    ]
    library.snd_pcm_writei.restype = ctypes.c_long
    library.snd_pcm_writei.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
    ]
    library.snd_pcm_prepare.argtypes = [ctypes.c_void_p]
    library.snd_pcm_drain.argtypes = [ctypes.c_void_p]
    library.snd_pcm_close.argtypes = [ctypes.c_void_p]


class _PulseOutput:
    """PulseAudio, including PipeWire through its PulseAudio compatibility."""

    name = "PulseAudio/PipeWire"

    @staticmethod
    def library():
        return _load("pulse-simple", "libpulse-simple.so.0", _prepare_pulse)

    def __init__(self, rate: int, channels: int):
        self.lib = self.library()
        self.error = ctypes.c_int(0)
        spec = _SampleSpec(PA_SAMPLE_S16LE, rate, channels)
        self.stream = self.lib.pa_simple_new(
            None, b"desktop-overlay", PA_STREAM_PLAYBACK, None, b"overlay",
            ctypes.byref(spec), None, None, ctypes.byref(self.error),
        )
        if not self.stream:
            raise OSError("pa_simple_new failed")

    def write(self, block: bytes) -> bool:
        return self.lib.pa_simple_write(
            self.stream, block, len(block), ctypes.byref(self.error)) >= 0

    def drain(self) -> None:
        self.lib.pa_simple_drain(self.stream, ctypes.byref(self.error))

    def close(self) -> None:
        self.lib.pa_simple_free(self.stream)


class _AlsaOutput:
    """Direct ALSA output when no sound server is running."""

    name = "ALSA"

    @staticmethod
    def library():
        return _load("asound", "libasound.so.2", _prepare_alsa)

    def __init__(self, rate: int, channels: int):
        self.lib = self.library()
        self.channels = channels
        self.pcm = ctypes.c_void_p()
        if self.lib.snd_pcm_open(
                ctypes.byref(self.pcm), b"default",
                SND_PCM_STREAM_PLAYBACK, 0) < 0:
            raise OSError("snd_pcm_open failed")
        if self.lib.snd_pcm_set_params(
                self.pcm, SND_PCM_FORMAT_S16_LE,
                SND_PCM_ACCESS_RW_INTERLEAVED, channels, rate,
                1, SND_LATENCY_US) < 0:
            self.lib.snd_pcm_close(self.pcm)
            raise OSError("snd_pcm_set_params failed")

    def write(self, block: bytes) -> bool:
        """Write every frame and recover from a bounded number of underruns."""
        frame_bytes = 2 * self.channels
        frames = len(block) // frame_bytes
        written = 0
        recoveries = 0
        while written < frames:
            result = self.lib.snd_pcm_writei(
                self.pcm, block[written * frame_bytes:], frames - written)
            if result > 0:
                written += result
                recoveries = 0
                continue
            if result < 0 and result != -EPIPE:
                return False
            if result == -EPIPE:
                self.lib.snd_pcm_prepare(self.pcm)
            recoveries += 1
            if recoveries > MAX_RECOVERIES:
                return False
        return True

    def drain(self) -> None:
        self.lib.snd_pcm_drain(self.pcm)

    def close(self) -> None:
        self.lib.snd_pcm_close(self.pcm)


_OUTPUTS = (_PulseOutput, _AlsaOutput)


def available() -> bool:
    """Return whether at least one native output library is loadable."""
    return any(output.library() is not None for output in _OUTPUTS)


def backend_name():
    """Return the first loadable native backend name, or None."""
    for output in _OUTPUTS:
        if output.library() is not None:
            return output.name
    return None


def _open_output(rate: int, channels: int):
    for output in _OUTPUTS:
        if output.library() is None:
            continue
        try:
            return output(rate, channels)
        except Exception:
            continue
    return None


def stereo_gains(pan: float) -> tuple[float, float]:
    """Return left/right gains with the dominant channel kept at full level."""
    pan = max(-1.0, min(1.0, float(pan)))
    angle = (pan + 1.0) * math.pi / 4.0
    left, right = math.cos(angle), math.sin(angle)
    peak = max(left, right)
    return left / peak, right / peak


def _prepare_pcm(path: Path, volume: float, pan: float):
    """Read, scale and optionally pan a WAV into native 16-bit PCM."""
    try:
        with wave.open(str(path), "rb") as source:
            if source.getsampwidth() != 2 or source.getnchannels() not in (1, 2):
                return None
            input_channels = source.getnchannels()
            rate = source.getframerate()
            raw = source.readframes(source.getnframes())
    except Exception:
        return None

    raw = raw[:len(raw) - len(raw) % 2]
    volume = max(0.0, min(1.0, float(volume)))
    pan = max(-1.0, min(1.0, float(pan)))
    spatial = abs(pan) > PAN_THRESHOLD
    if volume >= 1.0 and not spatial:
        return raw, rate, input_channels

    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder == "big":
        samples.byteswap()

    if not spatial:
        for index, value in enumerate(samples):
            samples[index] = int(round(value * volume))
        if sys.byteorder == "big":
            samples.byteswap()
        return samples.tobytes(), rate, input_channels

    left_gain, right_gain = stereo_gains(pan)
    left_gain *= volume
    right_gain *= volume
    multiplier = 2 if input_channels == 1 else 1
    result = array.array("h", bytes(len(samples) * multiplier * 2))
    if input_channels == 1:
        for index, value in enumerate(samples):
            result[2 * index] = int(round(value * left_gain))
            result[2 * index + 1] = int(round(value * right_gain))
    else:
        for index in range(0, len(samples) - 1, 2):
            result[index] = int(round(samples[index] * left_gain))
            result[index + 1] = int(round(samples[index + 1] * right_gain))
    if sys.byteorder == "big":
        result.byteswap()
    return result.tobytes(), rate, 2


class Playback:
    """A native playback that can be stopped or joined."""

    __slots__ = ("_stop", "_thread")

    def __init__(self):
        self._stop = threading.Event()
        self._thread = None

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout=None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)


def play_wav(path: Path, *, volume: float = 1.0,
             pan: float = 0.0) -> "Playback | None":
    """Play a supported WAV asynchronously, returning None for fallback."""
    if volume <= 0.0 or not available():
        return None
    prepared = _prepare_pcm(Path(path), volume, pan)
    if prepared is None:
        return None
    pcm, rate, channels = prepared
    if not pcm:
        return None
    output = _open_output(rate, channels)
    if output is None:
        return None

    playback = Playback()

    def stream():
        try:
            step = CHUNK_FRAMES * channels * 2
            for start in range(0, len(pcm), step):
                if playback._stop.is_set():
                    break
                if not output.write(pcm[start:start + step]):
                    break
            if not playback._stop.is_set():
                output.drain()
        except Exception:
            pass
        finally:
            try:
                output.close()
            except Exception:
                pass
            with _lock:
                _active.discard(playback)

    with _lock:
        _active.add(playback)
    playback._thread = threading.Thread(
        target=stream, name="desktop-overlay-audio", daemon=True)
    playback._thread.start()
    return playback


def wait_all(timeout: float = 5.0) -> None:
    """Let active playbacks finish, with one timeout shared by the snapshot."""
    deadline = time.monotonic() + max(0.0, float(timeout))
    with _lock:
        playbacks = list(_active)
    for playback in playbacks:
        remaining = max(0.0, deadline - time.monotonic())
        playback.join(remaining)


def stop_all() -> None:
    """Ask every active native playback to stop."""
    with _lock:
        playbacks = list(_active)
    for playback in playbacks:
        playback.stop()


atexit.register(wait_all)
