"""Reproducible distance experiment; run with python test_construction_gaps.py.

Scene provenance is used only to evaluate the resulting point labels.
"""
import csv
from pathlib import Path

import numpy as np
import open3d as o3d

from segment_e57 import (VoxelAccumulator, segment_planes, segment_freeform,
                         synthetic_room, synthetic_wall_pair)


def main():
    rows = []
    for gap in (.02, .05, .08, .12, .15, .20):
        for seed in (7, 11, 23):
            left, right = synthetic_wall_pair(seed, .01, gap)
            truth = {tuple(p): 1 for p in left}
            truth.update({tuple(p): 2 for p in right})
            accumulator = VoxelAccumulator(.02)
            accumulator.add(np.vstack((synthetic_room(seed, .01), left, right)))
            points = accumulator.array()
            source = np.array([truth.get(tuple(p), 0) for p in points])
            o3d.utility.random.seed(seed)
            planes = segment_planes(points, .03, 500, .02, 1000, 1.)
            free = segment_freeform(points, planes, .08, 150)
            labels = np.zeros(len(points), dtype=int)
            for segment in free:
                labels[segment.point_indices] = segment.segment_id
            dominant_ids = []
            row = dict(gap_m=gap, seed=seed, noise_m=.01, cluster_distance_m=.08,
                       plane_count=len(planes), freeform_count=len(free))
            for object_id in (1, 2):
                object_labels = labels[source == object_id]
                candidates = object_labels[object_labels > 0]
                dominant = int(np.bincount(candidates).argmax()) if len(candidates) else 0
                dominant_ids.append(dominant)
                row[f'object_{object_id}_segment'] = dominant
                row[f'object_{object_id}_recall'] = float(np.mean(object_labels == dominant)) if dominant else 0.0
                row[f'object_{object_id}_purity'] = float(np.mean(source[labels == dominant] == object_id)) if dominant else 0.0
            row['separate'] = bool(all(dominant_ids) and dominant_ids[0] != dominant_ids[1])
            rows.append(row)
            print(f"Abstand {gap:.2f} m, Seed {seed}: {len(free)} freie Segmente; getrennt={row['separate']}")
    output = Path(__file__).resolve().parent / 'construction_gap_results.csv'
    with output.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Messwerte: {output}")


if __name__ == '__main__':
    main()
