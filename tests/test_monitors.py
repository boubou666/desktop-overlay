import socket
import unittest
from unittest import mock

from desktop_overlay import Monitor, enumerate_monitors
from desktop_overlay import monitors


class PublicEnumeration(unittest.TestCase):
    def test_dispatches_to_the_current_platform(self):
        expected = [Monitor(10, 20, 800, 600, primary=True, name="test")]
        with mock.patch.object(monitors.sys, "platform", "win32"), \
                mock.patch.object(monitors, "_windows_monitors",
                                  return_value=expected) as detect:
            self.assertIs(enumerate_monitors()[0], expected[0])
        detect.assert_called_once_with()

    def test_returns_a_positive_fallback(self):
        with mock.patch.object(monitors.sys, "platform", "win32"), \
                mock.patch.object(monitors, "_windows_monitors",
                                  side_effect=OSError("unavailable")):
            found = enumerate_monitors(1280, 720)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].primary)
        self.assertEqual(
            (found[0].x, found[0].y, found[0].width, found[0].height),
            (0, 0, 1280, 720),
        )

    def test_discards_invalid_rectangles(self):
        invalid = [
            Monitor(0, 0, 0, 600),
            Monitor(0, 0, 800, -1),
        ]
        with mock.patch.object(monitors.sys, "platform", "win32"), \
                mock.patch.object(monitors, "_windows_monitors",
                                  return_value=invalid):
            found = enumerate_monitors(640, 480)
        self.assertEqual((found[0].width, found[0].height), (640, 480))


class LinuxEnumeration(unittest.TestCase):
    @staticmethod
    def one(name):
        return [Monitor(0, 0, 800, 600, name=name)]

    def test_direct_randr_precedes_the_command(self):
        with mock.patch.object(
                monitors, "_linux_monitors_wire",
                return_value=self.one("wire")) as wire, \
                mock.patch.object(
                    monitors, "_linux_monitors_cli",
                    return_value=self.one("cli")) as command:
            found = monitors._linux_monitors()
        self.assertEqual([item.name for item in found], ["wire"])
        wire.assert_called_once_with()
        command.assert_not_called()

    def test_command_is_used_after_a_socket_failure(self):
        with mock.patch.object(
                monitors, "_linux_monitors_wire",
                side_effect=ConnectionError("refused")), \
                mock.patch.object(
                    monitors, "_linux_monitors_cli",
                    return_value=self.one("cli")):
            found = monitors._linux_monitors()
        self.assertEqual([item.name for item in found], ["cli"])

    def test_xrandr_output_is_parsed(self):
        result = mock.Mock(
            returncode=0,
            stdout=(
                "Monitors: 2\n"
                " 0: +*eDP-1 2256/280x1504/190+0+0  eDP-1\n"
                " 1: +DP-9 1920/540x1080/300+2256+-100  DP-9\n"
            ),
        )
        with mock.patch.object(monitors.subprocess, "run",
                               return_value=result) as run:
            found = monitors._linux_monitors_cli()
        run.assert_called_once_with(
            ["xrandr", "--listmonitors"],
            capture_output=True,
            text=True,
            timeout=4,
        )
        self.assertEqual([item.name for item in found], ["eDP-1", "DP-9"])
        self.assertEqual(
            (found[1].x, found[1].y, found[1].width, found[1].height),
            (2256, -100, 1920, 1080),
        )
        self.assertTrue(found[0].primary)
        self.assertFalse(found[1].primary)

    def test_connection_closes_when_the_handshake_fails(self):
        left, right = socket.socketpair()
        self.addCleanup(right.close)
        self.addCleanup(left.close)

        with mock.patch.object(monitors._XConnection, "_open",
                               return_value=left), \
                mock.patch.object(monitors._XConnection, "_setup",
                                  side_effect=ConnectionError("refused")):
            with self.assertRaises(ConnectionError):
                monitors._XConnection()
        self.assertEqual(left.fileno(), -1)


if __name__ == "__main__":
    unittest.main()