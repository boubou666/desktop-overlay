"""Cross-platform monitor enumeration with no third-party dependency.

Tk reports either the primary display or the whole virtual desktop, depending
on the platform. Overlay applications need the usable rectangle of each
monitor, so this module asks the operating system directly and always returns
at least one :class:`~desktop_overlay.geometry.Monitor`.

Linux prefers RandR 1.5 over the X11 socket. This keeps enumeration available
on small installations without the ``xrandr`` executable. The command-line
backend remains as a compatibility fallback.
"""

from __future__ import annotations

import os
import re
import socket
import struct
import subprocess
import sys

from .geometry import Monitor


def _windows_monitors() -> list[Monitor]:
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", ctypes.c_ulong),
            ("szDevice", ctypes.c_wchar * 32),
        ]

    monitorinfof_primary = 0x00000001
    user32 = ctypes.windll.user32
    found: list[Monitor] = []

    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(RECT),
        ctypes.c_ssize_t,
    )

    def callback(handle, _hdc, _rect, _param):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(ctypes.c_void_p(handle), ctypes.byref(info)):
            work = info.rcWork
            found.append(
                Monitor(
                    work.left,
                    work.top,
                    work.right - work.left,
                    work.bottom - work.top,
                    primary=bool(info.dwFlags & monitorinfof_primary),
                    name=info.szDevice,
                )
            )
        return 1

    user32.EnumDisplayMonitors(
        wintypes.HDC(), None, callback_type(callback), ctypes.c_ssize_t(0)
    )
    return found


_XRANDR_LINE = re.compile(
    r"^\s*(?P<index>\d+):\s+\+(?P<primary>\*?)(?P<name>\S+)\s+"
    r"(?P<width>\d+)/\d+x(?P<height>\d+)/\d+\+(?P<x>-?\d+)\+(?P<y>-?\d+)"
)

_X_GET_ATOM_NAME = 17
_X_QUERY_EXTENSION = 98
_RR_QUERY_VERSION = 0
_RR_GET_MONITORS = 42


def _x_pad(length: int) -> int:
    return -length % 4


def _x_cookie(display_number: str) -> tuple[bytes, bytes]:
    """Read a matching MIT-MAGIC-COOKIE-1 entry from Xauthority."""
    path = os.environ.get("XAUTHORITY") or os.path.expanduser("~/.Xauthority")
    try:
        with open(path, "rb") as handle:
            blob = handle.read()
    except OSError:
        return b"", b""

    entries = []
    offset = 0
    while offset + 2 <= len(blob):
        try:
            family, = struct.unpack_from(">H", blob, offset)
            offset += 2
            fields = []
            for _ in range(4):
                size, = struct.unpack_from(">H", blob, offset)
                offset += 2
                fields.append(blob[offset:offset + size])
                offset += size
        except struct.error:
            break
        entries.append((family,) + tuple(fields))

    host = socket.gethostname().encode()
    for strict in (True, False):
        for family, address, number, name, data in entries:
            if name != b"MIT-MAGIC-COOKIE-1":
                continue
            if number.decode("latin-1") not in ("", display_number):
                continue
            if strict and family == 256 and address != host:
                continue
            return name, data
    return b"", b""


