"""plotly-Viewer: 3D-Ansicht (viewer_3d.html) und y-z-Schnitte mit x-Schieberegler (slices.html)."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from checker import FITS, NO_FIT, UNSURE, Candidate, Verdict
from config import Config
from fit import Fits
from scan import Scan, station_origin
from scene import NAMES, Scene
from voxels import FREE, OCCUPIED, UNKNOWN, GridSpec, boundary_mask, centers

if TYPE_CHECKING:
    from run import Twin

STATE_COLORS = {UNKNOWN: "#f2a33a", FREE: "#e8f1fa", OCCUPIED: "#1f3b57"}
STATE_NAMES = {UNKNOWN: "unbekannt", FREE: "frei", OCCUPIED: "belegt"}
VERDICT_COLORS = {FITS: "#2ca02c", UNSURE: "#ff9f1c", NO_FIT: "#d62728"}
STATION_COLORS = ["#1f77b4", "#9467bd", "#17becf", "#8c564b", "#e377c2", "#7f7f7f"]
STATE_LABELS = {"vorher": "Vorher (genutzte Stationen)", "nachher": "Nachher (+ empfohlene Station)"}


# --- Mesh-Bausteine ---

def box_mesh(los: list[np.ndarray], his: list[np.ndarray]):
    """Mehrere Boxen als ein Dreiecksnetz. Rückgabe: (verts (N,3), tris (M,3))."""
    corners = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]])
    faces = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                      [2, 3, 7], [2, 7, 6], [1, 2, 6], [1, 6, 5], [0, 3, 7], [0, 7, 4]])
    verts = [lo + corners * (hi - lo) for lo, hi in zip(los, his)]
    tris = [faces + 8 * k for k in range(len(verts))]
    if not verts:
        return np.zeros((0, 3)), np.zeros((0, 3), int)
    return np.concatenate(verts), np.concatenate(tris)


def cylinder_mesh(x0, x1, cy, cz, r, n: int = 32):
    """Mantel eines x-parallelen Zylinders."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring = np.column_stack([cy + r * np.cos(a), cz + r * np.sin(a)])
    verts = np.vstack([np.column_stack([np.full(n, x), ring]) for x in (x0, x1)])
    k = np.arange(n)
    k1 = (k + 1) % n
    tris = np.vstack([np.column_stack([k, k1, k + n]), np.column_stack([k1, k1 + n, k + n])])
    return verts, tris


def voxel_surface_mesh(spec: GridSpec, mask: np.ndarray):
    """Nur die Außenflächen einer Voxelmenge (innere Flächen werden weggelassen)."""
    padded = np.pad(mask, 1)
    verts, tris, offset = [], [], 0
    for ax in range(3):
        u, v = [a for a in range(3) if a != ax]
        for s in (-1, 1):
            neighbor = np.roll(padded, -s, axis=ax)[1:-1, 1:-1, 1:-1]
            idx = np.argwhere(mask & ~neighbor).astype(float)
            if not len(idx):
                continue
            idx[:, ax] += s > 0
            quad = np.repeat(idx[:, None, :], 4, axis=1)
            quad[:, [1, 2], u] += 1
            quad[:, [2, 3], v] += 1
            verts.append(quad.reshape(-1, 3))
            base = offset + 4 * np.arange(len(idx))[:, None]
            tris.append(np.vstack([base + [0, 1, 2], base + [0, 2, 3]]))
            offset += 4 * len(idx)
    if not verts:
        return np.zeros((0, 3)), np.zeros((0, 3), int)
    return spec.origin + np.concatenate(verts) * spec.size, np.concatenate(tris)


def mesh_trace(verts, tris, name, color, opacity, group, hovertext=None, showlegend=True) -> go.Mesh3d:
    return go.Mesh3d(x=verts[:, 0], y=verts[:, 1], z=verts[:, 2], i=tris[:, 0], j=tris[:, 1], k=tris[:, 2],
                     color=color, opacity=opacity, name=name, legendgroup=group, showlegend=showlegend,
                     flatshading=True, hovertext=hovertext, hoverinfo="text" if hovertext is not None else "name")


def wire_box(lo, hi):
    """12 Kanten einer Box als Linienzug mit None-Trennern."""
    c = lambda i: [lo[0] if i & 1 == 0 else hi[0], lo[1] if i & 2 == 0 else hi[1], lo[2] if i & 4 == 0 else hi[2]]
    edges = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
    pts = []
    for a, b in edges:
        pts += [c(a), c(b), [None] * 3]
    return pts


