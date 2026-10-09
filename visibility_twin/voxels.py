"""Voxelgitter mit UNKNOWN/FREE/OCCUPIED und einfachem Ray-Carving durch Abtasten."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config import Config
from scan import Scan

UNKNOWN, FREE, OCCUPIED = 0, 1, 2


@dataclass(frozen=True)
class GridSpec:
    origin: np.ndarray          # Ecke (min) des Gitters = Raumecke
    size: float                 # Kantenlänge eines Voxels
    shape: tuple[int, int, int]

    @property
    def n(self) -> int:
        return int(np.prod(self.shape))


@dataclass
class Carving:
    """Ergebnis einer Station: welche Voxel frei gesehen bzw. getroffen wurden."""
    free: np.ndarray            # bool, flach (n,)
    occupied: np.ndarray        # bool, flach (n,)


def make_spec(cfg: Config) -> GridSpec:
    lo, hi = np.array(cfg.room[0]), np.array(cfg.room[1])
    shape = tuple(int(round(v)) for v in (hi - lo) / cfg.voxel)
    return GridSpec(lo, cfg.voxel, shape)


def to_index(spec: GridSpec, pts: np.ndarray) -> np.ndarray:
    """Punkte (...,3) → Voxelindizes (...,3), am Rand geklemmt."""
    idx = np.floor((pts - spec.origin) / spec.size).astype(np.int64)
    return np.clip(idx, 0, np.array(spec.shape) - 1)


def to_flat(spec: GridSpec, idx: np.ndarray) -> np.ndarray:
    return np.ravel_multi_index(np.moveaxis(idx, -1, 0), spec.shape)


def centers(spec: GridSpec) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Voxelmittelpunkte je Achse."""
    return tuple(spec.origin[a] + (np.arange(spec.shape[a]) + 0.5) * spec.size for a in range(3))


def carve_station(cfg: Config, spec: GridSpec, scan: Scan) -> Carving:
    """Strahlen von der Station zu jedem Punkt: Voxel davor FREE, Treffervoxel OCCUPIED."""
    free = np.zeros(spec.n, bool)
    occ = np.zeros(spec.n, bool)
    occ[to_flat(spec, to_index(spec, scan.points))] = True

    pts = scan.points[:: cfg.carve_stride]
    step = spec.size / 2
    stop_before = cfg.carve_margin_vox * spec.size
    for start in range(0, len(pts), cfg.carve_block):
        vec = pts[start:start + cfg.carve_block] - scan.origin
        dist = np.linalg.norm(vec, axis=1)
        u = vec / dist[:, None]
        t = np.arange(0.0, dist.max(), step)                      # (S,)
        samples = scan.origin + t[None, :, None] * u[:, :, None].transpose(0, 2, 1)
        valid = t[None, :] < (dist - stop_before)[:, None]        # (B,S)
        free[to_flat(spec, to_index(spec, samples[valid]))] = True
    return Carving(free, occ)


def build_grid(spec: GridSpec, carvings: list[Carving]) -> np.ndarray:
    """Kombiniert Stationen. OCCUPIED wird nie durch FREE überschrieben. Rückgabe: (nx,ny,nz) uint8."""
    state = np.full(spec.n, UNKNOWN, np.uint8)
    state[np.logical_or.reduce([c.free for c in carvings])] = FREE
    state[np.logical_or.reduce([c.occupied for c in carvings])] = OCCUPIED
    return state.reshape(spec.shape)


def boundary_mask(spec: GridSpec) -> np.ndarray:
    """Äußerste Voxelschicht (Decke, Boden, Wände) – im Checker ausgenommen."""
    m = np.zeros(spec.shape, bool)
    m[[0, -1], :, :] = m[:, [0, -1], :] = m[:, :, [0, -1]] = True
    return m


def box_mask(spec: GridSpec, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Voxel, deren Mittelpunkt in der Box liegt (Mittelpunkt auf dem Rand zählt, konservativ)."""
    cx, cy, cz = centers(spec)
    tol = 1e-6 * spec.size   # Modulkanten fallen oft genau auf Voxelmittelpunkte
    inside = [(c >= l - tol) & (c <= h + tol) for c, l, h in zip((cx, cy, cz), lo, hi)]
    return inside[0][:, None, None] & inside[1][None, :, None] & inside[2][None, None, :]


def box_fractions(spec: GridSpec, state: np.ndarray, lo, hi, exclude_boundary: bool = True) -> dict:
    """Anteile unknown/free/occupied in einer achsparallelen Box (+ Voxelanzahl)."""
    m = box_mask(spec, np.asarray(lo), np.asarray(hi))
    if exclude_boundary:
        m &= ~boundary_mask(spec)
    vals = state[m]
    n = max(len(vals), 1)
    return {"unknown": np.sum(vals == UNKNOWN) / n, "free": np.sum(vals == FREE) / n,
            "occupied": np.sum(vals == OCCUPIED) / n, "n": len(vals)}