class _XConnection:
    """The small subset of X11 needed to ask RandR for monitor rectangles."""

    def __init__(self):
        display = os.environ.get("DISPLAY") or ":0"
        host, _, tail = display.rpartition(":")
        host = host.replace("/unix", "").replace("unix/", "")
        number = tail.split(".")[0] or "0"
        self.sock = self._open(host, number)
        self.sock.settimeout(4)
        try:
            self._setup(*_x_cookie(number))
        except Exception:
            self.close()
            raise

    @staticmethod
    def _open(host: str, number: str) -> socket.socket:
        if host in ("", "unix", "localhost"):
            addresses = (
                "\0/tmp/.X11-unix/X" + number,
                "/tmp/.X11-unix/X" + number,
            )
            for address in addresses:
                candidate = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    candidate.connect(address)
                    return candidate
                except OSError:
                    candidate.close()
            if host == "":
                raise ConnectionError("no X socket for display :" + number)
        return socket.create_connection((host or "localhost", 6000 + int(number)), 4)

    def _recv(self, size: int) -> bytes:
        buffer = b""
        while len(buffer) < size:
            chunk = self.sock.recv(size - len(buffer))
            if not chunk:
                raise ConnectionError("the X server closed the connection")
            buffer += chunk
        return buffer

    def _setup(self, name: bytes, data: bytes) -> None:
        order = 0x42 if sys.byteorder == "big" else 0x6C
        self.endian = ">" if order == 0x42 else "<"
        self.sock.sendall(
            struct.pack(self.endian + "BxHHHH2x", order, 11, 0, len(name), len(data))
            + name + b"\0" * _x_pad(len(name))
            + data + b"\0" * _x_pad(len(data))
        )
        status, _, _, _, extra = struct.unpack(self.endian + "BBHHH", self._recv(8))
        body = self._recv(extra * 4)
        if status != 1:
            raise ConnectionError("the X server refused the connection")
        vendor, _, screen_count, formats = struct.unpack_from(
            self.endian + "HHBB", body, 16
        )
        if not screen_count:
            raise ConnectionError("the X server reported no screen")
        offset = 32 + vendor + _x_pad(vendor) + 8 * formats
        self.root, = struct.unpack_from(self.endian + "I", body, offset)

    def request(self, major: int, minor: int, payload: bytes = b"") -> bytes:
        payload += b"\0" * _x_pad(len(payload))
        self.sock.sendall(
            struct.pack(self.endian + "BBH", major, minor, 1 + len(payload) // 4)
            + payload
        )
        while True:
            packet = self._recv(32)
            if packet[0] == 0:
                raise OSError("X11 error code {}".format(packet[1]))
            if packet[0] == 1:
                extra, = struct.unpack_from(self.endian + "I", packet, 4)
                return packet + (self._recv(extra * 4) if extra else b"")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def _linux_monitors_wire() -> list[Monitor]:
    connection = None
    try:
        connection = _XConnection()
        endian = connection.endian
        reply = connection.request(
            _X_QUERY_EXTENSION,
            0,
            struct.pack(endian + "H2x", 5) + b"RANDR",
        )
        present, opcode = struct.unpack_from(endian + "2B", reply, 8)
        if not present:
            return []

        reply = connection.request(
            opcode, _RR_QUERY_VERSION, struct.pack(endian + "II", 1, 5)
        )
        if struct.unpack_from(endian + "II", reply, 8) < (1, 5):
            return []

        reply = connection.request(
            opcode,
            _RR_GET_MONITORS,
            struct.pack(endian + "IBxxx", connection.root, 1),
        )
        count, = struct.unpack_from(endian + "4xI", reply, 8)

        found: list[Monitor] = []
        offset = 32
        for _ in range(count):
            atom, primary, _automatic, outputs, x, y, width, height = (
                struct.unpack_from(endian + "IBBHhhHH", reply, offset)
            )
            offset += 24 + 4 * outputs
            named = connection.request(
                _X_GET_ATOM_NAME, 0, struct.pack(endian + "I", atom)
            )
            size, = struct.unpack_from(endian + "H", named, 8)
            found.append(
                Monitor(
                    x,
                    y,
                    width,
                    height,
                    primary=bool(primary),
                    name=named[32:32 + size].decode("latin-1"),
                )
            )
        return found
    finally:
        if connection is not None:
            connection.close()


def _linux_monitors_cli() -> list[Monitor]:
    try:
        result = subprocess.run(
            ["xrandr", "--listmonitors"],
            capture_output=True,
            text=True,
            timeout=4,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []

    found: list[Monitor] = []
    for line in result.stdout.splitlines():
        match = _XRANDR_LINE.match(line)
        if not match:
            continue
        found.append(
            Monitor(
                match.group("x"),
                match.group("y"),
                match.group("width"),
                match.group("height"),
                primary=bool(match.group("primary")),
                name=match.group("name"),
            )
        )
    return found


def _linux_monitors() -> list[Monitor]:
    for detect in (_linux_monitors_wire, _linux_monitors_cli):
        try:
            found = detect()
        except Exception:
            continue
        if found:
            return found
    return []


def _macos_monitors() -> list[Monitor]:
    import ctypes
    import ctypes.util

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    class CGSize(ctypes.Structure):
        _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]

    class CGRect(ctypes.Structure):
        _fields_ = [("origin", CGPoint), ("size", CGSize)]

    path = ctypes.util.find_library("CoreGraphics")
    if not path:
        return []
    core = ctypes.cdll.LoadLibrary(path)

    max_displays = 16
    displays = (ctypes.c_uint32 * max_displays)()
    count = ctypes.c_uint32(0)
    if core.CGGetActiveDisplayList(max_displays, displays, ctypes.byref(count)) != 0:
        return []

    core.CGDisplayBounds.restype = CGRect
    core.CGDisplayBounds.argtypes = [ctypes.c_uint32]
    core.CGMainDisplayID.restype = ctypes.c_uint32

    main_id = core.CGMainDisplayID()
    found: list[Monitor] = []
    for index in range(count.value):
        display_id = displays[index]
        bounds = core.CGDisplayBounds(display_id)
        found.append(
            Monitor(
                bounds.origin.x,
                bounds.origin.y,
                bounds.size.width,
                bounds.size.height,
                primary=(display_id == main_id),
                name="display-{}".format(display_id),
            )
        )
    return found


def enumerate_monitors(fallback_width: int = 1920,
                       fallback_height: int = 1080) -> list[Monitor]:
    """Return usable monitor rectangles, or one safe fallback rectangle."""
    detect = {
        "win32": _windows_monitors,
        "darwin": _macos_monitors,
    }.get(sys.platform, _linux_monitors)

    try:
        found = detect()
    except Exception:
        found = []

    found = [
        monitor for monitor in found
        if monitor.width > 0 and monitor.height > 0
    ]
    if not found:
        width = max(1, int(fallback_width))
        height = max(1, int(fallback_height))
        found = [Monitor(0, 0, width, height, primary=True, name="screen")]
    return found


__all__ = ["enumerate_monitors"]