def wire_cylinder(x0, x1, cy, cz, r, n: int = 32):
    a = np.linspace(0, 2 * np.pi, n + 1)
    pts = []
    for x in (x0, x1):
        pts += [[x, cy + r * np.cos(t), cz + r * np.sin(t)] for t in a] + [[None] * 3]
    for t in a[:-1:4]:
        pts += [[x0, cy + r * np.cos(t), cz + r * np.sin(t)], [x1, cy + r * np.cos(t), cz + r * np.sin(t)], [None] * 3]
    return pts


def line3d(pts, name, color, group, width=3, dash=None) -> go.Scatter3d:
    p = np.array(pts, dtype=object)
    return go.Scatter3d(x=p[:, 0], y=p[:, 1], z=p[:, 2], mode="lines", name=name, legendgroup=group,
                        line=dict(color=color, width=width, dash=dash), hoverinfo="name")


# --- 3D-Viewer ---

def _state_traces(cfg: Config, spec: GridSpec, twin: Twin, cands: list[Candidate],
                  truth: list[Verdict]) -> list[go.BaseTraceType]:
    """Alle Ebenen, die vom Zustand (vorher/nachher) abhängen."""
    traces = []
    z0 = int(round((cfg.install_z - spec.origin[2]) / spec.size))
    region = np.zeros(spec.shape, bool)
    region[:, :, z0:] = True
    region &= ~boundary_mask(spec)   # Decke und Wände sind bekannt und würden alles verdecken
    for st, opacity in ((OCCUPIED, 0.7), (UNKNOWN, 0.35)):
        v, t = voxel_surface_mesh(spec, region & (twin.state == st))
        traces.append(mesh_trace(v, t, f"Voxel {STATE_NAMES[st]} (z > {cfg.install_z} m)",
                                 STATE_COLORS[st], opacity, f"vox{st}"))

    traces += _fit_traces(twin.fits)

    verdicts = twin.verdicts["unsicherheit"]
    for kind in ("flach", "hoch"):
        for label in (FITS, UNSURE, NO_FIT):
            sel = [(c, v, t) for c, v, t in zip(cands, verdicts, truth) if c.kind == kind and v.label == label]
            verts, tris = box_mesh([c.lo for c, _, _ in sel], [c.hi for c, _, _ in sel])
            text = [f"Modul {c.kind} x={c.x:.2f} y={c.y:.2f}<br>{v.label}: {v.reason}<br>Wahrheit: {t.label}"
                    for c, v, t in sel for _ in range(8)]
            traces.append(mesh_trace(verts, tris, f"Modul {kind}: {label} ({len(sel)})", VERDICT_COLORS[label],
                                     0.45, f"mod-{kind}-{label}", hovertext=text))
    return traces


def _fit_traces(fits: Fits) -> list[go.BaseTraceType]:
    traces = []
    verts, tris = box_mesh([b.lo for b in fits.boxes], [b.hi for b in fits.boxes])
    names = ", ".join(b.name for b in fits.boxes)
    traces.append(mesh_trace(verts, tris, f"Fit: Boxen ({names})", "#7f7fff", 0.3, "fitbox"))
    if fits.pipe:
        p = fits.pipe
        v, t = cylinder_mesh(p.x0, p.x1, p.cy, p.cz, p.r)
        traces.append(mesh_trace(v, t, f"Fit: Rohr Ø {2 * p.r * 1000:.1f} mm", "#7f7fff", 0.5, "fitpipe"))
    return traces


def _static_traces(cfg: Config, scene: Scene, scans: dict[str, Scan], twins: dict[str, Twin],
                   rec: str) -> tuple[list, list]:
    """Spuren für beide Zustände sowie nur „nachher" (Punkte der empfohlenen Station)."""
    both, after_only = [], []
    for k, (name, s) in enumerate(scans.items()):
        if name not in twins["nachher"].stations:
            continue
        p = s.points[:: cfg.viewer_point_step]
        tr = go.Scatter3d(x=p[:, 0], y=p[:, 1], z=p[:, 2], mode="markers", name=f"Punkte {name}",
                          legendgroup=f"pts{name}", marker=dict(size=1.2, color=STATION_COLORS[k % 6]),
                          hoverinfo="name", visible="legendonly")   # sonst verdecken Boden/Wände alles
        (after_only if name == rec else both).append(tr)

    truth_pts = []
    for b in scene.boxes:
        truth_pts += wire_box(b.lo, b.hi)
    for c in scene.cylinders:
        truth_pts += wire_cylinder(c.x0, c.x1, c.cy, c.cz, c.r)
    both.append(line3d(truth_pts, "Wahrheit (Gerät, Unterzug, Rohr, Kabeltrasse)", "black", "truth", 2))
    tray = [b for b in scene.boxes if NAMES[b.obj_id] == "Kabeltrasse"][0]
    both.append(line3d(wire_box(tray.lo, tray.hi), "Wahrheit: Kabeltrasse (versteckt)", "#e4007c", "tray", 6))
    both.append(line3d(wire_box(scene.room_lo, scene.room_hi), "Raum", "#aaaaaa", "room", 1))

    groups = [("genutzt", list(cfg.used), "#1f77b4", "circle", 6),
              ("Holdout", [h for h in cfg.holdout if h != rec], "#7f7f7f", "circle", 5),
              ("empfohlen", [rec], "#e4007c", "diamond", 10)]
    for label, names, color, symbol, size in groups:
        o = np.array([station_origin(cfg, n) for n in names]).reshape(-1, 3)
        both.append(go.Scatter3d(x=o[:, 0], y=o[:, 1], z=o[:, 2], mode="markers+text", text=names,
                                 textposition="top center", name=f"Stationen {label}",
                                 marker=dict(size=size, color=color, symbol=symbol), hoverinfo="text+name"))
    return both, after_only


