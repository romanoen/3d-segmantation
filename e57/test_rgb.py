import tempfile
import unittest
from pathlib import Path

import numpy as np
import pye57

from segment_e57 import (VoxelAccumulator, read_e57_stream, segment_freeform,
                         segment_planes, synthetic_room, synthetic_wall_pair)
from rgb_utils import surface_colors


class RGBTest(unittest.TestCase):
    def test_scaffold_not_removed_as_wall(self):
        import open3d as o3d
        from construction_site import site_details
        details, inventory, rgb = site_details(7, .01, with_colors=True)
        scaffold = set()
        offset = 0
        for item in inventory:
            count = item['generated_point_count']
            if item['name'].startswith('scaffold'):
                scaffold.update(tuple(p) for p in details[offset:offset+count])
            offset += count
        room = synthetic_room(7, .01, True)
        left, right = synthetic_wall_pair(7, .01, .05)
        acc = VoxelAccumulator(.02)
        acc.add(np.vstack((room, details, left, right)),
                np.vstack((surface_colors(room,[.75,.73,.69]), rgb,
                           surface_colors(left,[.8,.16,.08]), surface_colors(right,[.08,.25,.8],8))))
        points, colors = acc.array(), acc.colors()
        truth = np.array([tuple(p) in scaffold for p in points])
        o3d.utility.random.seed(7)
        planes = segment_planes(points,.03,500,.02,1000,1.)
        free = segment_freeform(points,planes,.08,150,colors,.18)
        plane_indices = np.concatenate([s.point_indices for s in planes])
        self.assertLess(truth[plane_indices].sum()/truth.sum(), .01)
        self.assertGreater(max(truth[s.point_indices].sum() for s in free)/truth.sum(), .99)
        self.assertTrue(all(s.plane_coverage >= .55 for s in planes))

    def test_construction_site_walls_remain_whole(self):
        import open3d as o3d
        from construction_site import site_details
        room = synthetic_room(7, .01, True)
        details, _, _ = site_details(7, .01, with_colors=True)
        left, right = synthetic_wall_pair(7, .01, .05)
        acc = VoxelAccumulator(.02)
        acc.add(np.vstack((room, details, left, right)))
        points = acc.array()
        o3d.utility.random.seed(7)
        planes = segment_planes(points, .03, 500, .02, 1000, 1.)
        # Four walls plus one horizontal construction surface. This guards
        # against splitting a wall into multiple RANSAC hypotheses.
        self.assertEqual(len(planes), 5)
        walls = [segment for segment in planes if abs(segment.plane[2]) < .1]
        self.assertEqual(len(walls), 4)
        self.assertTrue(all(len(segment.point_indices) > 3000 for segment in walls))
        indices = np.concatenate([segment.point_indices for segment in planes])
        self.assertEqual(len(indices), len(np.unique(indices)))

    def test_color_preserves_voxel_representative(self):
        acc = VoxelAccumulator(1)
        acc.add(np.array([[.1, 0, 0], [.2, 0, 0], [2, 0, 0]]),
                np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]]))
        np.testing.assert_allclose(acc.array(), [[.1, 0, 0], [2, 0, 0]])
        np.testing.assert_allclose(acc.colors(), [[1, 0, 0], [0, 0, 1]])

    def test_colored_e57_chunks_transform_filter_crop(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'color.e57'
            n = 12
            data = dict(cartesianX=np.arange(n, dtype=float),
                        cartesianY=np.zeros(n), cartesianZ=np.zeros(n),
                        colorRed=np.arange(n, dtype=np.uint8)*10,
                        colorGreen=np.full(n, 100, dtype=np.uint8),
                        colorBlue=np.full(n, 200, dtype=np.uint8),
                        cartesianInvalidState=np.zeros(n, dtype=np.int8))
            data['cartesianInvalidState'][5] = 1
            with pye57.E57(str(path), mode='w') as f:
                f.write_scan_raw(data, translation=np.array([10., 2., 3.]))
            points, meta, colors = read_e57_stream(path, 0, np.array([13,1,2,18,3,4]), .1, 3)
            expected = np.array([3,4,6,7,8])
            np.testing.assert_allclose(points[:, 0], expected+10)
            np.testing.assert_allclose(points[:, 1:], np.tile([2,3], (5,1)))
            np.testing.assert_allclose(colors[:, 0], expected*10/255)
            np.testing.assert_allclose(colors[:, 1:], np.tile([100/255,200/255], (5,1)))
            self.assertTrue(meta['rgb_available'])
            self.assertEqual(meta['read_point_count'], n)
            plain = Path(directory) / 'plain.e57'
            with pye57.E57(str(plain), mode='w') as f:
                f.write_scan_raw({k:v for k,v in data.items() if not k.startswith('color')})
            _, meta, colors = read_e57_stream(plain, 0, None, .1, 3)
            self.assertFalse(meta['rgb_available'])
            self.assertIsNone(colors)

    def test_rgb_separation_and_same_color_control(self):
        x,z = np.meshgrid(np.linspace(0,.2,15), np.linspace(0,.5,30))
        left = np.column_stack((x.ravel(), np.zeros(x.size), z.ravel()))
        right = left + [.25,0,0]
        points = np.vstack((left,right))
        colors = np.vstack((surface_colors(left,[.8,.1,.1]),surface_colors(right,[.1,.2,.8])))
        self.assertEqual(len(segment_freeform(points, [], .08, 50)), 1)
        segments = segment_freeform(points, [], .08, 50, colors, .18)
        self.assertEqual(len(segments), 2)
        self.assertEqual(set(segments[0].point_indices), set(range(len(left))))
        same = surface_colors(points,[.5,.5,.5])
        self.assertEqual(len(segment_freeform(points, [], .08, 50, same, .18)), 1)
        self.assertEqual(len(segment_freeform(points, [], .08, 50, np.full_like(colors,np.nan), .18)), 0)


if __name__ == '__main__':
    unittest.main()
