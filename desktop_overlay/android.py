"""Access to the Android platform when running inside an embedded Python.

Android has no display server and no audio library that ctypes can open, so
overlays reach the platform through Java. Chaquopy, which embeds CPython in an
Android app, exposes Java classes through its ``java`` module; everything here
imports it lazily so desktop installations never touch it.
"""

from __future__ import annotations

import sys


def is_android() -> bool:
    """Return whether this interpreter was built for Android.

    CPython defines ``sys.getandroidapilevel`` only in Android builds, while
    ``sys.platform`` stays ``"linux"`` before Python 3.13.
    """
    return hasattr(sys, "getandroidapilevel")


def jclass(name: str):
    """Return a Java class, or None outside an Android app with Chaquopy."""
    if not is_android():
        return None
    try:
        from java import jclass as _jclass
    except Exception:
        return None
    try:
        return _jclass(name)
    except Exception:
        return None


def byte_array(data: bytes):
    """Return `data` as a Java byte[], which overloaded Java methods need."""
    from java import jarray, jbyte

    return jarray(jbyte)(data)


def context():
    """Return the Android application context, or None."""
    python = jclass("com.chaquo.python.Python")
    if python is None:
        return None
    try:
        return python.getPlatform().getApplication()
    except Exception:
        return None


__all__ = ["byte_array", "context", "is_android", "jclass"]
