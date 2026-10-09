"""Primitive aus segmentierten Punkten: AABB-Boxen und x-paralleles Rohr mit Bootstrap-Unsicherheit."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config import Config
from scan import Scan
from scene import BEAM, DEVICE, NAMES, PIPE, TRAY


@dataclass
class FittedBox:
    name: str
    lo: np.ndarray
    hi: np.ndarray
    n_points: int


@dataclass
class FittedPipe:
    cy: float
    cz: float
    r: float
    x0: float
    x1: float
    n_points: int
    r_ci: tuple[float, float]
    cy_ci: tuple[float, float]
    cz_ci: tuple[float, float]
    top_ci: tuple[float, float]
    seen_fraction: float        # gesehener Umfangsanteil aus der größten Winkellücke
    sys_margin: float = 0.0     # systematischer Zuschlag, wächst mit ungesehenem Umfang

    @property
    def top(self) -> float:
        return self.cz + self.r

    def plausible_radius(self, largest: bool) -> float:
        """Kleinstes/größtes plausibles Rohr: Radiusgrenze ± halbe Mittelpunkt-Intervallbreite ± Zuschlag."""
        extra = max(np.diff(self.cy_ci)[0], np.diff(self.cz_ci)[0]) / 2 + self.sys_margin
        if largest:
            return self.r_ci[1] + extra
        return max(self.r_ci[0] - extra, 0.0)


def fit_box(points: np.ndarray, name: str, min_points: int) -> FittedBox | None:
    """AABB der Punkte; None bei zu wenigen Punkten („nicht erkannt")."""
    if len(points) < min_points:
        return None
    return FittedBox(name, points.min(axis=0), points.max(axis=0), len(points))


def fit_circle_kasa(yz: np.ndarray) -> tuple[float, float, float]:
    """Algebraischer Kreisfit (Kåsa): 2a·y + 2b·z + c = y² + z²."""
    A = np.column_stack([2 * yz, np.ones(len(yz))])
    rhs = np.sum(yz**2, axis=1)
    (a, b, c), *_ = np.linalg.lstsq(A, rhs, rcond=None)
    return a, b, np.sqrt(c + a**2 + b**2)


def refine_circle_gn(yz: np.ndarray, cy: float, cz: float, r: float, iters: int = 10):
    """Geometrischer Fit: Gauß-Newton auf Residuen ‖p − c‖ − r."""
    p = np.array([cy, cz, r])
    for _ in range(iters):
        diff = yz - p[:2]
        dist = np.linalg.norm(diff, axis=1)
        res = dist - p[2]
        J = np.column_stack([-diff / dist[:, None], -np.ones(len(yz))])
        delta, *_ = np.linalg.lstsq(J, -res, rcond=None)
        p += delta
        if np.linalg.norm(delta) < 1e-9:
            break
    return tuple(p)


def fit_circle(yz: np.ndarray, iters: int = 10) -> tuple[float, float, float]:
    return refine_circle_gn(yz, *fit_circle_kasa(yz), iters=iters)


def seen_fraction(yz: np.ndarray, cy: float, cz: float) -> float:
    """1 − größte Winkellücke / 2π."""
    ang = np.sort(np.arctan2(yz[:, 1] - cz, yz[:, 0] - cy))
    gaps = np.diff(np.concatenate([ang, [ang[0] + 2 * np.pi]]))
    return 1.0 - gaps.max() / (2 * np.pi)


def fit_pipe(points: np.ndarray, cfg: Config, rng: np.random.Generator) -> FittedPipe | None:
    """Manhattan-Prior: Achse ∥ x. Kreisfit in y-z, Länge aus den Punkten, Bootstrap-Intervalle."""
    if len(points) < cfg.min_points:
        return None
    yz = points[:, 1:]
    cy, cz, r = fit_circle(yz, cfg.gn_iters)
    seen = seen_fraction(yz, cy, cz)

    boot = np.empty((cfg.bootstrap_reps, 3))
    for i in range(cfg.bootstrap_reps):
        sample = yz[rng.integers(0, len(yz), len(yz))]
        boot[i] = fit_circle(sample, cfg.gn_iters)
    ci = lambda v: tuple(np.percentile(v, [2.5, 97.5]))
    return FittedPipe(cy, cz, r, points[:, 0].min(), points[:, 0].max(), len(points),
                      r_ci=ci(boot[:, 2]), cy_ci=ci(boot[:, 0]), cz_ci=ci(boot[:, 1]),
                      top_ci=ci(boot[:, 1] + boot[:, 2]), seen_fraction=seen,
                      sys_margin=cfg.pipe_sys_margin * (1 - seen))


@dataclass
class Fits:
    boxes: list[FittedBox]
    pipe: FittedPipe | None
    missing: list[str]          # Objekte mit < min_points („nicht erkannt")


def fit_all(scans: list[Scan], cfg: Config, rng: np.random.Generator) -> Fits:
    """Fittet alle Nicht-Raum-Objekte. Segmentierung über obj_id = ORAKEL."""
    pts = np.concatenate([s.points for s in scans])
    ids = np.concatenate([s.obj_id for s in scans])
    boxes, missing = [], []
    for oid in (DEVICE, BEAM, TRAY):
        box = fit_box(pts[ids == oid], NAMES[oid], cfg.min_points)
        (boxes.append(box) if box else missing.append(NAMES[oid]))
    pipe = fit_pipe(pts[ids == PIPE], cfg, rng)
    if pipe is None:
        missing.append(NAMES[PIPE])
    return Fits(boxes, pipe, missing)
