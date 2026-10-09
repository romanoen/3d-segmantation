"""Ablauf: scannen → Gitter → Fits → Checker → Kennzahlen → NBV-Vergleich → HTML.

Start: python run.py --used S0,S1,S2 --holdout S3,S4,S5 --voxel 0.05 --res 0.5 --seed 0
"""
from __future__ import annotations

import argparse
import dataclasses
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import viewer
from checker import UNSURE, VARIANTS, Candidate, Verdict, judge_all, judge_truth, make_candidates, metrics
from config import Config
from fit import Fits, fit_all
from nbv import choose, score_stations, task_mask
from scan import Scan, scan_station
from scene import NAMES, ROOM_IDS, TRAY, Scene, make_scene
from voxels import UNKNOWN, Carving, GridSpec, build_grid, carve_station, make_spec


@dataclass
class Twin:
    """Zwilling aus einer Menge von Stationen."""
    stations: list[str]
    state: np.ndarray
    fits: Fits
    verdicts: dict[str, list[Verdict]]


def make_twin(cfg: Config, names: list[str], scans: dict[str, Scan], carvings: dict[str, Carving],
              spec: GridSpec, cands: list[Candidate]) -> Twin:
    rng = np.random.default_rng(cfg.seed + 1)   # gleicher Bootstrap-Seed für jeden Zwilling
    state = build_grid(spec, [carvings[n] for n in names])
    fits = fit_all([scans[n] for n in names], cfg, rng)
    return Twin(list(names), state, fits, judge_all(cands, fits, spec, state, cfg))


def parse_args() -> Config:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--used", default=None, help="genutzte Stationen, z. B. S0,S1,S2")
    ap.add_argument("--holdout", default=None, help="Kandidaten für den Nachscan, z. B. S3,S4,S5")
    ap.add_argument("--voxel", type=float, default=None, help="Voxelgröße in m")
    ap.add_argument("--res", type=float, default=None, help="Winkelauflösung des Scanners in Grad")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    over = {"used": a.used and tuple(a.used.split(",")), "holdout": a.holdout and tuple(a.holdout.split(",")),
            "voxel": a.voxel, "angular_res": a.res, "seed": a.seed}
    return dataclasses.replace(Config(), **{k: v for k, v in over.items() if v is not None})


# --- Ausgaben ---

