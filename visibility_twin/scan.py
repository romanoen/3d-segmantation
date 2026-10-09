"""TLS-Simulation: Winkelraster, erster Treffer, einfallswinkelabhängiges Entfernungsrauschen."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config import Config
from scene import Scene, cast_rays


@dataclass
class Scan:
    station: str
    origin: np.ndarray      # (3,)
    points: np.ndarray      # (N,3)
    obj_id: np.ndarray      # (N,) ORAKEL: perfekte Segmentierung aus der Simulation
    # In echten Daten gibt es obj_id nicht – hier ersetzt sie eine Segmentierung.


def station_origin(cfg: Config, name: str) -> np.ndarray:
    x, y = cfg.stations[name]
    return np.array([x, y, cfg.station_height])


def ray_directions(res_deg: float, elev_range: tuple[float, float]) -> np.ndarray:
    """Einheitsvektoren auf einem Azimut × Elevation-Raster."""
    az = np.deg2rad(np.arange(0.0, 360.0, res_deg))
    el = np.deg2rad(np.arange(elev_range[0], elev_range[1] + 1e-9, res_deg))
    A, E = np.meshgrid(az, el, indexing="ij")
    A, E = A.ravel(), E.ravel()
    return np.stack([np.cos(E) * np.cos(A), np.cos(E) * np.sin(A), np.sin(E)], axis=1)


def scan_station(cfg: Config, scene: Scene, name: str, rng: np.random.Generator) -> Scan:
    o = station_origin(cfg, name)
    d = ray_directions(cfg.angular_res, cfg.elevation_range)
    t, ids, n = cast_rays(scene, o, d)
    cos_inc = np.abs(np.sum(d * n, axis=1))
    sigma = cfg.range_sigma / np.maximum(cos_inc, cfg.min_cos_incidence)
    r = t + rng.normal(0.0, 1.0, len(t)) * sigma
    return Scan(name, o, o + r[:, None] * d, ids)
