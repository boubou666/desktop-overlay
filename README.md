# desktop-overlay

Small, zero-dependency Python building blocks for desktop overlays.

This project extracts the platform work shared by
[doot](https://github.com/boubou666/doot) and
[butbutbut](https://github.com/boubou666/butbutbut): monitor geometry,
unobtrusive Tk windows, animation timing, native pixel surfaces, and audio.
Applications keep ownership of what they draw and when they draw it.

The project is in alpha. Version 0.2.0 provides cross-platform monitor
enumeration, common geometry, Tk window preparation, and native Linux WAV
playback that the two applications had started maintaining separately.

## Principles

- Python 3.8 or newer.
- Standard library only.
- Windows, macOS, and Linux are tested.
- Headless imports: using geometry or audio must not create a Tk window.
- Platform failures return a usable fallback instead of taking down the caller.
- Application policy remains in the application.

## Installation

Until the first PyPI release, install directly from GitHub:

~~~console
python -m pip install git+https://github.com/boubou666/desktop-overlay.git@v0.2.0
~~~

On Arch Linux, the repository also contains a package recipe:

~~~console
cd packaging
makepkg -si
~~~

It installs the same release wheel under the package name
`python-desktop-overlay`, allowing several overlay applications to share one
owned copy.

## Monitor geometry

The same monitor can support a random ambient appearance or an anchored
notification without embedding either policy in monitor enumeration:

~~~python
from desktop_overlay import Monitor

monitor = Monitor(1920, 0, 1920, 1080, primary=False, name="right")

x, y = monitor.random_position(400, 200)
x, y = monitor.corner_position(400, 200, "bottom-right", margin=24)
start_x, start_y, x, y = monitor.edge_entry(400, 200, "left")
~~~

Enumerate the active monitors, then make the caller's selection policy
explicit:

~~~python
from desktop_overlay import enumerate_monitors, pick_monitor

monitors = enumerate_monitors()
monitor = pick_monitor(monitors, preference=None, default="primary")
monitor = pick_monitor(monitors, preference=None, default="random")
~~~

Windows enumeration uses each display's work area so overlays avoid the
taskbar. Linux uses RandR 1.5 directly over X11 before trying `xrandr`, and
macOS uses CoreGraphics. A positive fallback monitor is always returned.

## Tk overlay windows

Prepare a Tk or Toplevel while it is still hidden, add the application's
widgets, position it, then show it:

~~~python
import tkinter as tk
from desktop_overlay import window

root = tk.Tk()
background = window.prepare_window(root)
label = tk.Label(root, text="hello", bg=background)
label.pack()
window.move_window(root, 300, 80, -1920, 24)
window.show_window(root)
root.mainloop()
~~~

On Windows, click-through, no-activation, and tool-window styles are installed
before the first display. This prevents an overlay from taking focus or
flashing a taskbar button over a full-screen application.

## Native WAV audio

The native backend handles 16-bit mono and stereo WAV files on Linux through
PulseAudio/PipeWire, then ALSA. Returning None means the caller should use its
usual external-player fallback.

~~~python
from desktop_overlay.audio import play_wav

playback = play_wav("alert.wav", volume=0.65, pan=-0.4)
~~~

Volume ranges from 0 to 1 and pan from -1 (left) to +1 (right). Both values are
clamped. A panned mono file is expanded to stereo; volume-only playback keeps
the source channel count.

## Roadmap

- A monotonic animation timeline usable from blocking and Tk event loops.
- Doot's X11 and Wayland pixel surfaces.
- Migration adapters and releases for Doot and ButButBut.

## Development

~~~console
python -m unittest discover -s tests -v
python -m compileall -q desktop_overlay tests
~~~

The code is licensed under the MIT License.
