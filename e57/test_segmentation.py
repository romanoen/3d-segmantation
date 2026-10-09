"""Geometric checks for the optional vertical-cylinder pipeline."""
import unittest

import numpy as np
import open3d as o3d

from segment_e57 import (PIPE_GROUPS, VoxelAccumulator, segment_planes,
                         segment_vertical_cylinders, synthetic_room,
                         synthetic_wall_construction, segment_freeform)


class FreeformTest(unittest.TestCase):
    def test_attached_construction_is_preserved(self):
        for seed in (7, 11, 23):
            with self.subTest(seed=seed):
                room = synthetic_room(seed, .01)
                construction = synthetic_wall_construction(seed, .01)
                # Ground truth is used ONLY for evaluation, never detection.
                truth = {tuple(p) for p in construction}
                acc = VoxelAccumulator(.02)
                acc.add(np.vstack((room, construction)))
                points = acc.array()
                target = np.array([tuple(p) in truth for p in points])
                o3d.utility.random.seed(seed)
                planes = segment_planes(points, .03, 500, .02, 1000, 1.)
                free = segment_freeform(points, planes, .08, 150)
                self.assertEqual(len(planes), 4)
                self.assertEqual(len(free), 1)
                indices = free[0].point_indices
                self.assertGreater(target[indices].sum() / target.sum(), .9)
                self.assertGreater(target[indices].mean(), .98)
                assigned = np.concatenate([s.point_indices for s in planes + free])
                self.assertEqual(len(assigned), len(np.unique(assigned)))
                self.assertIsNone(free[0].plane)
                self.assertIsNone(free[0].rmse)


class CylinderPipelineTest(unittest.TestCase):
    def pipeline(self, seed, installations, translation=(0, 0, 0)):
        accumulator = VoxelAccumulator(0.02)
        accumulator.add(synthetic_room(seed, 0.01, installations) + translation)
        points = accumulator.array()
        o3d.utility.random.seed(seed)
        planes = segment_planes(points, 0.03, 500, 0.02, 1000, min_plane_width=1.0)
        cylinders = segment_vertical_cylinders(points, planes, seed=seed)
        self.assertEqual(len(planes), 4)
        indices = np.concatenate([s.point_indices for s in planes + cylinders])
        self.assertEqual(len(indices), len(np.unique(indices)))
        for segment in cylinders:
            model = segment.cylinder
            errors = np.abs(np.linalg.norm(points[segment.point_indices, :2]
                                           - model['axis_point'][:2], axis=1) - model['radius'])
            self.assertLessEqual(errors.max(), 0.020001)
            self.assertAlmostEqual(segment.rmse, np.sqrt(np.mean(errors**2)))
        return cylinders

    def test_six_separate_pipes_and_translation(self):
        for seed, translation in [(7, (0, 0, 0)), (11, (12, -8, 3))]:
            with self.subTest(seed=seed):
                cylinders = self.pipeline(seed, True, translation)
                self.assertEqual(len(cylinders), 6)
                centers = np.array([s.cylinder['axis_point'][:2] for s in cylinders])
                expected = np.array(PIPE_GROUPS).reshape(-1, 2) + np.array(translation[:2])
                nearest = np.argmin(np.linalg.norm(expected[:, None] - centers[None], axis=2), axis=1)
                self.assertEqual(len(set(nearest)), 6)
                self.assertLess(np.linalg.norm(expected - centers[nearest], axis=1).max(), 0.015)
                for segment in cylinders:
                    self.assertLess(abs(segment.cylinder['radius'] - 0.06), 0.005)
                    self.assertLess(segment.rmse, 0.015)

    def test_room_without_pipes(self):
        self.assertEqual(len(self.pipeline(23, False)), 0)


if __name__ == '__main__':
    unittest.main()
