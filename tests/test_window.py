import unittest
from unittest import mock

from desktop_overlay import window


class FakeWindow:
    def __init__(self):
        self.log = []
        self.attributes = {}
        self.background = None
        self.position = None

    def withdraw(self):
        self.log.append("withdraw")

    def overrideredirect(self, value):
        self.log.append(("overrideredirect", value))

    def wm_attributes(self, name, value):
        self.log.append(("attribute", name, value))
        self.attributes[name] = value

    def configure(self, **options):
        self.log.append(("configure", options))
        self.background = options.get("bg", self.background)

    def deiconify(self):
        self.log.append("deiconify")

    def geometry(self, value):
        self.position = value


class Preparation(unittest.TestCase):
    def test_windows_styles_are_applied_before_the_window_is_shown(self):
        target = FakeWindow()

        def styles(_target):
            target.log.append("styles")
            return True

        with mock.patch.object(window, "make_click_through", styles):
            window.prepare_window(target)
            self.assertNotIn("deiconify", target.log)
            window.show_window(target)
        self.assertLess(target.log.index("withdraw"), target.log.index("styles"))
        self.assertLess(target.log.index("styles"), target.log.index("deiconify"))

    def test_window_starts_topmost_and_invisible(self):
        target = FakeWindow()
        with mock.patch.object(window, "make_click_through", return_value=False):
            window.prepare_window(target)
        self.assertIs(target.attributes["-topmost"], True)
        self.assertEqual(target.attributes["-alpha"], 0.0)

    def test_windows_transparent_key_is_configurable(self):
        target = FakeWindow()
        with mock.patch.object(window.sys, "platform", "win32"), \
                mock.patch.object(window, "make_click_through", return_value=True):
            background = window.prepare_window(
                target, transparent_key="#123456",
                fallback_background="#000000")
        self.assertEqual(background, "#123456")
        self.assertEqual(target.background, "#123456")

    def test_linux_requests_a_splash_window(self):
        target = FakeWindow()
        with mock.patch.object(window.sys, "platform", "linux"):
            self.assertEqual(
                window.setup_transparency(target, fallback_background="#101010"),
                "#101010",
            )
        self.assertIn(("attribute", "-type", "splash"), target.log)


class PositionAndOpacity(unittest.TestCase):
    def test_geometry_supports_negative_monitor_coordinates(self):
        self.assertEqual(window.geometry(400, 200, -1920, -100),
                         "400x200-1920-100")
        self.assertEqual(window.geometry(400, 200, 20, 30),
                         "400x200+20+30")

    def test_move_uses_the_safe_geometry(self):
        target = FakeWindow()
        window.move_window(target, 400, 200, -1920, 30)
        self.assertEqual(target.position, "400x200-1920+30")

    def test_opacity_is_clamped(self):
        target = FakeWindow()
        window.set_opacity(target, 2)
        self.assertEqual(target.attributes["-alpha"], 1.0)
        window.set_opacity(target, -1)
        self.assertEqual(target.attributes["-alpha"], 0.0)


class ImportBehavior(unittest.TestCase):
    def test_missing_tk_has_a_specific_error(self):
        real_import = __import__

        def without_tk(name, *args, **kwargs):
            if name == "tkinter" or name.startswith("tkinter."):
                raise ImportError("Tk is not installed")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=without_tk):
            with self.assertRaises(window.TkinterMissing) as raised:
                window.import_tk()
        self.assertIsInstance(raised.exception.__cause__, ImportError)

if __name__ == "__main__":
    unittest.main()
