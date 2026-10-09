"""Regression check for the synthetic density experiment."""
import unittest

from evaluate_robustness import evaluate, scene


class RobustnessTest(unittest.TestCase):
    def test_larger_plane_neighbourhood_recovers_thinned_walls(self):
        points, truth = scene(7, "half_density")
        tight = evaluate(points, truth, 7, "half_density", .075)
        wider = evaluate(points, truth, 7, "half_density", .12)
        self.assertEqual({row["wall"] for row in wider}, {1, 2, 3, 4})
        self.assertTrue(all(row["recall_visible"] == 0 for row in tight))
        self.assertTrue(all(row["recall_visible"] > .95 for row in wider))
        self.assertTrue(all(row["purity"] > .97 for row in wider))


if __name__ == "__main__":
    unittest.main()
