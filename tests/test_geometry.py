import unittest

from desktop_overlay import geometry


class FixedRandom:
    def __init__(self, integer=0, fraction=0.0, choice=0):
        self.integer = integer
        self.fraction = fraction
        self.choice_index = choice

    def randint(self, low, high):
        return max(low, min(self.integer, high))

    def uniform(self, low, high):
        return low + (high - low) * self.fraction

    def choice(self, values):
        return values[self.choice_index]


class MonitorPlacement(unittest.TestCase):
    def setUp(self):
        self.monitor = geometry.Monitor(1920, -100, 1920, 1080,
                                        primary=False, name="right")

    def test_center_respects_the_virtual_desktop_offset(self):
        self.assertEqual(
            self.monitor.random_position(400, 200, center=True),
            (2680, 340),
        )

    def test_random_position_stays_inside_the_monitor(self):
        rng = FixedRandom(integer=99999)
        self.assertEqual(
            self.monitor.random_position(400, 200, rng=rng),
            (3440, 780),
        )

    def test_each_corner_keeps_its_margin(self):
        self.assertEqual(self.monitor.corner_position(400, 200, "top-left"),
                         (1944, -76))
        self.assertEqual(self.monitor.corner_position(400, 200, "bottom-right"),
                         (3416, 756))

    def test_oversized_content_is_clamped_to_the_monitor_origin(self):
        self.assertEqual(
            self.monitor.corner_position(3000, 2000, "bottom-right"),
            (1920, -100),
        )

    def test_left_entry_starts_wholly_outside(self):
        start_x, start_y, rest_x, rest_y = self.monitor.edge_entry(
            400, 200, "left", rng=FixedRandom(integer=80))
        self.assertEqual(start_x, 1520)
        self.assertEqual(rest_x, 1920)
        self.assertEqual((start_y, rest_y), (-20, -20))

    def test_unknown_edge_is_rejected(self):
        with self.assertRaises(ValueError):
            self.monitor.edge_entry(100, 100, "diagonal")


class MonitorChoice(unittest.TestCase):
    def setUp(self):
        self.found = [
            geometry.Monitor(0, 0, 100, 100, name="left"),
            geometry.Monitor(100, 0, 100, 100, primary=True, name="right"),
        ]

    def test_primary_policy(self):
        self.assertIs(geometry.pick_monitor(self.found), self.found[1])

    def test_random_policy(self):
        self.assertIs(
            geometry.pick_monitor(self.found, default="random",
                                  rng=FixedRandom(choice=0)),
            self.found[0],
        )

    def test_explicit_choice_wins_over_the_default(self):
        self.assertIs(
            geometry.pick_monitor(self.found, "0", default="primary"),
            self.found[0],
        )

    def test_index_is_clamped(self):
        self.assertIs(geometry.pick_monitor(self.found, 99), self.found[1])

    def test_empty_input_has_a_safe_fallback(self):
        monitor = geometry.pick_monitor([])
        self.assertTrue(monitor.primary)
        self.assertEqual((monitor.width, monitor.height), (1920, 1080))


class AnimationAndAudioGeometry(unittest.TestCase):
    def test_easing_is_bounded(self):
        self.assertEqual(geometry.ease_out(-1), 0.0)
        self.assertEqual(geometry.ease_out(2), 1.0)
        self.assertGreater(geometry.ease_out(0.5), 0.5)

    def test_pan_uses_the_whole_virtual_desktop(self):
        found = [
            geometry.Monitor(-1920, 0, 1920, 1080),
            geometry.Monitor(0, 0, 1920, 1080),
        ]
        self.assertEqual(geometry.pan_for(-1920, found), -1.0)
        self.assertEqual(geometry.pan_for(0, found), 0.0)
        self.assertEqual(geometry.pan_for(1920, found), 1.0)


if __name__ == "__main__":
    unittest.main()
