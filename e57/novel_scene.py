"""Synthetic loading bay: no room walls, pipes, or scaffold.

The inventory records source objects for evaluation only. Segmentation never
receives these labels. Surfaces deliberately have different sampling steps.
"""

import numpy as np


def novel_scene(seed=7, noise=.01, with_colors=True):
    from rgb_utils import surface_colors

    rng = np.random.default_rng(seed + 900)
    parts, colors, inventory = [], [], []

    def add(name, xyz, keep_fraction, base_color):
        xyz = np.asarray(xyz, dtype=float).reshape(-1, 3)
        xyz = xyz[rng.random(len(xyz)) < keep_fraction].copy()
        xyz += rng.normal(0, noise, xyz.shape)
        parts.append(xyz)
        inventory.append({"name": name, "generated_point_count": len(xyz)})
        if with_colors:
            colors.append(surface_colors(xyz, base_color, seed + len(parts)))

    def rectangle(origin, u, v, step):
        u, v = np.asarray(u, float), np.asarray(v, float)
        a, b = np.meshgrid(np.linspace(0, 1, int(np.linalg.norm(u) / step) + 1),
                           np.linspace(0, 1, int(np.linalg.norm(v) / step) + 1))
        return np.asarray(origin, float) + a.ravel()[:, None] * u + b.ravel()[:, None] * v

    def box(origin, size, step):
        origin, size = np.asarray(origin, float), np.asarray(size, float)
        faces = []
        for axis in range(3):
            a, b = [coordinate for coordinate in range(3) if coordinate != axis]
            u, v = np.zeros(3), np.zeros(3)
            u[a], v[b] = size[a], size[b]
            for side in (0, size[axis]):
                offset = np.zeros(3)
                offset[axis] = side
                faces.append(rectangle(origin + offset, u, v, step))
        return np.vstack(faces)

    # Broad low-density slab. It is intentionally connected to several objects.
    add("ground_slab", rectangle([0, 0, 0], [8, 0, 0], [0, 6, 0], .11),
        .82, [.55, .55, .53])
    # One inclined loading surface, unlike the room's vertical planes.
    add("loading_ramp", rectangle([.4, .5, .12], [2.8, 0, 0], [0, 2.0, .8], .045),
        .78, [.54, .56, .58])
    # Enclosed rectangular kiosk, coarser and sparser than the ramp.
    add("control_kiosk", box([5.5, .5, .03], [1.55, 1.25, 2.2], .085),
        .7, [.6, .59, .55])
    # Curved elliptical machine housing: no planar or cylindrical surface.
    theta, height = np.meshgrid(np.linspace(0, 2 * np.pi, 100, endpoint=False),
                                np.linspace(-.96, .96, 65))
    ring = np.sqrt(1 - height**2)
    shell = np.column_stack((5.4 + .85 * ring.ravel() * np.cos(theta.ravel()),
                             4.0 + .65 * ring.ravel() * np.sin(theta.ravel()),
                             1.15 + 1.05 * height.ravel()))
    add("ellipsoid_housing", shell, .78, [.6, .59, .55])
    # Treads and risers form one assembled staircase, not one plane.
    stair_faces = []
    for i in range(6):
        x, z = .75 + .34 * i, .22 + .24 * i
        stair_faces.append(rectangle([x, 4.45, z], [.34, 0, 0], [0, 1.15, 0], .06))
        stair_faces.append(rectangle([x, 4.45, z - .24], [0, 1.15, 0], [0, 0, .24], .06))
    add("staircase", np.vstack(stair_faces), .75, [.54, .56, .58])
    # Folded suspended sheet with alternating normals, not a single plane.
    folds = []
    for i in range(4):
        x = 2.8 + .43 * i
        z = 2.25 + (.28 if i % 2 else 0)
        next_z = 2.25 + (.28 if (i + 1) % 2 else 0)
        folds.append(rectangle([x, 2.8, z], [.43, 0, next_z - z], [0, 1.5, 0], .04))
    add("folded_canopy", np.vstack(folds), .67, [.6, .59, .55])
    # A few isolated measurement outliers are not object ground truth.
    add("outliers", rng.uniform([-.2, -.2, -.2], [8.2, 6.2, 3.2], (450, 3)),
        1., [.5, .5, .5])
    return (np.vstack(parts), inventory,
            np.vstack(colors) if with_colors else None)
