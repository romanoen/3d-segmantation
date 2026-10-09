"""Synthetic construction-site surfaces; no labels are passed to segmentation."""
import numpy as np


def site_details(seed=7, noise=0.01, with_colors=False):
    rng = np.random.default_rng(seed + 500)
    parts = []
    inventory = []
    colors = []

    def add(name, points):
        points = np.asarray(points).reshape(-1, 3)
        points = points[rng.random(len(points)) > 0.15]
        points += rng.normal(0, noise, points.shape)
        parts.append(points)
        if with_colors:
            from rgb_utils import surface_colors
            # Shared material colors, not a unique color per object.
            base = [.5,.52,.54]
            if name.startswith(('riser', 'elbow', 'overhead')):
                base = [.75,.16,.09] if int(name.rsplit('_',1)[1]) < 2 else [.12,.3,.75]
            elif name.startswith('scaffold'):
                base = [.85,.65,.12]
            elif name == 'material_box':
                base = [.6,.4,.2]
            elif name == 'cable_coil':
                base = [.09,.09,.09]
            colors.append(surface_colors(points, base, seed+len(parts)))
        inventory.append({"name": name, "generated_point_count": len(points)})

    def rectangle(origin, u, v):
        u, v = np.asarray(u), np.asarray(v)
        a, b = np.meshgrid(np.linspace(0, 1, max(2, int(np.linalg.norm(u)/.035)+1)),
                           np.linspace(0, 1, max(2, int(np.linalg.norm(v)/.035)+1)))
        return np.asarray(origin) + a.ravel()[:, None]*u + b.ravel()[:, None]*v

    def box(name, origin, size, angle=0):
        origin, size = np.asarray(origin), np.asarray(size)
        surfaces = []
        for axis in range(3):
            others = [a for a in range(3) if a != axis]
            u, v = np.zeros(3), np.zeros(3)
            u[others[0]], v[others[1]] = size[others[0]], size[others[1]]
            for side in (0, size[axis]):
                start = np.zeros(3); start[axis] = side
                surfaces.append(rectangle(start, u, v))
        c, s = np.cos(angle), np.sin(angle)
        rotation = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        add(name, np.vstack(surfaces) @ rotation.T + origin)

    def tube(name, centers, radius):
        centers = np.asarray(centers)
        tangent = np.gradient(centers, axis=0)
        tangent /= np.linalg.norm(tangent, axis=1)[:, None]
        # Project the previous frame to avoid twisting around curved paths.
        reference = np.eye(3)[np.argmin(np.abs(tangent[0]))]
        frames = []
        for direction in tangent:
            reference = reference - direction * np.dot(reference, direction)
            reference /= np.linalg.norm(reference)
            frames.append(reference.copy())
        side = np.array(frames)
        other = np.cross(tangent, side)
        theta = np.linspace(0, 2*np.pi, max(16, int(2*np.pi*radius/.02)), endpoint=False)
        add(name, centers[:, None, :] + radius * (
            np.cos(theta)[None, :, None]*side[:, None, :]
            + np.sin(theta)[None, :, None]*other[:, None, :]))

    def pipe(name, start, end, radius):
        count = max(3, int(np.linalg.norm(np.asarray(end)-start)/.025)+1)
        tube(name, np.linspace(start, end, count), radius)

    add('floor', rectangle([0, 0, 0], [6, 0, 0], [0, 4, 0]))
    # Four risers turn through 90 degrees into closely spaced overhead runs.
    for i in range(4):
        x, y = 1.0 + i*.03, .35 + i*.16
        pipe(f'riser_{i}', [x, y, .05], [x, y, 2.1], .05)
        theta = np.linspace(0, np.pi/2, 25)
        centers = np.column_stack((x + .25*(1-np.cos(theta)), np.full(len(theta), y),
                                   2.1 + .25*np.sin(theta)))
        tube(f'elbow_{i}', centers, .05)
        pipe(f'overhead_{i}', centers[-1], [4.8, y, 2.35], .05)
    for i in range(3):
        pipe(f'diagonal_{i}', [4.7+i*.13, .7, .2], [4.7+i*.13, 2.8, 2.5], .045)
    # A channel and transverse supports near the overhead pipes.
    box('channel_bottom', [.8, .8, 2.15], [3.6, .28, .035])
    for y in (.8, 1.055):
        box('channel_edge', [.8, y, 2.15], [3.6, .025, .12])
    for x in (1.3, 2.8, 4.1):
        pipe('cross_support', [x, .1, 2.08], [x, 1.15, 2.08], .025)
    # Scaffold in front of the installations, including actual contacts.
    for x in (2.0, 3.5):
        for y in (1.7, 2.5):
            pipe('scaffold_post', [x,y,.04], [x,y,2.2], .03)
    for y in (1.7, 2.5):
        pipe('scaffold_rail', [2,y,1.95], [3.5,y,1.95], .025)
        pipe('scaffold_brace', [2,y,.15], [3.5,y,1.8], .025)
    box('scaffold_deck', [1.95,1.65,1.1], [1.6,.9,.06])
    # Equipment, stacked boxes, leaning sheet, loose pipes and floor cable.
    box('equipment', [4.8,3.3,.02], [.65,.45,1.15])
    for i in range(3):
        box('material_box', [.55+i*.18,2.8,.02+i*.3], [.6,.5,.28], .12*i)
    add('leaning_panel', rectangle([.15,1.0,.02], [.05,.9,0], [.55,0,1.6]))
    for i in range(4):
        pipe('loose_pipe', [3.9,1.25+i*.13,.08], [5.7,1.4+i*.13,.08], .055)
    t = np.linspace(0, 4*np.pi, 180)
    tube('cable_coil', np.column_stack((1.15+(.3+.015*t)*np.cos(t),
                                      2.1+(.3+.015*t)*np.sin(t), .045+.002*t)), .018)
    if with_colors:
        return np.vstack(parts), inventory, np.vstack(colors)
    return np.vstack(parts), inventory
