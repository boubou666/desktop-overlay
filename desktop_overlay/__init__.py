"""Shared building blocks for unobtrusive desktop overlays."""

__version__ = "0.1.0"

from .geometry import Monitor, ease_out, pan_for, pick_monitor

__all__ = ["Monitor", "ease_out", "pan_for", "pick_monitor", "__version__"]
