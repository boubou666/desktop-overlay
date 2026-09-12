"""Shared building blocks for unobtrusive desktop overlays."""

__version__ = "0.2.1"

from .geometry import Monitor, ease_out, pan_for, pick_monitor
from .monitors import enumerate_monitors

__all__ = [
    "Monitor",
    "ease_out",
    "enumerate_monitors",
    "pan_for",
    "pick_monitor",
    "__version__",
]
