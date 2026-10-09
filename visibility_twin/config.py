"""Zentrale Parameter des Prototyps. Alle Längen in Metern, Winkel in Grad."""
from __future__ import annotations

from dataclasses import dataclass, field

Vec3 = tuple[float, float, float]
BoxSpec = tuple[Vec3, Vec3]  # (min, max)


@dataclass(frozen=True)
class Config:
    seed: int = 0

    # --- Szene ---
    room: BoxSpec = ((0.0, 0.0, 0.0), (6.0, 4.0, 3.0))
    device: BoxSpec = ((3.5, 0.0, 0.0), (4.5, 0.8, 1.6))
    beam: BoxSpec = ((2.8, 0.0, 2.6), (3.1, 4.0, 3.0))
    pipe_x: tuple[float, float] = (0.5, 5.5)
    pipe_center_yz: tuple[float, float] = (1.0, 2.6)
    pipe_diameter: float = 0.114
    # Kabeltrasse: gegenüber der Vorgabe (y 0.75–0.95, z 2.78–2.86) verschoben und
    # verkleinert, damit sie vollständig im Rohrschatten der Stationen S0–S2 liegt
    # (der Schatten fällt schräg nach -y/oben, siehe README).
    tray: BoxSpec = ((1.5, 0.74, 2.675), (4.0, 0.84, 2.725))

    # --- Scanner ---
    stations: dict[str, tuple[float, float]] = field(default_factory=lambda: {
        "S0": (1.0, 3.0), "S1": (3.0, 3.2), "S2": (5.0, 3.0),
        "S3": (2.0, 0.4), "S4": (5.3, 1.6), "S5": (0.6, 1.8),
    })
    station_height: float = 1.5
    used: tuple[str, ...] = ("S0", "S1", "S2")
    holdout: tuple[str, ...] = ("S3", "S4", "S5")
    angular_res: float = 0.5               # Grad, Azimut und Elevation
    elevation_range: tuple[float, float] = (-60.0, 90.0)  # Totkegel unter dem Scanner
    range_sigma: float = 0.003             # σ bei senkrechtem Auftreffen
    min_cos_incidence: float = 0.25        # Deckel für das Rauschen bei streifendem Einfall

    # --- Voxelgitter ---
    voxel: float = 0.05
    carve_stride: int = 1                  # nur jeder n-te Strahl wird fürs Carving genutzt
    carve_margin_vox: float = 1.0          # FREE endet so viele Voxel vor dem Treffer
    carve_block: int = 4096                # Strahlen pro Vektorisierungsblock

    # --- Fits ---
    min_points: int = 20
    bootstrap_reps: int = 200
    gn_iters: int = 10
    # Bootstrap erfasst nur Streuung, nicht den Bias durch richtungsabhängiges Rauschen
    # bei Teilansicht (≈ −0.5 mm im Radius). Zuschlag auf die plausiblen Radien:
    # pipe_sys_margin · (1 − gesehener Umfangsanteil), Größenordnung Sensor-σ.
    pipe_sys_margin: float = 0.003

    # --- Checker ---
    clearance: float = 0.02
    module_footprint: tuple[float, float] = (0.30, 0.25)   # (x, y)
    flat_height: float = 0.15
    tall_margin: float = 0.001             # Luft des hohen Moduls über Rohr + Clearance
    cand_x: tuple[float, float, float] = (0.6, 5.4, 0.3)   # start, stop, step
    cand_y: tuple[float, ...] = (0.85, 1.0, 1.15)
    fixed_buffer: float = 0.05
    unknown_threshold: float = 0.02        # max. UNKNOWN-Volumenanteil für „passt"

    # --- NBV / Viewer ---
    nbv_res: float = 1.0                   # Winkelauflösung der Vorhersage-Strahlen
    install_z: float = 2.3                 # Installationsbereich z > install_z
    viewer_point_step: int = 15            # nur jeder n-te Punkt im 3D-Viewer
    slice_step: int = 2                    # jeder n-te Voxelschnitt im Schnittviewer
    out_dir: str = "out"

    @property
    def pipe_radius(self) -> float:
        return self.pipe_diameter / 2

    @property
    def tall_height(self) -> float:
        """Hohes Modul endet tall_margin über echtem Rohr + Clearance."""
        pipe_top = self.pipe_center_yz[1] + self.pipe_radius
        return self.room[1][2] - (pipe_top + self.clearance + self.tall_margin)
