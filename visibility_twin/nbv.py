"""Nachscan-Empfehlung: Vorhersage nur aus dem aktuellen Gitter (kein Spicken in die Holdout-Daten)."""
from __future__ import annotations

import numpy as np

from checker import UNSURE, Candidate, Verdict
from config import Config
from scan import ray_directions, station_origin
from scene import ray_room_exit
from voxels import OCCUPIED, UNKNOWN, GridSpec, box_mask, to_flat, to_index


def predict_seen_unknown(cfg: Config, spec: GridSpec, state: np.ndarray, origin: np.ndarray) -> np.ndarray:
    """UNKNOWN-Voxel (flache bool-Maske), die von origin aus sichtbar würden.
    UNKNOWN gilt als durchsichtig, OCCUPIED und die Raumgrenze stoppen den Strahl."""
    flat_state = state.ravel()
    seen = np.zeros(spec.n, bool)
    d = ray_directions(cfg.nbv_res, cfg.elevation_range)
    t_exit, _, _ = ray_room_exit(origin, d, spec.origin, spec.origin + np.array(spec.shape) * spec.size)
    t = np.arange(0.0, t_exit.max(), spec.size / 2)
    for start in range(0, len(d), cfg.carve_block):
        u = d[start:start + cfg.carve_block]
        samples = origin + t[None, :, None] * u[:, None, :]          # (B,S,3)
        idx = to_flat(spec, to_index(spec, samples))                  # (B,S)
        valid = t[None, :] < t_exit[start:start + cfg.carve_block, None]
        st = flat_state[idx]
        blocked = np.cumsum(st == OCCUPIED, axis=1) > 0
        hit_unknown = valid & ~blocked & (st == UNKNOWN)
        seen[idx[hit_unknown]] = True
    return seen


def task_mask(spec: GridSpec, cands: list[Candidate], verdicts: list[Verdict]) -> np.ndarray:
    """Vereinigung der Voxel aller aktuell unsicheren Kandidaten (flach)."""
    m = np.zeros(spec.shape, bool)
    for c, v in zip(cands, verdicts):
        if v.label == UNSURE:
            m |= box_mask(spec, c.lo, c.hi)
    return m.ravel()


def score_stations(cfg: Config, spec: GridSpec, state: np.ndarray, task: np.ndarray) -> dict[str, dict]:
    """Pro Holdout-Station: aufgabenbezogener Score und Abdeckungs-Score."""
    out = {}
    for name in cfg.holdout:
        seen = predict_seen_unknown(cfg, spec, state, station_origin(cfg, name))
        out[name] = {"task": int(np.sum(seen & task)), "coverage": int(seen.sum())}
    return out


def choose(scores: dict[str, dict], rng: np.random.Generator) -> dict[str, str]:
    """Wahl je Strategie: Aufgabe, Abdeckung, Zufall."""
    names = sorted(scores)
    return {
        "aufgabe": max(names, key=lambda s: scores[s]["task"]),
        "abdeckung": max(names, key=lambda s: scores[s]["coverage"]),
        "zufall": str(rng.choice(names)),
    }
