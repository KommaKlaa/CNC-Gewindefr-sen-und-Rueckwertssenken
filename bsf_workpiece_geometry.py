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


@dataclass(frozen=True)
class BSFHeuleProcessPositions:
    a_measurement_face_z: float
    x_measurement_face_z: float
    b_measurement_face_z: float
    c_measurement_face_z: float
    d_measurement_face_z: float
    x_clear_distance: float


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


def compute_heule_process_positions(
    *,
    deployment_edge_z: float,
    entry_edge_z: float,
    target_cutting_edge_z: float,
    measurement_face_to_cutting_edge_mm: float,
    deployment_length_al_mm: float,
    x_safety_clearance_mm: float,
    entry_clearance_mm: float,
    b_clearance_mm: float = 1.0,
    full_cut_overlap_mm: float = 0.25,
) -> BSFHeuleProcessPositions:
    """Berechnet A/X/B/C/D fuer die programmierte Vermessflaeche.

    Koordinatenmodell:
    - Werkzeug kommt von +Z und faehrt in -Z durch die Bohrung.
    - Rueckwaertssenken erfolgt in +Z Richtung.
    """
    for name, value in (
        ("deployment_edge_z", deployment_edge_z),
        ("entry_edge_z", entry_edge_z),
        ("target_cutting_edge_z", target_cutting_edge_z),
        ("measurement_face_to_cutting_edge_mm", measurement_face_to_cutting_edge_mm),
        ("deployment_length_al_mm", deployment_length_al_mm),
        ("x_safety_clearance_mm", x_safety_clearance_mm),
        ("entry_clearance_mm", entry_clearance_mm),
        ("b_clearance_mm", b_clearance_mm),
        ("full_cut_overlap_mm", full_cut_overlap_mm),
    ):
        if not math.isfinite(value):
            raise ValueError(f"{name} muss endlich sein.")
    if deployment_length_al_mm <= 0:
        raise ValueError("AL muss groesser 0 sein.")
    if x_safety_clearance_mm < 0:
        raise ValueError("Ausklapp-Sicherheitsabstand X muss >= 0 sein.")
    if entry_clearance_mm < 0:
        raise ValueError("Eintritts-Sicherheitsabstand A muss >= 0 sein.")

    hs = measurement_face_to_cutting_edge_mm

    # HEULE-X: X = E - AL - safety (auf Vermessflaeche, ohne Hs-Zusatzabzug)
    x_face = deployment_edge_z - deployment_length_al_mm - x_safety_clearance_mm
    a_face = entry_edge_z + entry_clearance_mm
    b_face = deployment_edge_z - hs - b_clearance_mm
    c_face = deployment_edge_z - hs + full_cut_overlap_mm
    d_face = target_cutting_edge_z - hs
    x_clear_distance = deployment_edge_z - x_face

    if x_clear_distance < deployment_length_al_mm + x_safety_clearance_mm:
        raise ValueError("Position X verletzt AL+Sicherheitsabstand.")
    if not (x_face < b_face < c_face < d_face):
        raise ValueError("Positionsinvariante verletzt: erwartet X < B < C < D.")

    return BSFHeuleProcessPositions(
        a_measurement_face_z=a_face,
        x_measurement_face_z=x_face,
        b_measurement_face_z=b_face,
        c_measurement_face_z=c_face,
        d_measurement_face_z=d_face,
        x_clear_distance=x_clear_distance,
    )
