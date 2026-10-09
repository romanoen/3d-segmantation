"""Modulkandidaten zwischen Rohr und Decke und vier Urteile: Wahrheit, Nominal, Puffer, Unsicherheit."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config import Config
from fit import Fits
from scene import NAMES, Scene
from voxels import OCCUPIED, GridSpec, box_fractions, box_mask, boundary_mask

FITS, NO_FIT, UNSURE = "passt", "passt nicht", "unsicher"
VARIANTS = ("nominal", "puffer", "unsicherheit")


@dataclass
class Candidate:
    idx: int
    kind: str                   # "flach" | "hoch"
    x: float
    y: float
    lo: np.ndarray
    hi: np.ndarray


@dataclass
class Verdict:
    label: str
    reason: str


def make_candidates(cfg: Config) -> list[Candidate]:
    """Raster aus x × y × Typ; Oberseite bündig mit der Decke."""
    ceiling = cfg.room[1][2]
    fx, fy = cfg.module_footprint
    start, stop, step = cfg.cand_x
    xs = np.round(np.arange(start, stop + 1e-9, step), 3)
    out = []
    for kind, h in (("flach", cfg.flat_height), ("hoch", cfg.tall_height)):
        for y in cfg.cand_y:
            for x in xs:
                lo = np.array([x - fx / 2, y - fy / 2, ceiling - h])
                hi = np.array([x + fx / 2, y + fy / 2, ceiling])
                out.append(Candidate(len(out), kind, float(x), float(y), lo, hi))
    return out


# --- Geometrie ---

def boxes_overlap(alo, ahi, blo, bhi) -> bool:
    return bool(np.all(alo < bhi) and np.all(blo < ahi))


def box_hits_pipe(lo, hi, x0, x1, cy, cz, r) -> bool:
    """Box gegen x-parallelen Zylinder: x-Überlappung und Abstand Achse–Rechteck (y-z) < r."""
    if not (lo[0] < x1 and x0 < hi[0]):
        return False
    ny, nz = np.clip(cy, lo[1], hi[1]), np.clip(cz, lo[2], hi[2])
    return bool(np.hypot(ny - cy, nz - cz) < r)


def _collisions(lo, hi, boxes, pipes) -> list[str]:
    """Namen aller kollidierenden Objekte. boxes: (name, lo, hi), pipes: (name, x0, x1, cy, cz, r)."""
    hits = [name for name, blo, bhi in boxes if boxes_overlap(lo, hi, blo, bhi)]
    hits += [name for name, *p in pipes if box_hits_pipe(lo, hi, *p)]
    return hits


# --- Urteile ---

def judge_truth(cand: Candidate, scene: Scene, cfg: Config) -> Verdict:
    """Analytisch gegen alle echten Objekte (inkl. Kabeltrasse). Decke wird nicht geprüft (Kontakt erlaubt)."""
    c = cfg.clearance
    boxes = [(NAMES[b.obj_id], b.lo, b.hi) for b in scene.boxes]
    pipes = [(NAMES[p.obj_id], p.x0, p.x1, p.cy, p.cz, p.r) for p in scene.cylinders]
    hits = _collisions(cand.lo - c, cand.hi + c, boxes, pipes)
    return Verdict(NO_FIT, "kollidiert mit " + ", ".join(hits)) if hits else Verdict(FITS, "frei")


def _fitted_geometry(fits: Fits, grow: float, pipe_r: float | None = None):
    boxes = [(b.name, b.lo - grow, b.hi + grow) for b in fits.boxes]
    pipes = []
    if fits.pipe:
        p = fits.pipe
        r = p.r if pipe_r is None else pipe_r
        pipes.append(("Rohr", p.x0 - grow, p.x1 + grow, p.cy, p.cz, r + grow))
    return boxes, pipes


def judge_fitted(cand: Candidate, fits: Fits, cfg: Config, grow: float) -> Verdict:
    """Nominal (grow = 0) bzw. fester Puffer: nur gefittete Primitive, Unbekanntes gilt als frei."""
    c = cfg.clearance
    hits = _collisions(cand.lo - c, cand.hi + c, *_fitted_geometry(fits, grow))
    if hits:
        return Verdict(NO_FIT, "kollidiert mit gefittetem " + ", ".join(hits))
    return Verdict(FITS, "keine Kollision mit gefitteten Primitiven")


def judge_uncertainty(cand: Candidate, fits: Fits, spec: GridSpec, state: np.ndarray,
                      cfg: Config) -> Verdict:
    """Sichtbarkeitsbewusst: belegte/unbekannte Voxel + plausible Rohrgrößen."""
    c = cfg.clearance
    inner = box_mask(spec, cand.lo, cand.hi) & ~boundary_mask(spec)   # Decke/Wände ausgenommen
    n_occ = int(np.sum(state[inner] == OCCUPIED))
    if n_occ:
        return Verdict(NO_FIT, f"{n_occ} belegte Voxel im Modul")
    box_hits = _collisions(cand.lo - c, cand.hi + c, _fitted_geometry(fits, 0.0)[0], [])
    if box_hits:
        return Verdict(NO_FIT, "kollidiert mit gefittetem " + ", ".join(box_hits))
    if fits.pipe:
        p = fits.pipe
        r_min, r_max = p.plausible_radius(False), p.plausible_radius(True)
        if _collisions(cand.lo - c, cand.hi + c, [], _fitted_geometry(fits, 0.0, r_min)[1]):
            return Verdict(NO_FIT, f"kollidiert schon mit kleinstem plausiblem Rohr (r={r_min*1000:.1f} mm)")
        if _collisions(cand.lo - c, cand.hi + c, [], _fitted_geometry(fits, 0.0, r_max)[1]):
            return Verdict(UNSURE, f"kollidiert mit größtem plausiblem Rohr (r={r_max*1000:.1f} mm)")
    unk = box_fractions(spec, state, cand.lo, cand.hi)["unknown"]
    if unk > cfg.unknown_threshold:
        return Verdict(UNSURE, f"{unk:.0%} des Volumens unbekannt")
    return Verdict(FITS, f"frei gesehen ({unk:.0%} unbekannt)")


def judge_all(cands: list[Candidate], fits: Fits, spec: GridSpec, state: np.ndarray,
              cfg: Config) -> dict[str, list[Verdict]]:
    return {
        "nominal": [judge_fitted(c, fits, cfg, 0.0) for c in cands],
        "puffer": [judge_fitted(c, fits, cfg, cfg.fixed_buffer) for c in cands],
        "unsicherheit": [judge_uncertainty(c, fits, spec, state, cfg) for c in cands],
    }


def metrics(verdicts: list[Verdict], truth: list[Verdict]) -> dict:
    """Zählungen, falsch-passt (gefährlich), falsch-passt-nicht (verschenkt), Anteil korrekt unter Entschiedenen."""
    lab = np.array([v.label for v in verdicts])
    tru = np.array([v.label for v in truth])
    decided = lab != UNSURE
    correct = np.sum(decided & (lab == tru))
    return {
        FITS: int(np.sum(lab == FITS)), NO_FIT: int(np.sum(lab == NO_FIT)), UNSURE: int(np.sum(lab == UNSURE)),
        "falsch-passt": int(np.sum((lab == FITS) & (tru == NO_FIT))),
        "falsch-passt-nicht": int(np.sum((lab == NO_FIT) & (tru == FITS))),
        "korrekt/entschieden": correct / max(int(decided.sum()), 1),
    }
