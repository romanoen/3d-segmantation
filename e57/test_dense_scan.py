"""Fast checks for angular sampling and deterministic first-hit output."""
import unittest

import numpy as np

from scanner_scene import OBJECTS, scanner_scene


class DenseScanTest(unittest.TestCase):
    def test_scanner_output_is_reproducible_and_labeled_only_for_evaluation(self):
        first = scanner_scene(seed=7, angular_step=.006)
        second = scanner_scene(seed=7, angular_step=.006)
        points, source, colors, metadata = first
        np.testing.assert_array_equal(points, second[0])
        np.testing.assert_array_equal(source, second[1])
        self.assertEqual(len(points), len(colors))
        self.assertGreater(len(points), 1000)
        self.assertTrue(np.isfinite(points).all())
        self.assertTrue(np.isfinite(colors).all())
        self.assertTrue(set(np.unique(source)).issubset(set(range(len(OBJECTS)))))
        self.assertEqual(metadata["raw_point_count"], len(points))
        self.assertEqual(metadata["angular_step_mrad"], 6.)


if __name__ == "__main__":
    unittest.main()
