"""Reines BSF-Werkstueck-Geometriemodell (ohne GUI-Abhaengigkeit)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BSFWorkpieceGeometry:
    reference_z: float
    sink_finish: float
    raw_surface_z: Optional[float]
    target_cutting_edge_z: float
    material_removal: Optional[float]
    programmed_measurement_face_z: float
    measurement_face_to_cutting_edge_mm: float


def parse_optional_finite_mm(text: str) -> Optional[float]:
    raw = (text or "").strip()
    if raw == "":
        return None
    try:
        value = float(raw.replace(",", "."))
    except ValueError as exc:
        raise ValueError("Wert muss numerisch sein.") from exc
    if not math.isfinite(value):
        raise ValueError("Wert muss endlich sein (kein NaN/Inf).")
    return value


def build_workpiece_geometry(
    *,
    reference_z: float,
    sink_finish: float,
    measurement_face_to_cutting_edge_mm: float,
    raw_surface_z: Optional[float] = None,
) -> BSFWorkpieceGeometry:
    """Berechnet Ziel-Schneidenlage und Vermessflaechen-Z.

    Hinweis: Dieses Modell ist eine geometrische Hilfsdarstellung.
    Die bestehende NC-Logik bleibt in dieser Phase unveraendert.
    """
    for name, value in (
        ("reference_z", reference_z),
        ("sink_finish", sink_finish),
        ("measurement_face_to_cutting_edge_mm", measurement_face_to_cutting_edge_mm),
    ):
        if not math.isfinite(value):
            raise ValueError(f"{name} muss endlich sein.")
    if raw_surface_z is not None and not math.isfinite(raw_surface_z):
        raise ValueError("raw_surface_z muss endlich sein.")

    # Fertigmaß ab Bezugsebene: reale Schneidenlage.
    target_cutting_edge_z = reference_z + sink_finish
    programmed_measurement_face_z = target_cutting_edge_z - measurement_face_to_cutting_edge_mm

    material_removal: Optional[float] = None
    if raw_surface_z is not None:
        material_removal = target_cutting_edge_z - raw_surface_z
        if material_removal < 0:
            raise ValueError(
                "Die angegebene Rohflaeche liegt in Bearbeitungsrichtung "
                "bereits hinter der Ziel-Senkflaeche. "
                "Bitte Bezugsebene, Rohmaß und Fertigmaß pruefen."
            )

    return BSFWorkpieceGeometry(
        reference_z=reference_z,
        sink_finish=sink_finish,
        raw_surface_z=raw_surface_z,
        target_cutting_edge_z=target_cutting_edge_z,
        material_removal=material_removal,
        programmed_measurement_face_z=programmed_measurement_face_z,
        measurement_face_to_cutting_edge_mm=measurement_face_to_cutting_edge_mm,
    )