def write_viewer_3d(path: Path, cfg: Config, scene: Scene, spec: GridSpec, scans: dict[str, Scan],
                    cands: list[Candidate], truth: list[Verdict], twins: dict[str, Twin], rec: str) -> None:
    both, after_only = _static_traces(cfg, scene, scans, twins, rec)
    before = _state_traces(cfg, spec, twins["vorher"], cands, truth)
    after = _state_traces(cfg, spec, twins["nachher"], cands, truth) + after_only
    # Sichtbarkeit je Zustand; "legendonly" (z. B. Punkte) bleibt beim Umschalten erhalten
    shown = lambda trs, on: [(t.visible if t.visible is not None else True) if on else False for t in trs]
    vis = {"vorher": shown(both, True) + shown(before, True) + shown(after, False),
           "nachher": shown(both, True) + shown(before, False) + shown(after, True)}

    fig = go.Figure(both + before + after)
    for tr, v in zip(fig.data, vis["vorher"]):
        tr.visible = v
    buttons = [dict(label=STATE_LABELS[k], method="update",
                    args=[{"visible": vis[k]}, {"title.text": _title_3d(k, rec)}]) for k in ("vorher", "nachher")]
    fig.update_layout(
        title=dict(text=_title_3d("vorher", rec), x=0.22),
        scene=dict(aspectmode="data", xaxis_title="x [m]", yaxis_title="y [m]", zaxis_title="z [m]",
                   camera=dict(eye=dict(x=-0.5, y=-1.5, z=-0.35), center=dict(x=0, y=0, z=0.15))),
        updatemenus=[dict(buttons=buttons, direction="down", x=0.0, y=1.0, xanchor="left", yanchor="bottom")],
        legend=dict(title="Ebenen (Klick = ein/aus)", itemsizing="constant"),
        margin=dict(l=0, r=0, t=80, b=0), height=850,
    )
    fig.write_html(path, include_plotlyjs=True)


def _title_3d(state: str, rec: str) -> str:
    extra = f" – Nachscan von {rec} hinzugefügt" if state == "nachher" else ""
    return (f"Sichtbarkeitsbewusster Zwilling{extra}<br><sub>Module: grün = passt, orange = unsicher, "
            f"rot = passt nicht (Unsicherheitsmodell). Hover zeigt Begründung und Wahrheit. "
            f"Punkte über die Legende einblenden.</sub>")


# --- Schnittansicht ---

def _yz_outlines(scene: Scene, x: float):
    """Echte Umrisse aller Objekte, die den Schnitt bei x schneiden."""
    ys, zs = [], []
    for b in scene.boxes:
        if b.lo[0] <= x <= b.hi[0]:
            ys += [b.lo[1], b.hi[1], b.hi[1], b.lo[1], b.lo[1], None]
            zs += [b.lo[2], b.lo[2], b.hi[2], b.hi[2], b.lo[2], None]
    for c in scene.cylinders:
        if c.x0 <= x <= c.x1:
            cy, cz = _circle(c.cy, c.cz, c.r)
            ys += cy + [None]
            zs += cz + [None]
    return ys, zs


def _circle(cy, cz, r, n: int = 64):
    a = np.linspace(0, 2 * np.pi, n + 1)
    return list(cy + r * np.cos(a)), list(cz + r * np.sin(a))


def _pipe_fit_lines(fits: Fits, x: float):
    """Gefitteter Rohrkreis und plausible Grenzen, falls das Rohr bei x liegt."""
    p = fits.pipe
    if p is None or not (p.x0 <= x <= p.x1):
        return [], [], [], []
    y, z = _circle(p.cy, p.cz, p.r)
    yb, zb = [], []
    for r in (p.plausible_radius(False), p.plausible_radius(True)):
        cy, cz = _circle(p.cy, p.cz, r)
        yb += cy + [None]
        zb += cz + [None]
    return y, z, yb, zb


