"""Monitor geometry and placement policies shared by desktop overlays.

The operating-system enumeration will live beside this module. Geometry stays
independent so it can be tested without a display server and so applications
can supply monitor information from another backend, such as Wayland.
"""

from __future__ import annotations

import random

SIDES = ("left", "right", "top", "bottom")
CORNERS = ("bottom-right", "bottom-left", "top-right", "top-left", "center")


class Monitor:
    """One monitor's usable rectangle in virtual-desktop coordinates."""

    __slots__ = ("x", "y", "width", "height", "primary", "name")

    def __init__(self, x, y, width, height, primary=False, name=""):
        self.x = int(x)
        self.y = int(y)
        self.width = int(width)
        self.height = int(height)
        self.primary = bool(primary)
        self.name = name or "screen"

    def random_position(self, width: int, height: int, center: bool = False,
                        rng=random) -> tuple[int, int]:
        """Place a rectangle randomly on this monitor, or center it."""
        if center:
            return (
                self.x + (self.width - width) // 2,
                self.y + (self.height - height) // 2,
            )
        return (
            self.x + rng.randint(0, max(0, self.width - width)),
            self.y + rng.randint(0, max(0, self.height - height)),
        )

    def corner_position(self, width: int, height: int,
                        corner: str = "bottom-right",
                        margin: int = 24) -> tuple[int, int]:
        """Anchor a rectangle to a corner while keeping it on the monitor."""
        corner = (corner or "bottom-right").strip().lower()
        if corner not in CORNERS:
            corner = "bottom-right"

        if corner == "center":
            return (
                self.x + (self.width - width) // 2,
                self.y + (self.height - height) // 2,
            )

        left = corner.endswith("left")
        top = corner.startswith("top")
        x = self.x + margin if left else self.x + self.width - width - margin
        y = self.y + margin if top else self.y + self.height - height - margin
        x = max(self.x, min(x, self.x + max(0, self.width - width)))
        y = max(self.y, min(y, self.y + max(0, self.height - height)))
        return x, y

    def edge_entry(self, width: int, height: int, side: str, rng=random,
                   near=(0.0, 0.03), center: bool = False
                   ) -> tuple[int, int, int, int]:
        """Return the off-screen start and on-screen rest position.

        The result is (start_x, start_y, rest_x, rest_y). The rectangle stops
        against the same edge it entered from.
        """
        side = str(side).strip().lower()
        if side not in SIDES:
            raise ValueError("unknown edge: {!r}".format(side))

        free_x = max(0, self.width - width)
        free_y = max(0, self.height - height)

        def along(free: int) -> int:
            return free // 2 if center else rng.randint(0, free)

        if side in ("left", "right"):
            inset = min(int(rng.uniform(*near) * self.width), free_x)
            if side == "left":
                rest_x, start_x = self.x + inset, self.x - width
            else:
                rest_x, start_x = self.x + free_x - inset, self.x + self.width
            rest_y = start_y = self.y + along(free_y)
        else:
            inset = min(int(rng.uniform(*near) * self.height), free_y)
            if side == "top":
                rest_y, start_y = self.y + inset, self.y - height
            else:
                rest_y, start_y = self.y + free_y - inset, self.y + self.height
            rest_x = start_x = self.x + along(free_x)

        return start_x, start_y, rest_x, rest_y

    def __repr__(self):
        flag = "*" if self.primary else " "
        return "<Monitor {}{} {}x{}+{}+{}>".format(
            flag, self.name, self.width, self.height, self.x, self.y)


def pick_monitor(found, preference=None, default="primary", rng=random) -> Monitor:
    """Choose a monitor using an explicit application policy.

    default is either primary for anchored notifications or random for ambient
    appearances. An explicit index is clamped.
    """
    found = list(found)
    if not found:
        return Monitor(0, 0, 1920, 1080, primary=True)

    wanted = preference
    if wanted in (None, ""):
        wanted = default

    if wanted in ("random", "any", "all"):
        return rng.choice(found)
    if wanted in ("primary", "main", "principal"):
        return next((monitor for monitor in found if monitor.primary), found[0])

    try:
        index = int(wanted)
    except (TypeError, ValueError):
        if default == "random":
            return rng.choice(found)
        return next((monitor for monitor in found if monitor.primary), found[0])
    return found[max(0, min(index, len(found) - 1))]


def ease_out(progress: float) -> float:
    """Cubic easing that starts quickly and settles gently."""
    progress = max(0.0, min(1.0, float(progress)))
    return 1.0 - (1.0 - progress) ** 3


def horizontal_bounds(found) -> tuple[int, int]:
    """Return the left and right edges of the whole virtual desktop."""
    found = list(found)
    if not found:
        return 0, 0
    return (
        min(monitor.x for monitor in found),
        max(monitor.x + monitor.width for monitor in found),
    )


def pan_for(center_x: float, found) -> float:
    """Map a horizontal desktop coordinate to a stereo pan from -1 to +1."""
    left, right = horizontal_bounds(found)
    span = right - left
    if span <= 0:
        return 0.0
    ratio = (center_x - left) / span
    return max(-1.0, min(1.0, ratio * 2.0 - 1.0))
