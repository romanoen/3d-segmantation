"""Synthetische Szene: Primitive und analytische Ray-Schnitte (vektorisiert über Strahlen)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config import Config

# Objekt-IDs. 0–5 sind die Raumflächen (von innen gesehen).
FLOOR, CEILING, WALL_X0, WALL_X1, WALL_Y0, WALL_Y1 = range(6)
DEVICE, BEAM, PIPE, TRAY = 6, 7, 8, 9
ROOM_IDS = (FLOOR, CEILING, WALL_X0, WALL_X1, WALL_Y0, WALL_Y1)
NAMES = {FLOOR: "Boden", CEILING: "Decke", WALL_X0: "Wand x0", WALL_X1: "Wand x1",
         WALL_Y0: "Wand y0", WALL_Y1: "Wand y1", DEVICE: "Gerät", BEAM: "Unterzug",
         PIPE: "Rohr", TRAY: "Kabeltrasse"}

EPS = 1e-9


@dataclass(frozen=True)
class Box:
    obj_id: int
    lo: np.ndarray
    hi: np.ndarray


@dataclass(frozen=True)
class Cylinder:
    """Endlicher Zylinder mit Achse parallel zu x."""
    obj_id: int
    x0: float
    x1: float
    cy: float
    cz: float
    r: float


@dataclass(frozen=True)
class Scene:
    room_lo: np.ndarray
    room_hi: np.ndarray
    boxes: list[Box]
    cylinders: list[Cylinder]


def make_scene(cfg: Config) -> Scene:
    b = lambda oid, spec: Box(oid, np.array(spec[0], float), np.array(spec[1], float))
    pipe = Cylinder(PIPE, *cfg.pipe_x, *cfg.pipe_center_yz, cfg.pipe_radius)
    return Scene(np.array(cfg.room[0], float), np.array(cfg.room[1], float),
                 [b(DEVICE, cfg.device), b(BEAM, cfg.beam), b(TRAY, cfg.tray)], [pipe])


def _safe(d: np.ndarray) -> np.ndarray:
    """Richtungskomponenten ≠ 0, damit die Slab-Division definiert ist."""
    return np.where(np.abs(d) < EPS, EPS, d)


def ray_box(o: np.ndarray, d: np.ndarray, lo: np.ndarray, hi: np.ndarray):
    """Slab-Methode. o: (3,), d: (N,3). Liefert Eintrittsdistanz (inf = kein Treffer) und Normale."""
    ds = _safe(d)
    t1, t2 = (lo - o) / ds, (hi - o) / ds
    tmin, tmax = np.minimum(t1, t2), np.maximum(t1, t2)
    t_near, t_far = tmin.max(axis=1), tmax.min(axis=1)
    hit = (t_near <= t_far) & (t_near > EPS)
    axis = tmin.argmax(axis=1)
    n = np.zeros_like(d)
    n[np.arange(len(d)), axis] = -np.sign(ds[np.arange(len(d)), axis])
    return np.where(hit, t_near, np.inf), n


def ray_cylinder_x(o: np.ndarray, d: np.ndarray, cyl: Cylinder):
    """Schnitt mit Mantel und Deckeln eines x-parallelen Zylinders."""
    oy, oz = o[1] - cyl.cy, o[2] - cyl.cz
    dy, dz = d[:, 1], d[:, 2]
    a = dy**2 + dz**2
    b = 2 * (oy * dy + oz * dz)
    c = oy**2 + oz**2 - cyl.r**2
    disc = b**2 - 4 * a * c
    with np.errstate(invalid="ignore", divide="ignore"):
        t_side = (-b - np.sqrt(disc)) / (2 * a)   # nur Eintritt von außen
    x_side = o[0] + t_side * d[:, 0]
    side_ok = (disc >= 0) & (t_side > EPS) & (x_side >= cyl.x0) & (x_side <= cyl.x1)
    t = np.where(side_ok, t_side, np.inf)
    n = np.zeros_like(d)
    py, pz = oy + t_side * dy, oz + t_side * dz
    n[:, 1], n[:, 2] = py / cyl.r, pz / cyl.r

    # Deckel bei x0 (Normale -x) und x1 (Normale +x)
    dx = _safe(d[:, 0])
    for xc, sign in ((cyl.x0, -1.0), (cyl.x1, 1.0)):
        tc = (xc - o[0]) / dx
        yy, zz = oy + tc * dy, oz + tc * dz
        cap_ok = (tc > EPS) & (yy**2 + zz**2 <= cyl.r**2) & (tc < t) & (sign * d[:, 0] < 0)
        t = np.where(cap_ok, tc, t)
        n[cap_ok] = (sign, 0.0, 0.0)
    return t, n


def ray_room_exit(o: np.ndarray, d: np.ndarray, lo: np.ndarray, hi: np.ndarray):
    """Austritt aus dem Raum (Start innen). Liefert Distanz, Raumflächen-ID und Normale (nach innen)."""
    ds = _safe(d)
    t1, t2 = (lo - o) / ds, (hi - o) / ds
    tmax = np.maximum(t1, t2)
    axis = tmax.argmin(axis=1)
    rows = np.arange(len(d))
    t = tmax[rows, axis]
    positive = ds[rows, axis] > 0
    # Achse 0 → Wand x0/x1, Achse 1 → Wand y0/y1, Achse 2 → Boden/Decke
    face_ids = np.array([[WALL_X0, WALL_X1], [WALL_Y0, WALL_Y1], [FLOOR, CEILING]])
    ids = face_ids[axis, positive.astype(int)]
    n = np.zeros_like(d)
    n[rows, axis] = np.where(positive, -1.0, 1.0)
    return t, ids, n


def cast_rays(scene: Scene, o: np.ndarray, d: np.ndarray):
    """Erster Treffer pro Strahl. d muss normiert sein. Liefert (t, obj_id, normal)."""
    t, ids, n = ray_room_exit(o, d, scene.room_lo, scene.room_hi)
    hits = [(box.obj_id, *ray_box(o, d, box.lo, box.hi)) for box in scene.boxes]
    hits += [(cyl.obj_id, *ray_cylinder_x(o, d, cyl)) for cyl in scene.cylinders]
    for oid, t_obj, n_obj in hits:
        closer = t_obj < t
        t = np.where(closer, t_obj, t)
        ids = np.where(closer, oid, ids)
        n[closer] = n_obj[closer]
    return t, ids, n
