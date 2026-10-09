"""Measure plane-instance consistency under thinning and occlusion.

Synthetic source labels are used only for evaluation, never by RANSAC.
Run: python evaluate_robustness.py
"""

import argparse
import csv
from pathlib import Path

import numpy as np
import open3d as o3d

from segment_e57 import ROOM_OPENINGS, VoxelAccumulator, segment_planes


WALLS = ((0, 0, 4), (0, 6, 4), (1, 0, 6), (1, 4, 6))
SCENARIOS = {
    "baseline": (1., 1., 1., 1.),
    "half_density": (.5, .5, .5, .5),
    "uneven_density": (.25, .85, .35, .7),
    "occluded": (1., 1., 1., 1.),
    "combined": (.25, .85, .35, .7),
}
DISTANCES = (.075, .12, .18)


def scene(seed, scenario):
    """Return voxelized points and ground-truth source IDs (0 = outlier)."""
    rng = np.random.default_rng(seed)
    parts = []
    source = []
    for object_id, (axis, position, length) in enumerate(WALLS, start=1):
        along, height = np.meshgrid(np.arange(0, length + .025, .05),
                                    np.arange(0, 2.825, .05))
        u, z = along.ravel(), height.ravel()
        keep = np.ones(len(u), dtype=bool)
        for opening in ROOM_OPENINGS:
            if opening["axis"] == axis and opening["position"] == position:
                keep &= ~((u >= opening["along"][0]) & (u <= opening["along"][1])
                          & (z >= opening["z"][0]) & (z <= opening["z"][1]))
        # Full-height missing strip on wall x=0: a genuine disconnected wall.
        if scenario in ("occluded", "combined") and object_id == 1:
            keep &= ~((u >= 2.8) & (u <= 3.5))
        keep &= rng.random(len(u)) < .9 * SCENARIOS[scenario][object_id - 1]
        xyz = np.zeros((len(u), 3))
        xyz[:, axis] = position
        xyz[:, 1 - axis] = u
        xyz[:, 2] = z
        xyz += rng.normal(0, .01, xyz.shape)
        xyz = xyz[keep]
        parts.append(xyz)
        source.extend([object_id] * len(xyz))
    outliers = rng.uniform([-.5, -.5, -.3], [6.5, 4.5, 3.1], (800, 3))
    parts.append(outliers)
    source.extend([0] * len(outliers))
    raw = np.vstack(parts)
    # VoxelAccumulator retains the first input point per voxel; coordinates
    # identify that representative and hence its unambiguous source label.
    truth = {tuple(point): label for point, label in zip(raw, source)}
    accumulator = VoxelAccumulator(.02)
    accumulator.add(raw)
    points = accumulator.array()
    return points, np.array([truth[tuple(point)] for point in points])


def evaluate(points, truth, seed, scenario, plane_cluster_distance):
    o3d.utility.random.seed(seed)
    planes = segment_planes(points, .03, 500, .02, 1000, min_plane_width=1.,
                            component_distance=plane_cluster_distance)
    predictions = np.zeros(len(points), dtype=int)
    for segment in planes:
        predictions[segment.point_indices] = segment.segment_id
    rows = []
    for object_id in range(1, 5):
        matching = predictions[truth == object_id]
        counts = np.bincount(matching, minlength=len(planes) + 1)
        dominant = int(np.argmax(counts[1:]) + 1) if len(planes) else 0
        captured = int(counts[dominant]) if dominant else 0
        rows.append(dict(seed=seed, scenario=scenario,
                         plane_cluster_distance_m=plane_cluster_distance, wall=object_id,
                         visible_points=len(matching), plane_count=len(planes),
                         dominant_segment=dominant,
                         recall_visible=captured / len(matching) if len(matching) else 0.,
                         purity=np.mean(truth[predictions == dominant] == object_id)
                         if dominant else 0.,
                         unassigned_fraction=counts[0] / len(matching) if len(matching) else 0.,
                         significant_fragments=int(np.sum(counts[1:] >= .05 * len(matching)))))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("robustness_results.csv"))
    args = parser.parse_args()
    rows = []
    for seed in (7, 11, 23):
        for scenario in SCENARIOS:
            points, truth = scene(seed, scenario)
            for distance in DISTANCES:
                rows.extend(evaluate(points, truth, seed, scenario, distance))
    baselines = {(row["seed"], row["wall"]): row["visible_points"]
                 for row in rows if row["scenario"] == "baseline"}
    for row in rows:
        row["visible_vs_baseline"] = row["visible_points"] / baselines[row["seed"], row["wall"]]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for scenario in SCENARIOS:
        for distance in DISTANCES:
            group = [row for row in rows if row["scenario"] == scenario
                     and row["plane_cluster_distance_m"] == distance]
            print(f"{scenario:16} eps={distance:.3f} "
                  f"recall={np.mean([r['recall_visible'] for r in group]):.3f} "
                  f"purity={np.mean([r['purity'] for r in group]):.3f} "
                  f"visible={np.mean([r['visible_vs_baseline'] for r in group]):.3f} "
                  f"unassigned={np.mean([r['unassigned_fraction'] for r in group]):.3f} "
                  f"detected={sum(r['recall_visible'] >= .5 and r['purity'] >= .9 for r in group)}/{len(group)} "
                  f"fragmented={sum(r['significant_fragments'] > 1 for r in group)}/{len(group)}")
    print(f"Einzelmessungen: {args.output}")


if __name__ == "__main__":
    main()
