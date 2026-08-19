"""Katalogisierte HEULE-BSF-Werkzeugprofile und Werkzeug-Stirnflaechenvermessung."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional


MEASUREMENT_MODEL = "TOOL_END_MEASUREMENT_FACE"
MEASUREMENT_LABEL = "Werkzeug-Stirnfläche"
MEASUREMENT_DETAIL_LABEL = "Untere Werkzeug-Stirnfläche"
MEASUREMENT_NC_COMMENT = "WERKZEUG-STIRNFLAECHE"
MEASUREMENT_OFFSET_DIRECTION = "+Z zur Spindel"
TOOL_SELECTION_REQUIRED = "--- bitte HEULE-Werkzeug waehlen ---"


@dataclass(frozen=True)
class BSFToolProfile:
    key: str
    designation: str
    family: str
    measurement_face_to_cutting_edge_mm: float
    deployment_length_al_mm: Optional[float]
    activation_speed_rpm: Optional[int]
    measurement_model: str = MEASUREMENT_MODEL


BSF_TOOL_PROFILES: Dict[str, BSFToolProfile] = {
    "BSF_C_1000_050_10_5_23": BSFToolProfile(
        key="BSF_C_1000_050_10_5_23",
        designation="BSF-C-1000/050-10.5-23",
        family="BSF-C",
        measurement_face_to_cutting_edge_mm=8.55,
        deployment_length_al_mm=20.250,
        activation_speed_rpm=2000,
    ),
    "BSF_E_1350_050_16_5_14": BSFToolProfile(
        key="BSF_E_1350_050_16_5_14",
        designation="BSF-E-1350/050-16.5-14",
        family="BSF-E",
        measurement_face_to_cutting_edge_mm=11.40,
        deployment_length_al_mm=26.750,
        activation_speed_rpm=1500,
    ),
}


def ordered_tool_profiles() -> tuple[BSFToolProfile, ...]:
    return tuple(BSF_TOOL_PROFILES.values())


def profile_options() -> tuple[str, ...]:
    return (TOOL_SELECTION_REQUIRED,) + tuple(profile.designation for profile in ordered_tool_profiles())


def profile_by_key(key: Optional[str]) -> Optional[BSFToolProfile]:
    if not key:
        return None
    return BSF_TOOL_PROFILES.get(key)


def profile_by_designation(designation: str) -> Optional[BSFToolProfile]:
    raw = (designation or "").strip()
    if raw == "" or raw == TOOL_SELECTION_REQUIRED:
        return None
    for profile in ordered_tool_profiles():
        if raw == profile.designation or raw == profile.key:
            return profile
    return None


def programmed_measurement_face_z_for_cutting_edge(
    target_cutting_edge_z: float, tool_profile: BSFToolProfile
) -> float:
    """Programmiert die untere Werkzeug-Stirnflaeche fuer eine gewuenschte Schneidenlage."""
    return float(target_cutting_edge_z) - float(tool_profile.measurement_face_to_cutting_edge_mm)


def cutting_edge_z_from_measurement_face_z(
    programmed_measurement_face_z: float, tool_profile: BSFToolProfile
) -> float:
    """Reale Schneidenlage aus programmierter Vermess-Stirnflaeche."""
    return float(programmed_measurement_face_z) + float(tool_profile.measurement_face_to_cutting_edge_mm)


def validate_profile_geometry(profile: BSFToolProfile) -> Optional[str]:
    if not isinstance(profile, BSFToolProfile):
        return "Unbekanntes HEULE-Werkzeugprofil."
    value = float(profile.measurement_face_to_cutting_edge_mm)
    if not math.isfinite(value) or value <= 0:
        return "HEULE-Werkzeugprofil enthaelt ungueltige Vermessflaeche/Schneiden-Geometrie."
    return None


def apply_measurement_face_offset(target_cutting_edge_z: dict, tool_profile: BSFToolProfile) -> dict:
    """Uebersetzt Schneiden-Ziele in programmierte Vermesspunkt-Z-Lagen."""
    err = validate_profile_geometry(tool_profile)
    if err:
        raise ValueError(err)
    return {
        "z_sink_finish": programmed_measurement_face_z_for_cutting_edge(
            target_cutting_edge_z["z_sink_finish"], tool_profile
        ),
        "z_clearance": programmed_measurement_face_z_for_cutting_edge(
            target_cutting_edge_z["z_clearance"], tool_profile
        ),
    }


# Abwaertskompatibilitaet fuer interne Importe waehrend der Migration.
programmed_holder_z_for_cutting_edge = programmed_measurement_face_z_for_cutting_edge
cutting_edge_z_from_holder_z = cutting_edge_z_from_measurement_face_z
apply_holder_offset = apply_measurement_face_offset
