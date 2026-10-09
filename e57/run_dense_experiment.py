"""Compare one angular loading-bay scan at 5, 10 and 20 mm voxels.

Source IDs are retained only for evaluation. The segmentation receives XYZ.
"""

import argparse
import csv
from pathlib import Path

import numpy as np
import open3d as o3d

from scanner_scene import OBJECTS, scanner_scene
from segment_e57 import (VoxelAccumulator, save_results, segment_freeform,
                         segment_planes, visualize)


def run(output_dir, seed=7, show_voxel_mm=None):
    raw, source, rgb, scan_metadata = scanner_scene(seed)
    print(f"Simulierter Einzelstandpunkt: {len(raw):,} sichtbare Rohpunkte")
    rows = []
    for voxel in (.005, .01, .02):
        accumulator = VoxelAccumulator(voxel)
        accumulator.add(raw, rgb)
        points, colors = accumulator.array(), accumulator.colors()
        # Same first-point-per-voxel rule as the production E57 reader.
        first_source = {}
        for point, object_id in zip(raw, source):
            key = tuple(np.floor(point / voxel).astype(np.int64))
            first_source.setdefault(key, object_id)
        truth = np.array([first_source[tuple(np.floor(point / voxel).astype(np.int64))]
                          for point in points])
        o3d.utility.random.seed(seed)
        planes = segment_planes(points, .008, 300, voxel, 1000,
                                min_plane_width=1., component_distance=.04)
        free = segment_freeform(points, planes, .06, 100)
        segments = planes + free
        labels = np.zeros(len(points), dtype=int)
        for segment in segments:
            labels[segment.point_indices] = segment.segment_id
        destination = output_dir / f"voxel_{int(voxel * 1000):03d}mm"
        metadata = {**scan_metadata, "input": "synthetic_angular_loading_bay",
                    "seed": seed, "voxel_size": voxel, "voxel_point_count": len(points),
                    "distance_tolerance": .008, "plane_cluster_distance": .04,
                    "freeform_cluster_distance": .06,
                    "ground_truth_used_for_detection": False}
        save_results(points, segments, metadata, destination, colors)
        for object_id, name in enumerate(OBJECTS):
            object_mask = truth == object_id
            observed = labels[object_mask]
            object_cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points[object_mask]))
            neighbours = np.asarray(object_cloud.compute_nearest_neighbor_distance())
            counts = np.bincount(observed, minlength=len(segments) + 1)
            dominant = int(np.argmax(counts[1:]) + 1) if len(segments) else 0
            segment = segments[dominant - 1] if dominant else None
            dominant_type = ("plane" if segment.plane is not None else "freeform") if segment else "unassigned"
            rows.append(dict(voxel_mm=int(voxel * 1000), object=name,
                             visible_points=len(observed), processed_points=len(points),
                             median_neighbour_mm=float(np.median(neighbours) * 1000),
                             p90_neighbour_mm=float(np.percentile(neighbours, 90) * 1000),
                             plane_count=len(planes), freeform_count=len(free),
                             dominant_segment=dominant,
                             dominant_type=dominant_type,
                             dominant_recall=counts[dominant] / len(observed) if dominant and len(observed) else 0.,
                             dominant_purity=np.mean(truth[labels == dominant] == object_id)
                             if dominant else 0.,
                             unassigned_fraction=counts[0] / len(observed) if len(observed) else 0.))
        print(f"{int(voxel * 1000):2d} mm: {len(points):,} Punkte; "
              f"{len(planes)} Ebenen, {len(free)} freie Segmente; {destination}")
        if show_voxel_mm == int(voxel * 1000):
            visualize(points, segments, colors)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "density_metrics.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Messwerte: {path}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("dense_scan_output"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--show", type=int, choices=(5, 10, 20),
                        help="Gewählte Voxel-Szene in Open3D anzeigen")
    args = parser.parse_args()
    run(args.output_dir, args.seed, args.show)


if __name__ == "__main__":
    main()
