import array
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from desktop_overlay import audio


def write_wav(path: Path, channels: int, frames) -> Path:
    with wave.open(str(path), "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(2)
        target.setframerate(44100)
        flat = [value for frame in frames
                for value in (frame if isinstance(frame, tuple) else (frame,))]
        target.writeframes(struct.pack("<{}h".format(len(flat)), *flat))
    return path


def samples(pcm):
    result = array.array("h")
    result.frombytes(pcm)
    return list(result)


class PcmPreparation(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_full_volume_without_pan_preserves_mono(self):
        path = write_wav(self.root / "mono.wav", 1, [10000, -7777, 7, -9])
        pcm, rate, channels = audio._prepare_pcm(path, 1.0, 0.0)
        self.assertEqual((rate, channels), (44100, 1))
        self.assertEqual(samples(pcm), [10000, -7777, 7, -9])

    def test_volume_is_applied_to_every_sample(self):
        path = write_wav(self.root / "quiet.wav", 1, [10000, -8000, 7, -9])
        pcm, _rate, channels = audio._prepare_pcm(path, 0.5, 0.0)
        self.assertEqual(channels, 1)
        self.assertEqual(samples(pcm), [5000, -4000, 4, -4])

    def test_panned_mono_becomes_stereo(self):
        path = write_wav(self.root / "left.wav", 1, [10000, -10000])
        pcm, _rate, channels = audio._prepare_pcm(path, 1.0, -1.0)
        self.assertEqual(channels, 2)
        self.assertEqual(samples(pcm), [10000, 0, -10000, 0])

    def test_panned_stereo_keeps_each_source_channel(self):
        path = write_wav(self.root / "stereo.wav", 2, [(20000, 4000)])
        pcm, _rate, channels = audio._prepare_pcm(path, 1.0, -0.9)
        left, right = audio.stereo_gains(-0.9)
        self.assertEqual(channels, 2)
        self.assertEqual(
            samples(pcm),
            [int(round(20000 * left)), int(round(4000 * right))],
        )

    def test_volume_and_pan_compose(self):
        path = write_wav(self.root / "both.wav", 1, [10000])
        pcm, _rate, channels = audio._prepare_pcm(path, 0.5, 1.0)
        self.assertEqual(channels, 2)
        self.assertEqual(samples(pcm), [0, 5000])

    def test_values_are_clamped(self):
        path = write_wav(self.root / "clamped.wav", 1, [10000])
        loud, _rate, _channels = audio._prepare_pcm(path, 9.0, 0.0)
        right, _rate, _channels = audio._prepare_pcm(path, 1.0, 9.0)
        self.assertEqual(samples(loud), [10000])
        self.assertEqual(samples(right), [0, 10000])

    def test_unsupported_or_unreadable_files_return_none(self):
        narrow = self.root / "8-bit.wav"
        with wave.open(str(narrow), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(1)
            target.setframerate(44100)
            target.writeframes(b"\x80" * 8)
        self.assertIsNone(audio._prepare_pcm(narrow, 1.0, 0.0))
        self.assertIsNone(audio._prepare_pcm(self.root / "missing", 1.0, 0.0))


class FakeAlsaLibrary:
    def __init__(self, results):
        self.results = list(results)
        self.prepares = 0

    def snd_pcm_writei(self, _pcm, _block, frames):
        if not self.results:
            return frames
        result = self.results.pop(0)
        return frames if result == "all" else result

    def snd_pcm_prepare(self, _pcm):
        self.prepares += 1


class AlsaRecovery(unittest.TestCase):
    def output(self, results, channels=1):
        target = audio._AlsaOutput.__new__(audio._AlsaOutput)
        target.lib = FakeAlsaLibrary(results)
        target.pcm = None
        target.channels = channels
        return target

    @staticmethod
    def block(frames, channels=1):
        return b"\0" * frames * channels * 2

    def test_partial_writes_continue(self):
        self.assertTrue(self.output([10, 20, "all"]).write(self.block(64)))

    def test_underrun_is_prepared_and_retried(self):
        target = self.output([-audio.EPIPE, "all"])
        self.assertTrue(target.write(self.block(64)))
        self.assertEqual(target.lib.prepares, 1)

    def test_real_error_stops_immediately(self):
        target = self.output([-5])
        self.assertFalse(target.write(self.block(64)))
        self.assertEqual(target.lib.prepares, 0)

    def test_perpetual_zero_or_underrun_is_bounded(self):
        self.assertFalse(
            self.output([0] * 100).write(self.block(64)))
        self.assertFalse(
            self.output([-audio.EPIPE] * 100).write(self.block(64)))

    def test_frame_count_uses_the_channel_count(self):
        seen = []
        target = self.output([], channels=2)
        target.lib.snd_pcm_writei = (
            lambda _pcm, _block, frames: seen.append(frames) or frames)
        self.assertTrue(target.write(self.block(32, channels=2)))
        self.assertEqual(seen, [32])


class BackendChoice(unittest.TestCase):
    def setUp(self):
        self.original = audio._OUTPUTS
        self.addCleanup(setattr, audio, "_OUTPUTS", self.original)

    @staticmethod
    def output(name, available=True, broken=False):
        class Fake:
            @staticmethod
            def library():
                return object() if available else None

            def __init__(self, rate, channels):
                if broken:
                    raise OSError("refused")
                self.rate = rate
                self.channels = channels

        Fake.name = name
        return Fake

    def test_first_usable_output_wins(self):
        first = self.output("first")
        second = self.output("second")
        audio._OUTPUTS = (first, second)
        self.assertIsInstance(audio._open_output(44100, 2), first)
        self.assertEqual(audio.backend_name(), "first")

    def test_refused_output_hands_over_to_the_next(self):
        first = self.output("first", broken=True)
        second = self.output("second")
        audio._OUTPUTS = (first, second)
        self.assertIsInstance(audio._open_output(44100, 1), second)

    def test_missing_libraries_mean_fallback(self):
        audio._OUTPUTS = (self.output("missing", available=False),)
        self.assertFalse(audio.available())
        self.assertIsNone(audio.backend_name())
        self.assertIsNone(audio.play_wav(Path("anything.wav")))


class PlaybackLifecycle(unittest.TestCase):
    def test_muted_playback_does_not_probe_the_system(self):
        with mock.patch.object(audio, "available") as available:
            self.assertIsNone(audio.play_wav(Path("anything.wav"), volume=0.0))
        available.assert_not_called()

    def test_stop_all_snapshots_under_the_lock(self):
        playback = mock.Mock()
        with mock.patch.object(audio, "_active", {playback}):
            audio.stop_all()
        playback.stop.assert_called_once()

    def test_wait_uses_one_shared_deadline(self):
        first, second = mock.Mock(), mock.Mock()
        clock = iter([10.0, 11.0, 14.5])
        with mock.patch.object(audio, "_active", {first, second}), \
                mock.patch.object(audio.time, "monotonic",
                                  side_effect=lambda: next(clock)):
            audio.wait_all(5.0)
        timeouts = sorted([
            first.join.call_args.args[0],
            second.join.call_args.args[0],
        ])
        self.assertEqual(timeouts, [0.5, 4.0])

    def test_playback_thread_writes_drains_and_closes(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = write_wav(Path(directory.name) / "tone.wav", 1, [100] * 16)
        output = mock.Mock(**{"write.return_value": True})
        with mock.patch.object(audio, "available", return_value=True), \
                mock.patch.object(audio, "_open_output", return_value=output):
            playback = audio.play_wav(path, volume=0.5, pan=0.0)
        self.assertIsNotNone(playback)
        playback.join(5)
        output.write.assert_called()
        output.drain.assert_called_once()
        output.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