def print_table(header: list[str], rows: list[list]) -> None:
    fmt = lambda v: f"{v:.2f}" if isinstance(v, float) else str(v)
    rows = [[fmt(v) for v in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(header)]
    print("  " + "  ".join(h.ljust(w) for h, w in zip(header, widths)))
    for r in rows:
        print("  " + "  ".join(v.ljust(w) for v, w in zip(r, widths)))


def print_scan_summary(cfg: Config, scans: dict[str, Scan], spec: GridSpec, state: np.ndarray) -> None:
    print("\nPunkte pro Objekt und Station (Objekt-ID = Orakel-Segmentierung):")
    objs = ["Raum"] + [NAMES[i] for i in range(6, 10)]
    rows = []
    for name, s in scans.items():
        room = int(np.isin(s.obj_id, ROOM_IDS).sum())
        rows.append([name + (" (genutzt)" if name in cfg.used else " (holdout)"), room]
                    + [int(np.sum(s.obj_id == i)) for i in range(6, 10)])
    print_table(["Station"] + objs, rows)

    z0 = int(round((cfg.install_z - spec.origin[2]) / spec.size))
    inst = state[:, :, z0:]
    print(f"\nUNKNOWN-Anteil im Installationsbereich (z > {cfg.install_z} m): {np.mean(inst == UNKNOWN):.1%}")
    n_tray = sum(int(np.sum(scans[n].obj_id == TRAY)) for n in cfg.used)
    seen_by = [n for n in cfg.holdout if np.sum(scans[n].obj_id == TRAY) >= cfg.min_points]
    print(f"Kabeltrasse von genutzten Stationen erfasst: {'ja' if n_tray >= cfg.min_points else 'nein'} "
          f"({n_tray} Punkte); sichtbar von Holdout: {', '.join(seen_by) or '–'}")


def print_fits(cfg: Config, fits: Fits) -> None:
    print("\nGefittete Primitive:")
    for b in fits.boxes:
        print(f"  {b.name:<12} {np.round(b.lo, 3)} – {np.round(b.hi, 3)}  ({b.n_points} Punkte)")
    print(f"  nicht erkannt: {', '.join(fits.missing) or '–'}")
    p = fits.pipe
    if p:
        mm = lambda v: v * 1000
        print(f"  Rohr: Ø {mm(2 * p.r):.1f} mm (wahr {mm(cfg.pipe_diameter):.1f}), "
              f"95%-KI Ø [{mm(2 * p.r_ci[0]):.1f}, {mm(2 * p.r_ci[1]):.1f}] mm, "
              f"Mitte y/z = {p.cy:.4f}/{p.cz:.4f}, Oberkante {p.top:.4f} "
              f"[{p.top_ci[0]:.4f}, {p.top_ci[1]:.4f}] (wahr {cfg.pipe_center_yz[1] + cfg.pipe_radius:.4f}), "
              f"gesehener Umfang {p.seen_fraction:.0%}")
        print(f"  plausible Radien (inkl. systematischem Zuschlag {mm(p.sys_margin):.1f} mm): "
              f"{mm(p.plausible_radius(False)):.1f} … {mm(p.plausible_radius(True)):.1f} mm")


def print_metrics(twin: Twin, truth: list[Verdict]) -> None:
    keys = ["passt", "passt nicht", "unsicher", "falsch-passt", "falsch-passt-nicht", "korrekt/entschieden"]
    rows = [["wahrheit"] + [metrics(truth, truth)[k] for k in keys]]
    rows += [[v] + [metrics(twin.verdicts[v], truth)[k] for k in keys] for v in VARIANTS]
    print_table(["Variante"] + keys, rows)


def main() -> None:
    cfg = parse_args()
    t0 = time.time()
    rng = np.random.default_rng(cfg.seed)
    scene: Scene = make_scene(cfg)
    spec = make_spec(cfg)
    print(f"Raster {spec.shape}, Voxel {cfg.voxel} m, Auflösung {cfg.angular_res}°, "
          f"genutzt {cfg.used}, holdout {cfg.holdout}")

    # 1) Scannen (alle Stationen, Holdout-Daten erst bei der Evaluation verwendet)
    scans = {n: scan_station(cfg, scene, n, rng) for n in (*cfg.used, *cfg.holdout)}
    # 2) Carving pro Station einmal; Zwillinge kombinieren die Masken
    carvings = {n: carve_station(cfg, spec, s) for n, s in scans.items()}
    print(f"Scan + Carving: {time.time() - t0:.1f} s")

    cands = make_candidates(cfg)
    truth = [judge_truth(c, scene, cfg) for c in cands]
    base = make_twin(cfg, list(cfg.used), scans, carvings, spec, cands)
    print_scan_summary(cfg, scans, spec, base.state)
    print_fits(cfg, base.fits)
    print(f"\nChecker ({len(cands)} Kandidaten, hohes Modul h = {cfg.tall_height * 1000:.0f} mm):")
    print_metrics(base, truth)

    # 3) Nachscan-Empfehlung
    task = task_mask(spec, cands, base.verdicts["unsicherheit"])
    scores = score_stations(cfg, spec, base.state, task)
    picks = choose(scores, rng)
    print("\nNBV-Vorhersage (nur aktuelles Gitter):")
    print_table(["Station", "UNKNOWN in unsicheren Modulen", "UNKNOWN gesamt"],
                [[n, s["task"], s["coverage"]] for n, s in scores.items()])

    # 4) Evaluation mit echten Holdout-Daten (für alle Holdouts = Rückschau-Referenz)
    after = {n: make_twin(cfg, [*cfg.used, n], scans, carvings, spec, cands) for n in cfg.holdout}
    unsure_before = sum(v.label == UNSURE for v in base.verdicts["unsicherheit"])
    rows = []
    for strategy, n in [*picks.items(), *((f"(rückschau {h})", h) for h in cfg.holdout)]:
        m = metrics(after[n].verdicts["unsicherheit"], truth)
        rows.append([strategy, n, unsure_before, m["unsicher"], unsure_before - m["unsicher"],
                     m["falsch-passt"], m["falsch-passt-nicht"]])
    print("\nNBV-Evaluation (Unsicherheitsmodell, gewählte Station tatsächlich hinzugefügt):")
    print_table(["Strategie", "Station", "unsicher vorher", "unsicher nachher", "geklärt",
                 "falsch-passt", "falsch-passt-nicht"], rows)

    rec = picks["aufgabe"]
    print(f"\nNach Hinzufügen der empfohlenen Station {rec}:")
    print_metrics(after[rec], truth)

    # 5) Viewer
    out = Path(cfg.out_dir)
    out.mkdir(exist_ok=True)
    states = {"vorher": base, "nachher": after[rec]}
    viewer.write_viewer_3d(out / "viewer_3d.html", cfg, scene, spec, scans, cands, truth, states, rec)
    viewer.write_slices(out / "slices.html", cfg, scene, spec, states)
    print(f"\nHTML geschrieben nach {out.resolve()}  (Gesamtlaufzeit {time.time() - t0:.1f} s)")


if __name__ == "__main__":
    main()
