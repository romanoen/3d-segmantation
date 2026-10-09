"""Single-view angular scan of the loading-bay geometry.

The first ray hit models occlusion. Object IDs are returned only for evaluation.
This is a simple synthetic sensor, not a calibrated scanner simulator.
"""

import numpy as np
import open3d as o3d

from rgb_utils import surface_colors


OBJECTS = ("ground_slab", "loading_ramp", "control_kiosk",
           "ellipsoid_housing", "staircase", "folded_canopy")
MATERIALS = ([.55, .55, .53], [.54, .56, .58], [.6, .59, .55],
             [.6, .59, .55], [.54, .56, .58], [.6, .59, .55])


def quad(origin, u, v):
    origin, u, v = np.asarray(origin, float), np.asarray(u, float), np.asarray(v, float)
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(np.array([origin, origin + u,
                                                        origin + u + v, origin + v]))
    mesh.triangles = o3d.utility.Vector3iVector([[0, 1, 2], [0, 2, 3]])
    return mesh


def make_scene():
    scene = o3d.t.geometry.RaycastingScene()
    owner = {}

    def add(mesh, object_id):
        geometry_id = scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
        owner[int(geometry_id)] = object_id

    add(quad([0, 0, 0], [8, 0, 0], [0, 6, 0]), 0)
    add(quad([.4, .5, .12], [2.8, 0, 0], [0, 2.0, .8]), 1)
    kiosk = o3d.geometry.TriangleMesh.create_box(width=1.55, height=1.25, depth=2.2)
    kiosk.translate([5.5, .5, .03])
    add(kiosk, 2)
    shell = o3d.geometry.TriangleMesh.create_sphere(radius=1, resolution=40)
    vertices = np.asarray(shell.vertices)
    vertices *= [.85, .65, 1.05]
    vertices += [5.4, 4., 1.15]
    add(shell, 3)
    for i in range(6):
        x, z = .75 + .34 * i, .22 + .24 * i
        add(quad([x, 4.45, z], [.34, 0, 0], [0, 1.15, 0]), 4)
        add(quad([x, 4.45, z - .24], [0, 1.15, 0], [0, 0, .24]), 4)
    for i in range(4):
        x = 2.8 + .43 * i
        z = 2.25 + (.28 if i % 2 else 0)
        next_z = 2.25 + (.28 if (i + 1) % 2 else 0)
        add(quad([x, 2.8, z], [.43, 0, next_z - z], [0, 1.5, 0]), 5)
    return scene, owner


def scanner_scene(seed=7, angular_step=.0012, range_noise=.002):
    """Return visible XYZ, source IDs, RGB and scan metadata.

    At 3 m the 1.2 mrad angular step corresponds to about 3.6 mm transverse
    spacing; at 10 m it corresponds to 12 mm. Range noise is independent.
    """
    if angular_step <= 0 or range_noise < 0:
        raise ValueError("Winkelabstand muss positiv sein; Rauschen darf nicht negativ sein.")
    rng = np.random.default_rng(seed)
    scene, owner = make_scene()
    position = np.array([4., -3.5, 1.6], dtype=np.float32)
    horizontal = np.arange(-50., 50.01, np.rad2deg(angular_step))
    vertical = np.arange(-30., 20.01, np.rad2deg(angular_step))
    azimuth, elevation = np.meshgrid(np.deg2rad(horizontal), np.deg2rad(vertical))
    direction = np.column_stack((np.cos(elevation.ravel()) * np.sin(azimuth.ravel()),
                                 np.cos(elevation.ravel()) * np.cos(azimuth.ravel()),
                                 np.sin(elevation.ravel()))).astype(np.float32)
    points, owners = [], []
    for start in range(0, len(direction), 50_000):
        rays = np.empty((min(50_000, len(direction) - start), 6), dtype=np.float32)
        rays[:, :3] = position
        rays[:, 3:] = direction[start:start + len(rays)]
        hits = scene.cast_rays(o3d.core.Tensor(rays))
        distance = hits["t_hit"].numpy()
        geometry = hits["geometry_ids"].numpy()
        keep = np.isfinite(distance) & (distance < 15) & (rng.random(len(rays)) > .08)
        distance = distance[keep] + rng.normal(0, range_noise, keep.sum())
        xyz = position + rays[keep, 3:] * distance[:, None]
        points.append(xyz)
        owners.extend(owner[int(geometry_id)] for geometry_id in geometry[keep])
    points = np.vstack(points).astype(np.float64)
    owners = np.asarray(owners, dtype=np.int16)
    colors = np.empty_like(points)
    for object_id, base in enumerate(MATERIALS):
        mask = owners == object_id
        colors[mask] = surface_colors(points[mask], base, seed + object_id)
    metadata = {"scanner_position_m": position.tolist(),
                "angular_step_mrad": angular_step * 1000,
                "range_noise_std_m": range_noise,
                "random_dropout": .08,
                "fov_horizontal_deg": [-50, 50], "fov_vertical_deg": [-30, 20],
                "raw_point_count": len(points)}
    return points, owners, colors, metadata
