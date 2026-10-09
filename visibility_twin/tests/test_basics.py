"""Wenige Sanity-Tests. Start: python -m pytest tests (im Ordner visibility_twin)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Config
from fit import fit_circle
from scan import Scan
from scene import Cylinder, ray_box, ray_cylinder_x
from voxels import FREE, OCCUPIED, UNKNOWN, build_grid, carve_station, make_spec


def test_ray_box():
    t, n = ray_box(np.zeros(3), np.array([[1.0, 0, 0], [-1.0, 0, 0]]),
                   np.array([1.0, -0.5, -0.5]), np.array([2.0, 0.5, 0.5]))
    assert np.isclose(t[0], 1.0) and np.allclose(n[0], [-1, 0, 0])
    assert np.isinf(t[1])


def test_ray_cylinder():
    cyl = Cylinder(0, x0=0.0, x1=2.0, cy=0.0, cz=0.0, r=0.5)
    d = np.array([[0, 0, 1.0], [0, 0, 1.0]])
    t, n = ray_cylinder_x(np.array([1.0, 0, -2]), d, cyl)
    assert np.isclose(t[0], 1.5) and np.allclose(n[0], [0, 0, -1])
    t_out, _ = ray_cylinder_x(np.array([3.0, 0, -2]), d, cyl)   # neben dem Zylinder
    assert np.isinf(t_out[0])


def test_circle_fit_noisy_half_circle():
    rng = np.random.default_rng(0)
    a = rng.uniform(np.pi, 2 * np.pi, 500)          # nur untere Hälfte sichtbar
    yz = np.column_stack([1.0 + 0.057 * np.cos(a), 2.6 + 0.057 * np.sin(a)])
    yz += rng.normal(0, 0.001, yz.shape)
    cy, cz, r = fit_circle(yz)
    assert abs(cy - 1.0) < 2e-3 and abs(cz - 2.6) < 2e-3 and abs(r - 0.057) < 2e-3


def test_single_ray_marks_voxels():
    cfg = Config()
    spec = make_spec(cfg)
    origin = np.array([0.525, 2.025, 1.525])            # Voxelmitte
    hit = np.array([[2.525, 2.025, 1.525]])             # 40 Voxel weiter in +x
    scan = Scan("T", origin, hit, np.zeros(1, int))
    state = build_grid(spec, [carve_station(cfg, spec, scan)])
    line = state[:, 40, 30]
    assert line[50] == OCCUPIED
    assert np.all(line[10:50] == FREE)                  # bis einen Voxel vor dem Treffer
    assert line[51] == UNKNOWN and line[9] == UNKNOWN   # hinter Treffer / hinter Station
    assert np.sum(state != UNKNOWN) == 41               # nichts außerhalb des Strahls


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