def write_slices(path: Path, cfg: Config, scene: Scene, spec: GridSpec, twins: dict[str, Twin]) -> None:
    cx, cy, cz = centers(spec)
    keys = ["vorher", "nachher"]
    fig = make_subplots(rows=2, cols=1, vertical_spacing=0.08,
                        subplot_titles=[f"{STATE_LABELS[k]}: Stationen {', '.join(twins[k].stations)}" for k in keys])
    c0, c1, c2 = (STATE_COLORS[s] for s in (UNKNOWN, FREE, OCCUPIED))
    scale = [[0, c0], [1 / 3, c0], [1 / 3, c1], [2 / 3, c1], [2 / 3, c2], [1, c2]]

    # Statische Spuren: Legende der Zustände, Stationen (Projektion in y-z)
    for st in (FREE, OCCUPIED, UNKNOWN):
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=f"Voxel {STATE_NAMES[st]}",
                                 marker=dict(symbol="square", size=14, color=STATE_COLORS[st],
                                             line=dict(color="#555", width=1))), row=1, col=1)
    for row, k in enumerate(keys, start=1):
        names = twins[k].stations
        o = np.array([station_origin(cfg, n) for n in names])
        fig.add_trace(go.Scatter(x=o[:, 1], y=o[:, 2], mode="markers+text", text=names, textposition="top center",
                                 marker=dict(symbol="triangle-up", size=11, color="#e4007c"),
                                 name="Stationen (y-z-Projektion)", showlegend=row == 1,
                                 legendgroup="stations"), row=row, col=1)
    n_static = len(fig.data)

    slice_idx = list(range(0, spec.shape[0], cfg.slice_step))
    per_slice = 0
    for ix in slice_idx:
        x = cx[ix]
        before = len(fig.data)
        for row, k in enumerate(keys, start=1):
            fig.add_trace(go.Heatmap(x=cy, y=cz, z=twins[k].state[ix].T, zmin=0, zmax=2, colorscale=scale,
                                     showscale=False, visible=False, name="Voxel",
                                     customdata=np.vectorize(STATE_NAMES.get)(twins[k].state[ix].T),
                                     hovertemplate="y=%{x:.3f} z=%{y:.3f}: %{customdata}<extra></extra>"),
                          row=row, col=1)
            ty, tz = _yz_outlines(scene, x)
            fig.add_trace(go.Scatter(x=ty, y=tz, mode="lines", line=dict(color="black", width=1.5),
                                     name="Wahrheit (Umrisse)", visible=False, showlegend=row == 1,
                                     legendgroup="truth", hoverinfo="skip"), row=row, col=1)
            py, pz, by, bz = _pipe_fit_lines(twins[k].fits, x)
            fig.add_trace(go.Scatter(x=py, y=pz, mode="lines", line=dict(color="#d62728", width=2),
                                     name="Rohr-Fit (nominal)", visible=False, showlegend=row == 1,
                                     legendgroup="fit", hoverinfo="skip"), row=row, col=1)
            fig.add_trace(go.Scatter(x=by, y=bz, mode="lines", line=dict(color="#d62728", width=1, dash="dot"),
                                     name="Rohr: kleinstes/größtes plausibles", visible=False, showlegend=row == 1,
                                     legendgroup="fitci", hoverinfo="skip"), row=row, col=1)
        per_slice = len(fig.data) - before

    default = int(np.argmin(np.abs(cx[slice_idx] - 2.0)))   # x ≈ 2 m: Kabeltrasse im Rohrschatten
    steps = []
    for s, ix in enumerate(slice_idx):
        vis = [True] * n_static + [False] * per_slice * len(slice_idx)
        for t in range(per_slice):
            vis[n_static + s * per_slice + t] = True
        steps.append(dict(method="update", args=[{"visible": vis}], label=f"{cx[ix]:.2f}"))
    for t in range(per_slice):
        fig.data[n_static + default * per_slice + t].visible = True

    for row in (1, 2):
        fig.update_xaxes(title_text="y [m]", range=[0, spec.shape[1] * spec.size], row=row, col=1)
        fig.update_yaxes(title_text="z [m]", range=[1.2, 3.05], scaleanchor=f"x{'' if row == 1 else row}",
                         scaleratio=1, row=row, col=1)
    fig.update_layout(
        title=("Schnitt in der y-z-Ebene – Rohrschatten und versteckte Kabeltrasse<br><sub>Orange = unbekannt "
               "(kein Strahl hat hier etwas gesehen). Zoomen: Rahmen aufziehen, Doppelklick = zurück.</sub>"),
        sliders=[dict(active=default, steps=steps, currentvalue=dict(prefix="Schnitt bei x = ", suffix=" m"),
                      pad=dict(t=40))],
        height=1000, plot_bgcolor="white", margin=dict(t=110),
    )
    fig.write_html(path, include_plotlyjs=True)
