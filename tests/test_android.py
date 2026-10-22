import sys
import types
import unittest
from unittest import mock

from desktop_overlay import android, audio, enumerate_monitors, monitors


def fake_java(classes):
    """A stand-in for Chaquopy's `java` module, serving the given classes."""
    module = types.ModuleType("java")

    def jclass(name):
        if name not in classes:
            raise LookupError(name)
        return classes[name]

    module.jclass = jclass
    return module


def on_android(classes):
    """Pretend to run inside an Android app with Chaquopy."""
    return mock.patch.multiple(
        sys, getandroidapilevel=mock.Mock(return_value=34), create=True
    ), mock.patch.dict(sys.modules, {"java": fake_java(classes)})


class Detection(unittest.TestCase):
    def test_desktop_interpreters_are_not_android(self):
        if hasattr(sys, "getandroidapilevel"):
            self.skipTest("running on Android")
        self.assertFalse(android.is_android())
        self.assertIsNone(android.jclass("android.media.AudioTrack"))
        self.assertIsNone(android.context())

    def test_classes_come_from_the_java_bridge(self):
        track = object()
        api, bridge = on_android({"android.media.AudioTrack": track})
        with api, bridge:
            self.assertTrue(android.is_android())
            self.assertIs(android.jclass("android.media.AudioTrack"), track)
            self.assertIsNone(android.jclass("android.missing"))

    def test_missing_bridge_means_no_classes(self):
        with mock.patch.object(sys, "getandroidapilevel", create=True), \
                mock.patch.dict(sys.modules, {"java": None}):
            self.assertIsNone(android.jclass("android.media.AudioTrack"))


class Monitors(unittest.TestCase):
    @staticmethod
    def platform(width, height):
        class Metrics:
            widthPixels = 0
            heightPixels = 0

        class Display:
            @staticmethod
            def getRealMetrics(metrics):
                metrics.widthPixels = width
                metrics.heightPixels = height

        app = mock.Mock()
        app.getSystemService.return_value.getDefaultDisplay.return_value = Display
        python = mock.Mock()
        python.getPlatform.return_value.getApplication.return_value = app
        return {"com.chaquo.python.Python": python,
                "android.util.DisplayMetrics": Metrics}

    def test_the_real_display_size_is_the_only_monitor(self):
        api, bridge = on_android(self.platform(3840, 2160))
        with api, bridge, mock.patch.object(monitors, "_linux_monitors") as linux:
            found = enumerate_monitors()
        linux.assert_not_called()
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].x, found[0].y, found[0].width,
                          found[0].height), (0, 0, 3840, 2160))
        self.assertTrue(found[0].primary)

    def test_without_an_app_context_the_fallback_is_used(self):
        api, bridge = on_android({})
        with api, bridge:
            found = enumerate_monitors(1280, 720)
        self.assertEqual(
            [(m.x, m.y, m.width, m.height, m.primary) for m in found],
            [(0, 0, 1280, 720, True)])


class AudioTrackOutput(unittest.TestCase):
    def setUp(self):
        self.track = mock.Mock()
        self.track.write.side_effect = lambda block, offset, size: size
        self.track.getPlaybackHeadPosition.return_value = 0
        builder = mock.MagicMock()
        for step in ("setAudioAttributes", "setAudioFormat",
                     "setBufferSizeInBytes", "setTransferMode"):
            getattr(builder, step).return_value = builder
        builder.build.return_value = self.track
        self.track_class = mock.Mock(MODE_STREAM=1)
        self.track_class.getMinBufferSize.return_value = 1024
        self.track_class.Builder.return_value = builder
        api, bridge = on_android({
            "android.media.AudioTrack": self.track_class,
            "android.media.AudioFormat": mock.MagicMock(
                CHANNEL_OUT_MONO=4, CHANNEL_OUT_STEREO=12,
                ENCODING_PCM_16BIT=2),
            "android.media.AudioAttributes": mock.MagicMock(),
        })
        api.start()
        bridge.start()
        self.addCleanup(api.stop)
        self.addCleanup(bridge.stop)

    def test_android_output_comes_first(self):
        self.assertIs(audio._OUTPUTS[0], audio._AndroidOutput)
        self.assertEqual(audio.backend_name(), "Android AudioTrack")

    def test_stereo_stream_is_opened_and_started(self):
        audio._AndroidOutput(44100, 2)
        self.track_class.getMinBufferSize.assert_called_once_with(44100, 12, 2)
        self.track.play.assert_called_once_with()

    def test_writes_count_frames_and_report_short_writes(self):
        output = audio._AndroidOutput(44100, 2)
        self.assertTrue(output.write(b"\0" * 400))
        self.assertEqual(output.frames, 100)
        self.track.write.side_effect = lambda block, offset, size: size - 4
        self.assertFalse(output.write(b"\0" * 400))
        self.track.write.side_effect = lambda block, offset, size: -3
        self.assertFalse(output.write(b"\0" * 400))

    def test_drain_waits_for_the_playback_head(self):
        output = audio._AndroidOutput(44100, 1)
        output.write(b"\0" * 200)
        self.track.getPlaybackHeadPosition.side_effect = [10, 60, 100]
        with mock.patch.object(audio.time, "sleep") as sleep:
            output.drain()
        self.assertEqual(sleep.call_count, 2)

    def test_close_stops_then_releases(self):
        output = audio._AndroidOutput(44100, 1)
        self.track.stop.side_effect = RuntimeError("already stopped")
        with self.assertRaises(RuntimeError):
            output.close()
        self.track.release.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
