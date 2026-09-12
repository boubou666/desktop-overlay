"""Small, policy-free helpers for creating unobtrusive Tk overlay windows."""

from __future__ import annotations

import sys

TRANSPARENT_KEY = "#ff00fe"
DEFAULT_BACKGROUND = "#0d1017"


class TkinterMissing(RuntimeError):
    """Raised when the platform's optional Tk installation is unavailable."""


def import_tk():
    """Import Tk lazily so headless and non-Tk consumers can use the package."""
    try:
        import tkinter as tk
        import tkinter.font as tkfont
    except Exception as exc:
        raise TkinterMissing("tkinter is unavailable") from exc
    return tk, tkfont


def make_click_through(window) -> bool:
    """Keep a Tk window out of the mouse, focus and taskbar paths on Windows.

    This must be called before the first deiconify: Windows decides activation
    when the window is first shown.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        gwl_exstyle = -20
        ws_ex_layered = 0x00080000
        ws_ex_transparent = 0x00000020
        ws_ex_noactivate = 0x08000000
        ws_ex_toolwindow = 0x00000080

        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, gwl_exstyle)
        user32.SetWindowLongW(
            hwnd,
            gwl_exstyle,
            style | ws_ex_layered | ws_ex_transparent
            | ws_ex_noactivate | ws_ex_toolwindow,
        )
        return True
    except Exception:
        return False


def setup_transparency(window, transparent_key: str = TRANSPARENT_KEY,
                       fallback_background: str = DEFAULT_BACKGROUND) -> str:
    """Configure the best Tk transparency available and return its background."""
    if sys.platform == "win32":
        try:
            window.wm_attributes("-transparentcolor", transparent_key)
            return transparent_key
        except Exception:
            return fallback_background

    if sys.platform == "darwin":
        try:
            window.wm_attributes("-transparent", True)
            window.configure(bg="systemTransparent")
            return "systemTransparent"
        except Exception:
            return fallback_background

    try:
        window.wm_attributes("-type", "splash")
    except Exception:
        pass
    return fallback_background


def prepare_window(window, transparent_key: str = TRANSPARENT_KEY,
                   fallback_background: str = DEFAULT_BACKGROUND) -> str:
    """Prepare an existing Tk or Toplevel window while it is still hidden.

    The caller remains responsible for its widgets and event loop. This helper
    owns only the cross-platform window-manager behavior.
    """
    try:
        window.withdraw()
    except Exception:
        pass
    try:
        window.overrideredirect(True)
    except Exception:
        pass
    for attribute, value in (("-topmost", True), ("-alpha", 0.0)):
        try:
            window.wm_attributes(attribute, value)
        except Exception:
            pass

    background = setup_transparency(window, transparent_key,
                                    fallback_background)
    try:
        window.configure(bg=background)
    except Exception:
        pass

    # The ordering is part of the contract: this happens while still hidden.
    make_click_through(window)
    return background


def geometry(width: int, height: int, x: int, y: int) -> str:
    """Return valid Tk geometry, including monitors left or above the origin."""
    return "{}x{}{:+d}{:+d}".format(int(width), int(height), int(x), int(y))


def move_window(window, width: int, height: int, x: int, y: int) -> None:
    """Resize and position a window in virtual-desktop coordinates."""
    window.geometry(geometry(width, height, x, y))


def set_opacity(window, opacity: float) -> None:
    """Set a clamped window opacity when the platform supports it."""
    value = max(0.0, min(1.0, float(opacity)))
    try:
        window.wm_attributes("-alpha", value)
    except Exception:
        pass


def show_window(window) -> None:
    """Show a prepared overlay without changing its activation styles."""
    window.deiconify()
