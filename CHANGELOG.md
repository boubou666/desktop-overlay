# Changelog

All notable changes to desktop-overlay are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/boubou666/desktop-overlay/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/boubou666/desktop-overlay/releases/tag/v0.1.0
