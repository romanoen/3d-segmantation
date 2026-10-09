"""Input colors and spatial/color DBSCAN (not semantic object labels)."""
import numpy as np


def surface_colors(points, base, seed=7):
    rng = np.random.default_rng(seed)
    brightness = .85 + .12 * np.sin(points[:, 0] * 1.4 + points[:, 2])
    return np.clip(np.asarray(base) * brightness[:, None]
                   + rng.normal(0, .018, (len(points), 3)), 0, 1)


def color_dbscan(cloud, colors, eps, color_distance):
    """DBSCAN with spatial radius AND RGB distance; invalid colors stay noise.

    Five compatible neighbours make a core point. Color is in [0,1], not
    illumination invariant; local color chains can still connect objects.
    """
    import open3d as o3d
    xyz = np.asarray(cloud.points)
    tree = o3d.geometry.KDTreeFlann(cloud)
    labels = np.full(len(xyz), -1, dtype=int)
    visited = np.zeros(len(xyz), dtype=bool)
    valid = np.isfinite(colors).all(axis=1)

    def neighbours(i):
        _, ids, _ = tree.search_radius_vector_3d(xyz[i], eps)
        ids = np.asarray(ids, dtype=int)
        return ids[valid[ids] & (np.linalg.norm(colors[ids] - colors[i], axis=1) <= color_distance)]

    label = 0
    for start in range(len(xyz)):
        if visited[start] or not valid[start]:
            continue
        visited[start] = True
        seeds = neighbours(start)
        if len(seeds) < 5:
            continue
        labels[start] = label
        stack = seeds.tolist()
        queued = set(stack)
        while stack:
            i = stack.pop()
            if not visited[i]:
                visited[i] = True
                near = neighbours(i)
                if len(near) >= 5:
                    for j in near:
                        if j not in queued:
                            queued.add(j)
                            stack.append(j)
            if labels[i] < 0:
                labels[i] = label
        label += 1
    return labels
