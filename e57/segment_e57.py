#!/usr/bin/env python3
"""Small E57 plane-segmentation prototype.

The E57 reader uses pye57's low-level compressed-vector reader.  Therefore
only one block of points is held while the file is read.  The points that
survive the crop are reduced to one representative per voxel before Open3D
is used for RANSAC segmentation.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


@dataclass
class Segment:
    segment_id: int
    point_indices: np.ndarray
    plane: np.ndarray | None
    rmse: float | None
    mean_absolute_error: float | None
    cylinder: dict | None = None
    freeform: dict | None = None
    plane_coverage: float | None = None


class VoxelAccumulator:
    """Keep one point per voxel, so raw point count does not determine memory."""

    def __init__(self, voxel_size: float) -> None:
        self.voxel_size = voxel_size
        self._points: dict[tuple[int, int, int], np.ndarray] = {}
        self._colors = {}

    def add(self, points: np.ndarray, colors=None) -> None:
        if len(points) == 0:
            return
        keys = np.floor(points / self.voxel_size).astype(np.int64)
        for i, (key, point) in enumerate(zip(keys, points)):
            key = tuple(key)
            if key not in self._points:
                self._points[key] = point.astype(np.float64, copy=True)
                if colors is not None:
                    self._colors[key] = np.asarray(colors[i]).copy()

    def colors(self):
        if not self._colors:
            return None
        return np.array([self._colors.get(key, [np.nan]*3) for key in self._points])

    def array(self) -> np.ndarray:
        if not self._points:
            return np.empty((0, 3), dtype=np.float64)
        return np.asarray(list(self._points.values()), dtype=np.float64)


def print_e57_metadata(e57, selected_scan: int) -> None:
    """Print scan count, point fields, scan fields and pose information."""
    print(f"Scans: {e57.scan_count}")
    for index in range(e57.scan_count):
        header = e57.get_header(index)
        marker = "  < ausgewählt" if index == selected_scan else ""
        print(
            f"  Scan {index}: {header.point_count:,} Punkte; "
            f"Punktattribute={header.point_fields}; "
            f"Scanattribute={header.scan_fields}{marker}"
        )
        print(f"    Translation: {np.asarray(header.translation)}")
        print(f"    Rotation (Matrix): {np.asarray(header.rotation_matrix).tolist()}")


def _transform(points: np.ndarray, rotation: np.ndarray, translation: np.ndarray) -> np.ndarray:
    # This is the same convention used by pye57.to_global().
    return (rotation @ points.T + translation.reshape(3, 1)).T


def _spherical_to_cartesian(values: np.ndarray) -> np.ndarray:
    radius, azimuth, elevation = values.T
    cos_elevation = np.cos(elevation)
    return np.column_stack(
        (
            radius * cos_elevation * np.cos(azimuth),
            radius * cos_elevation * np.sin(azimuth),
            radius * np.sin(elevation),
        )
    )


def read_e57_stream(
    path: Path,
    scan_index: int,
    bbox: np.ndarray | None,
    voxel_size: float,
    chunk_size: int,
) -> tuple[np.ndarray, dict, np.ndarray | None]:
    """Read one scan in chunks and return the cropped, voxelized point set."""
    try:
        import pye57
    except ImportError as exc:
        raise RuntimeError("pye57 fehlt. Installiere zuerst requirements.txt.") from exc

    e57 = pye57.E57(str(path))
    try:
        if not 0 <= scan_index < e57.scan_count:
            raise ValueError(f"--scan-index muss zwischen 0 und {e57.scan_count - 1} liegen.")

        print_e57_metadata(e57, scan_index)
        header = e57.get_header(scan_index)
        if all(name in header.point_fields for name in ("cartesianX", "cartesianY", "cartesianZ")):
            coordinate_fields = ["cartesianX", "cartesianY", "cartesianZ"]
            invalid_field = "cartesianInvalidState"
            spherical = False
        elif all(name in header.point_fields for name in ("sphericalRange", "sphericalAzimuth", "sphericalElevation")):
            coordinate_fields = ["sphericalRange", "sphericalAzimuth", "sphericalElevation"]
            invalid_field = "sphericalInvalidState"
            spherical = True
        else:
            raise ValueError("Der Scan enthält weder vollständige kartesische noch sphärische Koordinaten.")

        # read_scan() would allocate arrays for the whole scan.  make_buffers()
        # plus reader.read() keeps this prototype bounded by chunk_size.
        fields = coordinate_fields + ([invalid_field] if invalid_field in header.point_fields else [])
        arrays, buffers = e57.make_buffers(fields, chunk_size)
        rgb_fields = ["colorRed", "colorGreen", "colorBlue"]
        has_rgb = all(field in header.point_fields for field in rgb_fields)
        limits = []
        if has_rgb:
            # Float buffers avoid the uint8 limitation for higher-range E57 RGB.
            for field in rgb_fields:
                arrays[field] = np.empty(chunk_size, dtype=np.float64)
                buffers.append(pye57.libe57.SourceDestBuffer(e57.image_file, field, arrays[field], chunk_size, True, True))
                lo, hi = 0, 255
                if header.node.isDefined("colorLimits"):
                    node = header["colorLimits"]
                    if node.isDefined(field + "Minimum") and node.isDefined(field + "Maximum"):
                        lo, hi = node[field + "Minimum"].value(), node[field + "Maximum"].value()
                limits.append((lo, hi))
            if "isColorInvalid" in header.point_fields:
                arrays["isColorInvalid"] = np.empty(chunk_size, dtype=np.int8)
                buffers.append(pye57.libe57.SourceDestBuffer(e57.image_file, "isColorInvalid",
                               arrays["isColorInvalid"], chunk_size, True, True))
        reader = header.points.reader(buffers)
        accumulator = VoxelAccumulator(voxel_size)
        rotation = np.asarray(header.rotation_matrix, dtype=np.float64)
        translation = np.asarray(header.translation, dtype=np.float64)
        selected_count = 0
        read_count = 0

        try:
            while read_count < header.point_count:
                count = reader.read()
                if count is None:
                    count = min(chunk_size, header.point_count - read_count)
                if count <= 0:
                    break
                raw = np.column_stack([arrays[field][:count] for field in coordinate_fields])
                read_count += count
                rgb = None
                if has_rgb:
                    rgb = np.column_stack([arrays[field][:count] for field in rgb_fields])
                    bounds = np.asarray(limits)
                    rgb = np.clip((rgb - bounds[:, 0]) / np.maximum(bounds[:, 1] - bounds[:, 0], 1), 0, 1)
                    if "isColorInvalid" in arrays:
                        rgb[arrays["isColorInvalid"][:count] != 0] = np.nan
                keep = np.isfinite(raw).all(axis=1)
                if invalid_field in arrays:
                    keep &= arrays[invalid_field][:count] == 0
                raw = raw[keep]
                if rgb is not None:
                    rgb = rgb[keep]
                if spherical:
                    raw = _spherical_to_cartesian(raw)
                raw = _transform(raw, rotation, translation)

                if bbox is not None and len(raw):
                    keep = (
                        np.all(raw >= bbox[:3], axis=1)
                        & np.all(raw <= bbox[3:], axis=1)
                    )
                    raw = raw[keep]
                    if rgb is not None:
                        rgb = rgb[keep]
                selected_count += len(raw)
                accumulator.add(raw, rgb)
        finally:
            reader.close()

        points = accumulator.array()
        print(f"Gelesen: {read_count:,}; im Ausschnitt: {selected_count:,}; nach Voxel: {len(points):,}")
        metadata = {
            "input": str(path),
            "scan_index": scan_index,
            "raw_point_count": int(header.point_count),
            "read_point_count": int(read_count),
            "cropped_point_count": int(selected_count),
            "voxel_point_count": int(len(points)),
            "point_fields": list(header.point_fields),
            "rotation_matrix": rotation.tolist(),
            "translation": translation.tolist(),
            "transformation_applied_once": True,
            "rgb_available": has_rgb,
            "rgb_normalization_limits": limits,
        }
        return points, metadata, accumulator.colors()
    finally:
        e57.close()


def synthetic_scene(seed: int = 7) -> np.ndarray:
    """Create two disconnected patches of one plane, another plane and outliers."""
    rng = np.random.default_rng(seed)

    def grid(x0: float, x1: float, y0: float, y1: float, z: float) -> np.ndarray:
        x, y = np.meshgrid(np.arange(x0, x1, 0.05), np.arange(y0, y1, 0.05))
        points = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, z)))
        points[:, 2] += rng.normal(0, 0.006, len(points))
        return points

    horizontal_a = grid(0, 2, 0, 2, 0)
    horizontal_b = grid(5, 7, 0, 2, 0)  # same plane, intentionally disconnected
    y, z = np.meshgrid(np.arange(-3, -1, 0.05), np.arange(0, 2, 0.05))
    vertical = np.column_stack((np.zeros(y.size), y.ravel(), z.ravel()))
    vertical[:, 0] += rng.normal(0, 0.006, len(vertical))
    outliers = rng.uniform([-1, -3, -1], [8, 3, 3], size=(150, 3))
    return np.vstack((horizontal_a, horizontal_b, vertical, outliers))


# Opening bounds: distance along wall and height, before measurement noise.
ROOM_OPENINGS = [
    {"kind": "door", "axis": 1, "position": 0, "along": [1.0, 1.9], "z": [0, 2.1]},
    {"kind": "door", "axis": 0, "position": 6, "along": [1.4, 2.3], "z": [0, 2.1]},
    {"kind": "window", "axis": 1, "position": 4, "along": [1.0, 2.2], "z": [1.0, 2.2]},
    {"kind": "window", "axis": 0, "position": 0, "along": [1.4, 2.6], "z": [1.0, 2.2]},
]
PIPE_GROUPS = [
    [[3.0, 0.4], [3.18, 0.4], [3.36, 0.4]],
    [[5.6, 2.9], [5.6, 3.08], [5.6, 3.26]],
]


def synthetic_room(seed: int = 7, noise: float = 0.015,
                   installations: bool = False) -> np.ndarray:
    """Four walls of a 6 x 4 x 2.8 m room, without floor or ceiling."""
    rng = np.random.default_rng(seed)
    walls = []
    for axis, position, length in [(0, 0, 4), (0, 6, 4), (1, 0, 6), (1, 4, 6)]:
        along, height = np.meshgrid(np.arange(0, length + 0.025, 0.05),
                                   np.arange(0, 2.825, 0.05))
        wall = np.zeros((along.size, 3))
        wall[:, axis] = position
        wall[:, 1 - axis] = along.ravel()
        wall[:, 2] = height.ravel()
        if installations:
            for opening in ROOM_OPENINGS:
                if opening["axis"] == axis and opening["position"] == position:
                    u = wall[:, 1 - axis]
                    z = wall[:, 2]
                    inside = ((u >= opening["along"][0]) & (u <= opening["along"][1])
                              & (z >= opening["z"][0]) & (z <= opening["z"][1]))
                    wall = wall[~inside]
        wall += rng.normal(0, noise, wall.shape)
        walls.append(wall[rng.random(len(wall)) > 0.1])
    if installations:
        # Sample cylindrical surfaces, not solid cylinders or planar strips.
        theta, z = np.meshgrid(np.linspace(0, 2 * np.pi, 24, endpoint=False),
                               np.linspace(0, 2.8, 113))
        for group in PIPE_GROUPS:
            for x, y in group:
                pipe = np.column_stack((x + 0.06 * np.cos(theta.ravel()),
                                        y + 0.06 * np.sin(theta.ravel()), z.ravel()))
                pipe += rng.normal(0, noise, pipe.shape)
                walls.append(pipe[rng.random(len(pipe)) > 0.1])
    outliers = rng.uniform([-0.5, -0.5, -0.3], [6.5, 4.5, 3.1], (800, 3))
    return np.vstack([*walls, outliers])


def synthetic_wall_construction(seed=7, noise=0.01):
    """Small plate, two wall-mounted braces and a bent, variable-radius tube.

    Touches the y=4 wall; dimensions remain below the large-plane threshold.
    This function only generates input, never supplies segmentation labels.
    """
    rng = np.random.default_rng(seed + 100)
    x, z = np.meshgrid(np.linspace(3.0, 3.8, 41), np.linspace(1.2, 1.8, 31))
    plate = np.column_stack((x.ravel(), np.full(x.size, 3.65), z.ravel()))

    def sweep(centers, radii):
        tangent = np.gradient(centers, axis=0)
        tangent /= np.linalg.norm(tangent, axis=1)[:, None]
        side = np.cross(tangent, [1, 0, 0])
        side /= np.linalg.norm(side, axis=1)[:, None]
        other = np.cross(tangent, side)
        angles = np.linspace(0, 2 * np.pi, 20, endpoint=False)
        offsets = (np.cos(angles)[None, :, None] * side[:, None, :]
                   + np.sin(angles)[None, :, None] * other[:, None, :])
        return (centers[:, None, :] + np.asarray(radii)[:, None, None] * offsets).reshape(-1, 3)

    pieces = [plate]
    t = np.linspace(0, 1, 40)
    for x_pos in (3.08, 3.72):
        centers = np.column_stack((np.full(len(t), x_pos), 4 - .35 * t, 1.0 + .3 * t))
        pieces.append(sweep(centers, np.full(len(t), .04)))
    t = np.linspace(0, np.pi, 100)
    centers = np.column_stack((3.4 + .4 * np.cos(t), 3.65 - .3 * np.sin(t),
                               1.75 + .4 * np.sin(t)))
    pieces.append(sweep(centers, .04 + .012 * np.sin(3 * t)))
    points = np.vstack(pieces)
    points += rng.normal(0, noise, points.shape)
    return points[rng.random(len(points)) > .1]


def synthetic_wall_pair(seed=7, noise=0.01, gap=0.15):
    """Two independently noisy constructions; gap between noiseless X bounds.

    Bounds define placement only. They are never passed to segmentation.
    """
    left = synthetic_wall_construction(seed, noise)
    right = synthetic_wall_construction(seed + 1, noise)
    clean_left = synthetic_wall_construction(seed, 0)
    clean_right = synthetic_wall_construction(seed + 1, 0)
    left[:, 0] += 3.4 - gap / 2 - clean_left[:, 0].max()
    right[:, 0] += 3.4 + gap / 2 - clean_right[:, 0].min()
    return left, right


def segment_freeform(points, assigned, eps=0.08, min_points=150, colors=None, color_distance=0.18):
    """Group residual points without assuming a primitive geometry."""
    import open3d as o3d

    available = np.ones(len(points), dtype=bool)
    for segment in assigned:
        available[segment.point_indices] = False
    remaining = np.flatnonzero(available)
    if len(remaining) < min_points:
        return []
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points[remaining]))
    if colors is None:
        labels = np.asarray(cloud.cluster_dbscan(eps=eps, min_points=5, print_progress=False))
    else:
        from rgb_utils import color_dbscan
        labels = color_dbscan(cloud, colors[remaining], eps, color_distance)
    result = []
    for label in np.unique(labels):
        if label < 0:
            continue
        indices = remaining[labels == label]
        if len(indices) < min_points:
            continue
        xyz = points[indices]
        result.append(Segment(len(assigned) + len(result) + 1, indices, None, None, None,
                              freeform={"bbox_min": xyz.min(axis=0).tolist(),
                                        "bbox_max": xyz.max(axis=0).tolist(),
                                        "centroid": xyz.mean(axis=0).tolist()}))
    return result


def plane_surface_coverage(points, cell_size=0.12):
    """Occupied fraction of a robust 2D bounding grid in the PCA plane.

    Trim 2% at each edge to limit the influence of isolated outliers. A wall
    with openings can still fill most cells; sparse coplanar bars usually don't.
    This is a scale-dependent heuristic, not a semantic wall classifier.
    """
    centered = points - points.mean(axis=0)
    _, _, basis = np.linalg.svd(centered, full_matrices=False)
    uv = centered @ basis[:2].T
    low, high = np.percentile(uv, [2, 98], axis=0)
    uv = uv[np.all((uv >= low) & (uv <= high), axis=1)]
    if not len(uv) or np.any(high - low < 1e-9):
        return 0.0
    shape = np.maximum(1, np.ceil((high - low) / cell_size).astype(np.int64))
    cells = np.minimum(np.floor((uv - low) / cell_size).astype(np.int64), shape - 1)
    return float(len(np.unique(cells, axis=0)) / (int(shape[0]) * int(shape[1])))


def segment_planes(
    points: np.ndarray,
    distance_tolerance: float,
    min_segment_size: int,
    voxel_size: float,
    max_iterations: int,
    min_plane_width: float = 0.0,
    min_plane_coverage: float = 0.55,
    coverage_cell_size: float = 0.12,
    component_distance: float | None = None,
) -> list[Segment]:
    """Iteratively fit planes and split each plane into spatial components."""
    try:
        import open3d as o3d
    except ImportError as exc:
        raise RuntimeError("open3d fehlt. Installiere zuerst requirements.txt.") from exc

    available = np.arange(len(points), dtype=np.int64)
    # Rejected hypotheses must not be sampled forever, but their points may
    # still belong to a different (valid) plane.
    seeds = available.copy()
    segments: list[Segment] = []
    if component_distance is None:
        component_distance = max(2.5 * voxel_size, 2.5 * distance_tolerance)
    if not np.isfinite(component_distance) or component_distance <= 0:
        raise ValueError("component_distance muss positiv und endlich sein.")

    while len(seeds) >= min_segment_size:
        cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points[seeds]))
        model, inliers = cloud.segment_plane(
            distance_threshold=distance_tolerance,
            ransac_n=3,
            num_iterations=max_iterations,
        )
        inlier_indices = np.asarray(inliers, dtype=np.int64)
        if len(inlier_indices) < min_segment_size:
            break

        normal = np.asarray(model[:3], dtype=np.float64)
        normal_length = np.linalg.norm(normal)
        if normal_length == 0:
            break
        plane = np.asarray([*normal / normal_length, model[3] / normal_length])
        # Score a new hypothesis against *all* unassigned points, not only
        # against the reduced RANSAC seed set.
        candidate = available[np.abs(points[available] @ plane[:3] + plane[3]) <= distance_tolerance]
        inlier_cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points[candidate]))
        labels = np.asarray(
            inlier_cloud.cluster_dbscan(
                eps=component_distance,
                # DBSCAN's density threshold is separate from the desired
                # component size.  A large min_segment_size would otherwise
                # reject normal scan grids whose local neighbourhood is small.
                min_points=3,
                print_progress=False,
            )
        )
        accepted = []

        for label in sorted(set(labels.tolist())):
            if label < 0:
                continue
            component_inlier_positions = np.flatnonzero(labels == label)
            if len(component_inlier_positions) < min_segment_size:
                continue
            global_indices = candidate[component_inlier_positions]
            if min_plane_width > 0:
                xyz = points[global_indices]
                centered = xyz - xyz.mean(axis=0)
                _, _, basis = np.linalg.svd(centered, full_matrices=False)
                extent = np.diff(np.percentile(centered @ basis[:2].T, [2, 98], axis=0), axis=0)[0]
                if min(extent) < min_plane_width:
                    continue
            coverage = plane_surface_coverage(points[global_indices], coverage_cell_size)
            if coverage < min_plane_coverage:
                continue
            errors = np.abs(points[global_indices] @ plane[:3] + plane[3])
            segment_id = len(segments) + 1
            segments.append(
                Segment(
                    segment_id=segment_id,
                    point_indices=global_indices,
                    plane=plane,
                    rmse=float(np.sqrt(np.mean(errors**2))),
                    mean_absolute_error=float(np.mean(errors)),
                    plane_coverage=coverage,
                )
            )
            accepted.append(global_indices)

        if accepted:
            accepted_indices = np.concatenate(accepted)
            available = available[~np.isin(available, accepted_indices)]
            seeds = seeds[~np.isin(seeds, accepted_indices)]
        else:
            # Only suppress this failed hypothesis as a future RANSAC seed.
            seeds = np.delete(seeds, inlier_indices)

    return segments


def segment_vertical_cylinders(points, planes, tolerance=0.02, radius_range=(0.03, 0.12),
                               min_points=500, min_height=1.0, iterations=1000, seed=7):
    """Circle RANSAC in XY; assumes cylinder axes parallel to global Z.

    No synthetic scene dimensions/centers are used. Angular and height coverage
    reject short arcs and isolated point accumulations. Returns disjoint labels.
    """
    rng = np.random.default_rng(seed)
    available = np.ones(len(points), dtype=bool)
    for plane in planes:
        available[plane.point_indices] = False
    remaining = np.flatnonzero(available)
    cylinders = []
    while len(remaining) >= min_points:
        xyz = points[remaining]
        xy = xyz[:, :2]
        best = None
        best_count = min_points - 1
        for _ in range(iterations):
            first = rng.integers(len(xy))
            neighbours = np.flatnonzero(np.linalg.norm(xy - xy[first], axis=1) < 2 * radius_range[1])
            if len(neighbours) < 3:
                continue
            sample = xy[rng.choice(neighbours, 3, replace=False)]
            offsets = sample[1:] - sample[0]
            if abs(np.linalg.det(offsets)) < 1e-8:
                continue
            center = sample[0] + np.linalg.solve(2 * offsets, np.sum(offsets**2, axis=1))
            radius = np.linalg.norm(sample[0] - center)
            if not radius_range[0] <= radius <= radius_range[1]:
                continue
            mask = np.abs(np.linalg.norm(xy - center, axis=1) - radius) <= tolerance
            count = int(mask.sum())
            if count <= best_count:
                continue
            angles = np.arctan2(xy[mask, 1] - center[1], xy[mask, 0] - center[0])
            bins = np.floor((angles + np.pi) / (2 * np.pi) * 12).astype(int) % 12
            heights = np.percentile(xyz[mask, 2], [2, 98])
            height_counts, _ = np.histogram(xyz[mask, 2], bins=8, range=heights)
            if len(np.unique(bins)) < 10 or np.diff(heights)[0] < min_height or np.any(height_counts < 5):
                continue
            best = (center, radius, mask)
            best_count = count
        if best is None:
            break
        center, radius, mask = best
        # Geometric least-squares refinement of radial distances (Gauss-Newton).
        for _ in range(8):
            delta = xy[mask] - center
            distances = np.maximum(np.linalg.norm(delta, axis=1), 1e-12)
            jacobian = np.column_stack((-delta / distances[:, None], -np.ones(mask.sum())))
            update = np.linalg.lstsq(jacobian, -(distances - radius), rcond=None)[0]
            candidate_center, candidate_radius = center + update[:2], radius + update[2]
            if not radius_range[0] <= candidate_radius <= radius_range[1]:
                break
            candidate_mask = np.abs(np.linalg.norm(xy - candidate_center, axis=1) - candidate_radius) <= tolerance
            if candidate_mask.sum() < min_points:
                break
            center, radius, mask = candidate_center, candidate_radius, candidate_mask
        indices = remaining[mask]
        errors = np.abs(np.linalg.norm(points[indices, :2] - center, axis=1) - radius)
        z_min, z_max = np.percentile(points[indices, 2], [2, 98])
        cylinders.append(Segment(len(planes) + len(cylinders) + 1, indices, None,
                                 float(np.sqrt(np.mean(errors**2))), float(errors.mean()),
                                 {"axis_point": [float(center[0]), float(center[1]), 0.0],
                                  "axis_direction": [0.0, 0.0, 1.0], "radius": float(radius),
                                  "z_min": float(z_min), "z_max": float(z_max),
                                  "height": float(z_max - z_min)}))
        remaining = remaining[~mask]
    return cylinders


def segment_palette(count: int) -> np.ndarray:
    """Generate visibly different colors without adding a plotting dependency."""
    colors = []
    for index in range(count):
        hue = (index * 0.61803398875) % 1.0
        sector = int(hue * 6)
        fraction = hue * 6 - sector
        values = [(1.0, fraction, 0.15), (1.0 - fraction, 1.0, 0.15), (0.15, 1.0, fraction),
                  (0.15, 1.0 - fraction, 1.0), (fraction, 0.15, 1.0), (1.0, 0.15, 1.0 - fraction)]
        colors.append(values[sector])
    return np.asarray(colors, dtype=np.float64)


def save_results(
    points: np.ndarray,
    segments: Iterable[Segment],
    metadata: dict,
    output_dir: Path,
    input_colors=None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    segments = list(segments)
    labels = np.zeros(len(points), dtype=np.int32)
    for segment in segments:
        labels[segment.point_indices] = segment.segment_id

    with (output_dir / "assignments.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["point_index", "x", "y", "z", "segment_id"] + (["red", "green", "blue"] if input_colors is not None else []))
        for index, (point, label) in enumerate(zip(points, labels)):
            writer.writerow([index, *[f"{value:.9g}" for value in point], int(label)]
                            + (input_colors[index].tolist() if input_colors is not None else []))

    segment_records = []
    for segment in segments:
        segment_records.append(
            {
                "segment_id": segment.segment_id,
                "type": "freeform" if segment.freeform is not None else ("cylinder" if segment.cylinder is not None else "plane"),
                "plane": segment.plane.tolist() if segment.plane is not None else None,
                "cylinder": segment.cylinder,
                "freeform": segment.freeform,
                "plane_coverage": segment.plane_coverage,
                "point_count": int(len(segment.point_indices)),
                "rmse": segment.rmse,
                "mean_absolute_error": segment.mean_absolute_error,
            }
        )
    result = {**metadata, "segments": segment_records, "unassigned_point_count": int(np.sum(labels == 0))}
    (output_dir / "segments.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    try:
        import open3d as o3d
    except ImportError:
        return
    palette = segment_palette(len(segments))
    colors = np.tile([0.55, 0.55, 0.55], (len(points), 1))
    for segment in segments:
        colors[segment.point_indices] = palette[segment.segment_id - 1]
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    cloud.colors = o3d.utility.Vector3dVector(colors)
    o3d.io.write_point_cloud(str(output_dir / "segmented.ply"), cloud)
    if input_colors is not None:
        cloud.colors = o3d.utility.Vector3dVector(np.nan_to_num(input_colors, nan=.35))
        o3d.io.write_point_cloud(str(output_dir / "input_rgb.ply"), cloud)


def visualize(points: np.ndarray, segments: Iterable[Segment], input_colors=None) -> None:
    import open3d as o3d

    segments = list(segments)
    labels = np.zeros(len(points), dtype=np.int32)
    for segment in segments:
        labels[segment.point_indices] = segment.segment_id
    colors = np.tile([0.55, 0.55, 0.55], (len(points), 1))
    palette = segment_palette(len(segments))
    for segment in segments:
        colors[segment.point_indices] = palette[segment.segment_id - 1]
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    cloud.colors = o3d.utility.Vector3dVector(colors)
    viewer = o3d.visualization.VisualizerWithKeyCallback()
    if not viewer.create_window(window_name="Segmente | 1–5: Ansichten | R: Grau/Segmente | C: Eingangs-RGB"):
        raise RuntimeError("Open3D-Fenster konnte nicht geöffnet werden.")
    viewer.add_geometry(cloud)
    viewer.get_render_option().point_size = 3.0
    center = cloud.get_axis_aligned_bounding_box().get_center()

    def camera(front, up):
        def callback(vis):
            control = vis.get_view_control()
            control.set_lookat(center)
            control.set_front(front)
            control.set_up(up)
            control.set_zoom(0.7)
            return False
        return callback

    views = [([1, -1, 0.9], [0, 0, 1]),
             ([0, 0, 1], [0, 1, 0]),
             ([0, -1, 0], [0, 0, 1]),
             ([1, 0, 0], [0, 0, 1]),
             ([-1, 1, 0.9], [0, 0, 1])]
    for key, (front, up) in zip("12345", views):
        viewer.register_key_callback(ord(key), camera(front, up))
    show_segments = True

    def toggle_colors(vis):
        nonlocal show_segments
        show_segments = not show_segments
        cloud.colors = o3d.utility.Vector3dVector(
            colors if show_segments else np.tile([0.35, 0.35, 0.35], (len(points), 1)))
        vis.update_geometry(cloud)
        print("Segmentfarben" if show_segments else "Ungefärbte Punkte (nach Ausschnitt/Voxelreduktion)")
        return False

    viewer.register_key_callback(ord("R"), toggle_colors)
    def original_colors(vis):
        nonlocal show_segments
        if input_colors is not None:
            show_segments = False
            cloud.colors = o3d.utility.Vector3dVector(np.nan_to_num(input_colors, nan=.35))
            vis.update_geometry(cloud)
            print("Eingangs-RGB (keine Segmentfarben)")
        else:
            print("Keine Eingangsfarben vorhanden.")
        return False
    viewer.register_key_callback(ord("C"), original_colors)
    camera(*views[0])(viewer)
    print("Ansichten: 1–5; R: Segmentfarben/Grau; C: Eingangs-RGB; Maus: frei drehen.")
    try:
        viewer.run()
    finally:
        viewer.destroy_window()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="Lokale .e57-Datei")
    parser.add_argument("--synthetic", action="store_true", help="Kleine Testszene statt E57 verwenden")
    parser.add_argument("--room", action="store_true", help="Verrauschten Raum mit vier Wänden erzeugen")
    parser.add_argument("--construction-site", action="store_true", help="Komplexe Baustellen-Testszene erzeugen")
    parser.add_argument("--novel-scene", action="store_true", help="Laderampe, Kiosk, Gehäuse, Treppe und Faltblech testen")
    parser.add_argument("--installations", action="store_true",
                        help="Mit --room: zwei Türen, zwei Fenster und zwei Gruppen mit je drei Rohren")
    parser.add_argument("--noise", type=float, default=0.015, help="Raum: Rausch-Standardabweichung je Achse in Metern")
    parser.add_argument("--seed", type=int, default=7, help="Zufallsseed für Testszene und RANSAC")
    parser.add_argument("--scan-index", type=int, default=0)
    parser.add_argument("--bbox", type=float, nargs=6, metavar=("XMIN", "YMIN", "ZMIN", "XMAX", "YMAX", "ZMAX"))
    parser.add_argument("--voxel-size", type=float, default=0.03, help="Voxelgröße in Einheiten der Datei (default: 0.03)")
    parser.add_argument("--distance-tolerance", type=float, default=0.025, help="RANSAC-Abstandstoleranz (default: 0.025)")
    parser.add_argument("--plane-cluster-distance", type=float, default=None,
                        help="DBSCAN-Radius innerhalb einer Ebene; Standard: 2.5 × max(Voxelgröße, Abstandstoleranz)")
    parser.add_argument("--min-segment-size", type=int, default=150, help="Minimale Punktzahl pro Segment")
    parser.add_argument("--max-iterations", type=int, default=1000, help="RANSAC-Iterationen")
    parser.add_argument("--chunk-size", type=int, default=100_000, help="Anzahl Rohpunkte je E57-Leseblock")
    parser.add_argument("--output-dir", type=Path, default=Path("e57_output"))
    parser.add_argument("--no-visualization", action="store_true")
    parser.add_argument("--wall-construction", action="store_true", help="Mit --room: unregelmäßige Wandkonstruktion hinzufügen")
    parser.add_argument("--two-constructions", action="store_true", help="Mit --room: zwei benachbarte Wandkonstruktionen")
    parser.add_argument("--construction-gap", type=float, default=0.15, help="Abstand der rauschfreien X-Begrenzungen in Metern")
    parser.add_argument("--freeform", action="store_true", help="Nach großen Ebenen und optional Zylindern freie Punktsegmente bilden")
    parser.add_argument("--use-rgb", action="store_true", help="Mit --freeform: RGB zusätzlich zur Nähe berücksichtigen")
    parser.add_argument("--color-distance", type=float, default=0.18, help="Maximaler RGB-Abstand in normiertem RGB [0,1]")
    parser.add_argument("--cluster-distance", type=float, default=0.08, help="DBSCAN-Radius für freie Segmente")
    parser.add_argument("--min-freeform-size", type=int, default=150)
    parser.add_argument("--cylinders", action="store_true", help="Große Ebenen, dann senkrechte Zylinder suchen")
    parser.add_argument("--min-plane-width", type=float, default=1.0, help="Mit --cylinders: Mindestbreite großer Ebenen")
    parser.add_argument("--min-plane-coverage", type=float, default=0.55, help="Mindestanteil belegter Rasterzellen je Ebene; 0 deaktiviert Filter")
    parser.add_argument("--coverage-cell-size", type=float, default=0.12, help="Rasterzellengröße für Flächendeckung")
    parser.add_argument("--cylinder-tolerance", type=float, default=0.02, help="Radiale Zylinder-Abstandstoleranz")
    parser.add_argument("--radius-range", type=float, nargs=2, default=[0.03, 0.12], metavar=("MIN", "MAX"))
    parser.add_argument("--min-cylinder-height", type=float, default=1.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.use_rgb and not args.freeform:
        raise SystemExit("--use-rgb benötigt --freeform.")
    if not np.isfinite(args.color_distance) or args.color_distance <= 0:
        raise SystemExit("--color-distance muss positiv und endlich sein.")
    input_colors = None
    if (not np.isfinite(args.min_plane_coverage) or not 0 <= args.min_plane_coverage <= 1
            or not np.isfinite(args.coverage_cell_size) or args.coverage_cell_size <= 0):
        raise SystemExit("Flächendeckung muss in [0,1] liegen; Rasterzellengröße muss positiv und endlich sein.")
    if args.voxel_size <= 0 or args.distance_tolerance <= 0 or args.min_segment_size < 3 or args.chunk_size < 1:
        raise SystemExit("Voxelgröße und Toleranz müssen > 0 sein; Mindestsegmentgröße >= 3; Chunkgröße > 0.")
    if args.plane_cluster_distance is not None and (
            not np.isfinite(args.plane_cluster_distance) or args.plane_cluster_distance <= 0):
        raise SystemExit("--plane-cluster-distance muss positiv und endlich sein.")
    if sum([args.synthetic, args.room, args.construction_site, args.novel_scene, args.input is not None]) != 1:
        raise SystemExit("Bitte genau eine Quelle wählen: E57-Datei, --synthetic, --room, --construction-site oder --novel-scene.")
    if not np.isfinite(args.noise) or args.noise < 0:
        raise SystemExit("--noise muss endlich und >= 0 sein.")
    if args.installations and not args.room:
        raise SystemExit("--installations benötigt --room.")
    if (args.wall_construction or args.two_constructions) and not args.room:
        raise SystemExit("Wandkonstruktionen benötigen --room.")
    if not np.isfinite(args.construction_gap) or not 0 <= args.construction_gap <= 2:
        raise SystemExit("--construction-gap muss zwischen 0 und 2 m liegen (Test-Raumgröße).")
    if not np.isfinite(args.cluster_distance) or args.cluster_distance <= 0 or args.min_freeform_size < 5:
        raise SystemExit("Clusterabstand muss positiv und endlich sein; Mindestgröße >= 5.")
    if (not all(np.isfinite(v) and v > 0 for v in
                [args.min_plane_width, args.cylinder_tolerance, *args.radius_range, args.min_cylinder_height])
            or args.radius_range[0] >= args.radius_range[1] or args.max_iterations < 1):
        raise SystemExit("Geometrieparameter müssen positiv und endlich sein; Radius MIN < MAX; Iterationen >= 1.")

    try:
        if args.synthetic or args.room or args.construction_site or args.novel_scene:
            if args.construction_site:
                from construction_site import site_details
                from rgb_utils import surface_colors
                details, inventory, detail_rgb = site_details(args.seed, args.noise, with_colors=True)
                room = synthetic_room(args.seed, args.noise, True)
                left, right = synthetic_wall_pair(args.seed, args.noise, .05)
                points = np.vstack((room, details, left, right))
                input_colors = np.vstack((surface_colors(room, [.75,.73,.69]), detail_rgb,
                                          surface_colors(left, [.8,.16,.08]),
                                          surface_colors(right, [.08,.25,.8], args.seed+1)))
            elif args.novel_scene:
                from novel_scene import novel_scene
                points, inventory, input_colors = novel_scene(args.seed, args.noise)
            else:
                points = synthetic_room(args.seed, args.noise, args.installations) if args.room else synthetic_scene(args.seed)
            if args.two_constructions:
                points = np.vstack((points, *synthetic_wall_pair(args.seed, args.noise, args.construction_gap)))
            elif args.wall_construction:
                points = np.vstack((points, synthetic_wall_construction(args.seed, args.noise)))
            raw_count = len(points)
            if args.bbox is not None:
                bbox = np.asarray(args.bbox)
                keep = np.all(points >= bbox[:3], axis=1) & np.all(points <= bbox[3:], axis=1)
                points = points[keep]
                if input_colors is not None:
                    input_colors = input_colors[keep]
            accumulator = VoxelAccumulator(args.voxel_size)
            accumulator.add(points, input_colors)
            points = accumulator.array()
            input_colors = accumulator.colors()
            metadata = {"input": "synthetic_room" if args.room else "synthetic",
                        "raw_point_count": raw_count, "voxel_point_count": int(len(points)),
                        "seed": args.seed, "transformation_applied_once": False}
            if args.construction_site:
                metadata.update(input="synthetic_construction_site", room_dimensions_m=[6,4,2.8],
                                noise_std_m=args.noise, site_details=inventory,
                                openings=ROOM_OPENINGS, base_pipe_groups_xy_m=PIPE_GROUPS,
                                construction_count=2, construction_gap_m=.05,
                                visibility_model="surface sampling; no scanner occlusion simulation")
            if args.novel_scene:
                metadata.update(input="synthetic_loading_bay", scene_objects=inventory,
                                noise_std_m=args.noise,
                                visibility_model="uneven surface sampling; no scanner visibility model")
            if args.room:
                metadata["wall_construction"] = args.wall_construction
                metadata["construction_count"] = 2 if args.two_constructions else int(args.wall_construction)
                if args.two_constructions:
                    metadata["construction_gap_m"] = args.construction_gap
                metadata.update(room_dimensions_m=[6, 4, 2.8], noise_std_m=args.noise,
                                missing_wall_fraction=0.1, generated_outlier_count=800)
                if args.installations:
                    metadata.update(openings=ROOM_OPENINGS, pipe_groups_xy_m=PIPE_GROUPS,
                                    pipe_radius_m=0.06, pipe_height_m=2.8,
                                    missing_pipe_fraction=0.1)
        else:
            bbox = np.asarray(args.bbox, dtype=np.float64) if args.bbox is not None else None
            points, metadata, input_colors = read_e57_stream(
                args.input,
                args.scan_index,
                bbox,
                args.voxel_size,
                args.chunk_size,
            )

        if len(points) < args.min_segment_size:
            raise SystemExit(f"Nach Filterung sind nur {len(points)} Punkte übrig.")
        import open3d as o3d
        if args.use_rgb and input_colors is None:
            raise SystemExit("Keine RGB-Daten vorhanden. --use-rgb weglassen oder farbige E57/Baustellenszene verwenden.")
        metadata.update(rgb_available=input_colors is not None, use_rgb=args.use_rgb,
                        color_distance=args.color_distance if args.use_rgb else None)
        o3d.utility.random.seed(args.seed)
        metadata.update(voxel_size=args.voxel_size, distance_tolerance=args.distance_tolerance,
                        min_segment_size=args.min_segment_size,
                        min_plane_coverage=args.min_plane_coverage, coverage_cell_size=args.coverage_cell_size,
                        plane_cluster_distance=args.plane_cluster_distance or max(2.5 * args.voxel_size,
                                                                                 2.5 * args.distance_tolerance))
        segments = segment_planes(
            points,
            args.distance_tolerance,
            args.min_segment_size,
            args.voxel_size,
            args.max_iterations,
            args.min_plane_width if args.cylinders or args.freeform else 0.0,
            args.min_plane_coverage,
            args.coverage_cell_size,
            args.plane_cluster_distance,
        )
        if args.cylinders:
            metadata.update(cylinder_axis_assumption="global Z", min_plane_width=args.min_plane_width,
                            cylinder_tolerance=args.cylinder_tolerance, radius_range=args.radius_range,
                            min_cylinder_height=args.min_cylinder_height)
            segments += segment_vertical_cylinders(
                points, segments, args.cylinder_tolerance, args.radius_range,
                args.min_segment_size, args.min_cylinder_height, args.max_iterations, args.seed)
        if args.freeform:
            metadata.update(cluster_distance=args.cluster_distance, min_freeform_size=args.min_freeform_size,
                            min_plane_width=args.min_plane_width)
            segments += segment_freeform(points, segments, args.cluster_distance, args.min_freeform_size,
                                         input_colors if args.use_rgb else None, args.color_distance)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    save_results(points, segments, metadata, args.output_dir, input_colors)
    print(f"Segmente: {len(segments)}")
    for segment in segments:
        if segment.freeform is not None:
            print(f"  Segment {segment.segment_id}: {len(segment.point_indices):,} Punkte; freie Geometrie (kein Modellfit)")
            continue
        print(
            f"  Segment {segment.segment_id}: {len(segment.point_indices):,} Punkte; "
            f"RMSE={segment.rmse:.5f}; "
            + (f"Zylinder: Radius={segment.cylinder['radius']:.4f}, Höhe={segment.cylinder['height']:.3f}"
               if segment.cylinder is not None else f"Ebene={np.array2string(segment.plane, precision=5)}")
        )
    print(f"Ergebnisse: {args.output_dir.resolve()}")
    if not args.no_visualization:
        visualize(points, segments, input_colors)


if __name__ == "__main__":
    main()
