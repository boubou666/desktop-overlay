# Changelog

All notable changes to desktop-overlay are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- An Arch Linux recipe for the `python-desktop-overlay` package, built from
  the checksummed 0.2.0 release wheel.

## [0.2.0] - 2026-09-12

### Added

- Cross-platform monitor enumeration using Win32 work areas, CoreGraphics, or
  RandR 1.5 directly over X11 with an `xrandr` command fallback.
- A guaranteed positive fallback monitor when the platform backend is
  unavailable or reports invalid rectangles.

## [0.1.0] - 2026-09-12

### Added

- Shared monitor geometry with random, centered, corner, and edge-entry
  placement strategies.
- Safe Tk overlay-window preparation, including transparent backgrounds and
  Windows click-through/no-activation styles applied before the window is
  shown.
- Native WAV playback through PulseAudio/PipeWire or ALSA, with independent
  volume and stereo-position controls and no third-party dependency.
- Cross-platform tests on Python 3.8 through 3.14.

[Unreleased]: https://github.com/boubou666/desktop-overlay/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/boubou666/desktop-overlay/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/boubou666/desktop-overlay/releases/tag/v0.1.0
