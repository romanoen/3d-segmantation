"""Evaluate exported novel-scene assignments using held-out generator labels.

Run after segment_e57.py --novel-scene; labels never enter segmentation.
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from novel_scene import novel_scene
from segment_e57 import VoxelAccumulator


def evaluate(result_dir):
    metadata = json.loads((result_dir / "segments.json").read_text(encoding="utf-8"))
    if metadata.get("input") != "synthetic_loading_bay":
        raise ValueError("Das Ergebnis stammt nicht von --novel-scene.")
    seed = metadata["seed"]
    voxel_size = metadata["voxel_size"]
    raw, inventory, _ = novel_scene(seed, metadata["noise_std_m"])
    source_by_voxel = {}
    offset = 0
    for object_id, item in enumerate(inventory):
        for point in raw[offset:offset + item["generated_point_count"]]:
            key = tuple(np.floor(point / voxel_size).astype(np.int64))
            source_by_voxel.setdefault(key, object_id)
        offset += item["generated_point_count"]
    accumulator = VoxelAccumulator(voxel_size)
    accumulator.add(raw)
    points = accumulator.array()
    source = np.array([source_by_voxel[tuple(np.floor(point / voxel_size).astype(np.int64))]
                       for point in points])
    with (result_dir / "assignments.csv").open(newline="", encoding="utf-8") as handle:
        assignments = list(csv.DictReader(handle))
    if len(assignments) != len(points):
        raise ValueError("Punktzahl passt nicht zur erzeugten Szene.")
    exported = np.array([[float(row[axis]) for axis in ("x", "y", "z")]
                         for row in assignments])
    if not np.allclose(exported, points, atol=1e-6):
        raise ValueError("Punkte passen nicht zur erzeugten Szene/Seed/Voxelgröße.")
    labels = np.array([int(row["segment_id"]) for row in assignments])
    types = {item["segment_id"]: item["type"] for item in metadata["segments"]}
    rows = []
    for object_id, item in enumerate(inventory):
        observed = labels[source == object_id]
        counts = np.bincount(observed)
        dominant = int(np.argmax(counts[1:]) + 1) if len(counts) > 1 else 0
        rows.append(dict(object=item["name"], points=len(observed),
                         dominant_segment=dominant,
                         dominant_type=types.get(dominant, "unassigned"),
                         dominant_recall=counts[dominant] / len(observed) if dominant else 0.,
                         dominant_purity=np.mean(source[labels == dominant] == object_id)
                         if dominant else 0.,
                         unassigned_fraction=counts[0] / len(observed),
                         significant_segments=int(np.sum(counts[1:] >= .05 * len(observed)))))
    output = result_dir / "object_metrics.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(f"{row['object']:20} Punkte={row['points']:5} "
              f"größtes Segment={row['dominant_segment']:2} ({row['dominant_type']:8}) "
              f"Recall={row['dominant_recall']:.2f} Reinheit={row['dominant_purity']:.2f} "
              f"unzugeordnet={row['unassigned_fraction']:.2f} "
              f"größere Teilsegmente={row['significant_segments']}")
    print(f"Messwerte: {output}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path, nargs="?", default=Path("novel_scene_output"))
    args = parser.parse_args()
    evaluate(args.result_dir)


if __name__ == "__main__":
    main()
