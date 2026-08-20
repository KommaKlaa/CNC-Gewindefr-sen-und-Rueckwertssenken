"""Direktes BSF-Werkstueck-Geometriemodell auf Werkstuecknullpunkt Z0 = 0.000.

Kein zweites Bezugsebenen-Modell. Alle Z-Werte sind absolute Koordinaten
im aktiven Werkstuecksystem (Z0 = 0).

STOERKONTUR_E_NC_MODEL = NOT_IMPLEMENTED
Die HEULE-Groesse "Stoerkontur E" wird nicht als NC-Formel verwendet und
nicht mit exit_edge_z gleichgesetzt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

Z0_CANONICAL = 0.0
DEFAULT_X_SAFETY_CLEARANCE_MM = 2.0
DEFAULT_ENTRY_CLEARANCE_MM = 1.0
DEFAULT_B_CLEARANCE_MM = 1.0
DEFAULT_FULL_CUT_OVERLAP_MM = 0.25
STOERKONTUR_E_NC_MODEL = "NOT_IMPLEMENTED"

PROCESS_SURFACE_RAW = "RAW_SURFACE"
PROCESS_SURFACE_EXIT = "EXIT_EDGE"


@dataclass(frozen=True)
class BSFWorkpieceGeometry:
    entry_edge_z: float
    exit_edge_z: float
    target_surface_z: float
    raw_surface_z: Optional[float]
    sink_depth: float
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
    process_surface_z: float
    process_surface_source: str  # RAW_SURFACE | EXIT_EDGE


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


def parse_required_finite_mm(text: str, field_name: str) -> float:
    value = parse_optional_finite_mm(text)
    if value is None:
        raise ValueError(f"{field_name} fehlt.")
    return value


def build_workpiece_geometry(
    *,
    entry_edge_z: float,
    exit_edge_z: float,
    target_surface_z: float,
    measurement_face_to_cutting_edge_mm: float,
    raw_surface_z: Optional[float] = None,
) -> BSFWorkpieceGeometry:
    """Reine Werkstueckgeometrie relativ zu Z0 = 0.000."""
    for name, value in (
        ("entry_edge_z", entry_edge_z),
        ("exit_edge_z", exit_edge_z),
        ("target_surface_z", target_surface_z),
        ("measurement_face_to_cutting_edge_mm", measurement_face_to_cutting_edge_mm),
    ):
        if not math.isfinite(value):
            raise ValueError(f"{name} muss endlich sein.")
    if raw_surface_z is not None and not math.isfinite(raw_surface_z):
        raise ValueError("raw_surface_z muss endlich sein.")

    if not (target_surface_z > exit_edge_z):
        raise ValueError(
            "Ziel-Senkflaeche muss in +Z groesser als die Bohrungs-Austrittskante sein "
            "(Rueckwaertssenken zur Spindel)."
        )

    sink_depth = target_surface_z - exit_edge_z
    programmed_measurement_face_z = target_surface_z - measurement_face_to_cutting_edge_mm

    material_removal: Optional[float] = None
    if raw_surface_z is not None:
        material_removal = target_surface_z - raw_surface_z
        if material_removal < 0:
            raise ValueError(
                "Die angegebene Rohflaeche liegt in Bearbeitungsrichtung "
                "bereits hinter der Ziel-Senkflaeche. "
                "Bitte Rohflaeche / Ist-Z und Ziel-Senkflaeche pruefen."
            )

    return BSFWorkpieceGeometry(
        entry_edge_z=float(entry_edge_z),
        exit_edge_z=float(exit_edge_z),
        target_surface_z=float(target_surface_z),
        raw_surface_z=None if raw_surface_z is None else float(raw_surface_z),
        sink_depth=float(sink_depth),
        material_removal=material_removal,
        programmed_measurement_face_z=float(programmed_measurement_face_z),
        measurement_face_to_cutting_edge_mm=float(measurement_face_to_cutting_edge_mm),
    )


def resolve_process_surface_z(
    *,
    exit_edge_z: float,
    raw_surface_z: Optional[float] = None,
) -> Tuple[float, str]:
    """Kanonische Prozesskontur fuer X/B/C: Rohflaeche wenn angegeben, sonst Austritt."""
    if raw_surface_z is not None:
        return float(raw_surface_z), PROCESS_SURFACE_RAW
    return float(exit_edge_z), PROCESS_SURFACE_EXIT


def compute_heule_process_positions(
    *,
    exit_edge_z: float,
    entry_edge_z: float,
    target_surface_z: float,
    measurement_face_to_cutting_edge_mm: float,
    deployment_length_al_mm: float,
    x_safety_clearance_mm: float,
    entry_clearance_mm: float,
    b_clearance_mm: float = DEFAULT_B_CLEARANCE_MM,
    full_cut_overlap_mm: float = DEFAULT_FULL_CUT_OVERLAP_MM,
    raw_surface_z: Optional[float] = None,
) -> BSFHeuleProcessPositions:
    """Berechnet A/X/B/C/D fuer die programmierte Vermessflaeche.

    Koordinatenmodell:
    - Werkstuecknullpunkt Z0 = 0.000
    - Werkzeug kommt von +Z und faehrt in -Z durch die Bohrung.
    - Rueckwaertssenken erfolgt in +Z Richtung.

    Prozesskontur (X/B/C):
    process_surface_z = raw_surface_z wenn vorhanden, sonst exit_edge_z

    Semantik:
    - A: Anfahrt vor Eintritt (entry-basiert)
    - X: Ausklappen hinter der realen Senkseiten-Kontur (AL+Sicherheit)
    - B: FIRST_APPROACH_TO_ACTUAL_RAW_SURFACE
    - C: INITIAL_CUT_RELATIVE_TO_ACTUAL_RAW_SURFACE
    - D: Ziel-Senkflaeche (target-basiert, unveraendert)

    Formeln:
    A = entry_edge_z + entry_clearance
    X = process_surface_z - AL - x_safety
    B = process_surface_z - Hs - b_clearance
    C = process_surface_z - Hs + full_cut_overlap
    D = target_surface_z - Hs
    """
    for name, value in (
        ("exit_edge_z", exit_edge_z),
        ("entry_edge_z", entry_edge_z),
        ("target_surface_z", target_surface_z),
        ("measurement_face_to_cutting_edge_mm", measurement_face_to_cutting_edge_mm),
        ("deployment_length_al_mm", deployment_length_al_mm),
        ("x_safety_clearance_mm", x_safety_clearance_mm),
        ("entry_clearance_mm", entry_clearance_mm),
        ("b_clearance_mm", b_clearance_mm),
        ("full_cut_overlap_mm", full_cut_overlap_mm),
    ):
        if not math.isfinite(value):
            raise ValueError(f"{name} muss endlich sein.")
    if raw_surface_z is not None and not math.isfinite(raw_surface_z):
        raise ValueError("raw_surface_z muss endlich sein.")
    if deployment_length_al_mm <= 0:
        raise ValueError("AL muss groesser 0 sein.")
    if x_safety_clearance_mm < 0:
        raise ValueError("Ausklapp-Sicherheitsabstand X muss >= 0 sein.")
    if entry_clearance_mm < 0:
        raise ValueError("Eintritts-Sicherheitsabstand A muss >= 0 sein.")
    if b_clearance_mm < 0:
        raise ValueError("B-Sicherheitsabstand muss >= 0 sein.")
    if full_cut_overlap_mm < 0:
        raise ValueError("Schneiden-Ueberdeckung C muss >= 0 sein.")
    if not (target_surface_z > exit_edge_z):
        raise ValueError(
            "Ziel-Senkflaeche muss in +Z groesser als die Bohrungs-Austrittskante sein."
        )

    hs = measurement_face_to_cutting_edge_mm
    process_surface_z, process_source = resolve_process_surface_z(
        exit_edge_z=exit_edge_z,
        raw_surface_z=raw_surface_z,
    )
    required_clear = deployment_length_al_mm + x_safety_clearance_mm

    x_face = process_surface_z - deployment_length_al_mm - x_safety_clearance_mm
    a_face = entry_edge_z + entry_clearance_mm
    b_face = process_surface_z - hs - b_clearance_mm
    c_face = process_surface_z - hs + full_cut_overlap_mm
    d_face = target_surface_z - hs
    x_clear_distance = process_surface_z - x_face

    if x_clear_distance + 1e-12 < required_clear:
        raise ValueError(
            "Position X verletzt AL+Sicherheitsabstand "
            f"(process_surface - X = {x_clear_distance:.3f} mm, erforderlich {required_clear:.3f} mm)."
        )
    if not (x_face < b_face < c_face < d_face):
        raise ValueError("Positionsinvariante verletzt: erwartet X < B < C < D.")

    return BSFHeuleProcessPositions(
        a_measurement_face_z=a_face,
        x_measurement_face_z=x_face,
        b_measurement_face_z=b_face,
        c_measurement_face_z=c_face,
        d_measurement_face_z=d_face,
        x_clear_distance=x_clear_distance,
        process_surface_z=process_surface_z,
        process_surface_source=process_source,
    )


def required_bsf_safe_z(heule_pos: BSFHeuleProcessPositions) -> float:
    """Mindest-Sicherheits-Z = max(A, X, B, C, D). Eine Source of Truth."""
    return max(
        heule_pos.a_measurement_face_z,
        heule_pos.x_measurement_face_z,
        heule_pos.b_measurement_face_z,
        heule_pos.c_measurement_face_z,
        heule_pos.d_measurement_face_z,
    )


def validate_bsf_safe_z_direct(
    safe_z: float,
    end_safe_z: float,
    heule_pos: BSFHeuleProcessPositions,
) -> Optional[str]:
    """safe_z muss oberhalb der hoechsten Prozesslage (typisch A) liegen."""
    if not math.isfinite(safe_z) or not math.isfinite(end_safe_z):
        return "Sicherheits-Z darf nicht NaN/Infinity sein."
    required = required_bsf_safe_z(heule_pos)
    if safe_z < required or end_safe_z < required:
        return (
            "Sicherheits-Z ist zu niedrig.\n\n"
            f"Erforderliches Minimum:\nZ{required:+.3f}\n\n"
            f"Aktuell:\nSicherheits-Z Z{safe_z:+.3f}\n"
            f"End-Sicherheits-Z Z{end_safe_z:+.3f}\n\n"
            "Bitte Sicherheits-Z bzw. End-Sicherheits-Z anpassen."
        )
    return None


# Didaktische Z0-Beispiele (identische Relativgeometrie).
Z0_EXAMPLE_TOP = {
    "name": "Z0 obere Flaeche",
    "entry_edge_z": 0.0,
    "exit_edge_z": -30.0,
    "target_surface_z": -22.0,
}
Z0_EXAMPLE_REAR = {
    "name": "Z0 hintere / innere Flaeche",
    "entry_edge_z": 30.0,
    "exit_edge_z": 0.0,
    "target_surface_z": 8.0,
}
Z0_EXAMPLE_BOTTOM = {
    "name": "Z0 untere Flaeche",
    "entry_edge_z": 90.0,
    "exit_edge_z": 60.0,
    "target_surface_z": 68.0,
}
Z0_EXAMPLES = (Z0_EXAMPLE_TOP, Z0_EXAMPLE_REAR, Z0_EXAMPLE_BOTTOM)
