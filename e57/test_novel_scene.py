"""Checks that the new scene is reproducible and tests actual segmentation."""
import unittest

import numpy as np
import open3d as o3d

from novel_scene import novel_scene
from segment_e57 import VoxelAccumulator, segment_freeform, segment_planes


class NovelSceneTest(unittest.TestCase):
    def test_generator_and_pipeline(self):
        raw, inventory, colors = novel_scene(7, .01)
        again, again_inventory, again_colors = novel_scene(7, .01)
        np.testing.assert_array_equal(raw, again)
        np.testing.assert_array_equal(colors, again_colors)
        self.assertEqual(inventory, again_inventory)
        self.assertEqual(sum(item["generated_point_count"] for item in inventory), len(raw))
        self.assertEqual(colors.shape, raw.shape)
        self.assertEqual({item["name"] for item in inventory},
                         {"ground_slab", "loading_ramp", "control_kiosk",
                          "ellipsoid_housing", "staircase", "folded_canopy", "outliers"})
        acc = VoxelAccumulator(.03)
        acc.add(raw, colors)
        points = acc.array()
        o3d.utility.random.seed(7)
        planes = segment_planes(points, .03, 300, .03, 1000, min_plane_width=1.,
                                component_distance=.12)
        free = segment_freeform(points, planes, .12, 100)
        self.assertGreaterEqual(len(planes), 2)
        self.assertGreaterEqual(len(free), 3)
        assigned = np.concatenate([item.point_indices for item in planes + free])
        self.assertEqual(len(assigned), len(np.unique(assigned)))


if __name__ == "__main__":
    unittest.main()
