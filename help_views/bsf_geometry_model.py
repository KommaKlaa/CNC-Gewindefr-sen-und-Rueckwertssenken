"""Read-only Snapshot fuer die HEULE-BSF-Senkgeometrie-Hilfe (direktes Z0-Modell)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from bsf_workpiece_geometry import (
    STOERKONTUR_E_NC_MODEL,
    Z0_CANONICAL,
    Z0_EXAMPLES,
    build_workpiece_geometry,
    compute_heule_process_positions,
    parse_optional_finite_mm,
    required_bsf_safe_z,
)
from ui.bsf_safe_status import STATUS_INCOMPLETE, evaluate_bsf_safe_z_status
from heule_bsf_tools import (
    BSFToolProfile,
    MEASUREMENT_LABEL,
    MEASUREMENT_OFFSET_DIRECTION,
    profile_by_designation,
)


def _parse_optional_mm(text: str) -> Optional[float]:
    raw = (text or "").strip()
    if raw == "":
        return None
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def fmt_mm(value: Optional[float], *, decimals: int = 3) -> str:
    if value is None:
        return "—"
    return f"{value:.{decimals}f} mm"


def fmt_axis_z(value: Optional[float]) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.4f}"


def status_headline(snapshot: "BSFGeometryHelpSnapshot") -> str:
    return "NC-STATUS: BLOCKIERT" if snapshot.nc_blocked else "NC-STATUS: FREIGEGEBEN"


def status_detail(snapshot: "BSFGeometryHelpSnapshot") -> str:
    return " · ".join(snapshot.notes)


@dataclass(frozen=True)
class BSFGeometryHelpSnapshot:
    entry_edge_z: Optional[float]
    exit_edge_z: Optional[float]
    target_surface_z: Optional[float]
    raw_surface_z: Optional[float]
    sink_depth: Optional[float]
    tool_profile: Optional[BSFToolProfile]
    material_removal: Optional[float]
    programmed_measurement_face_z_target: Optional[float]
    a_z: Optional[float]
    x_z: Optional[float]
    b_z: Optional[float]
    c_z: Optional[float]
    d_z: Optional[float]
    nc_blocked: bool
    notes: List[str] = field(default_factory=list)
    z0: float = Z0_CANONICAL
    stoerkontur_e_nc_model: str = STOERKONTUR_E_NC_MODEL
    z0_examples: tuple = Z0_EXAMPLES
    safe_z: Optional[float] = None
    end_safe_z: Optional[float] = None
    required_safe_z: Optional[float] = None
    safe_status: str = STATUS_INCOMPLETE
    safe_headline: str = "— Geometrie noch unvollstaendig"
    x_safety_clearance: Optional[float] = None
    entry_clearance: Optional[float] = None
    full_cut_overlap: Optional[float] = None

    @property
    def target_cutting_edge_z(self) -> Optional[float]:
        return self.target_surface_z

    @property
    def programmed_measurement_face_z_sink_finish(self) -> Optional[float]:
        return self.d_z

    @property
    def reference_z(self) -> float:
        return self.z0


def build_bsf_geometry_help_snapshot(
    *,
    entry_text: str = "",
    exit_text: str = "",
    target_text: str = "",
    raw_surface_z_text: str = "",
    x_safety_text: str = "2.000",
    entry_clearance_text: str = "1.000",
    overlap_text: str = "0.250",
    tool_designation: str = "",
    safe_z_text: str = "",
    end_safe_z_text: str = "",
    **_legacy_ignored,
) -> BSFGeometryHelpSnapshot:
    """Baut den Hilfesnapshot aus GUI-Texten. Keine Dialoge, keine erfundenen Werte."""
    entry_z = _parse_optional_mm(entry_text)
    exit_z = _parse_optional_mm(exit_text)
    target_z = _parse_optional_mm(target_text)
    tool_profile = profile_by_designation(tool_designation)
    try:
        raw_surface_z = parse_optional_finite_mm(raw_surface_z_text)
    except ValueError:
        raw_surface_z = None
    x_safety = _parse_optional_mm(x_safety_text)
    entry_clearance = _parse_optional_mm(entry_clearance_text)
    overlap = _parse_optional_mm(overlap_text)
    safe_z = _parse_optional_mm(safe_z_text)
    end_safe_z = _parse_optional_mm(end_safe_z_text)

    notes: List[str] = []
    if entry_z is None:
        notes.append("Eintrittskante fehlt")
    if exit_z is None:
        notes.append("Austrittskante fehlt")
    if target_z is None:
        notes.append("Ziel-Senkflaeche fehlt")
    if tool_profile is None:
        notes.append("HEULE Werkzeug fehlt")
    if (raw_surface_z_text or "").strip() and raw_surface_z is None:
        notes.append("Rohflaeche / Ist-Z ungueltig")

    sink_depth = None
    material_removal = None
    programmed_target = None
    a_z = x_z = b_z = c_z = d_z = None
    heule_pos = None
    if None not in (entry_z, exit_z, target_z) and tool_profile is not None:
        try:
            geom = build_workpiece_geometry(
                entry_edge_z=entry_z,
                exit_edge_z=exit_z,
                target_surface_z=target_z,
                raw_surface_z=raw_surface_z,
                measurement_face_to_cutting_edge_mm=tool_profile.measurement_face_to_cutting_edge_mm,
            )
            sink_depth = geom.sink_depth
            material_removal = geom.material_removal
            programmed_target = geom.programmed_measurement_face_z
            heule_pos = compute_heule_process_positions(
                exit_edge_z=exit_z,
                entry_edge_z=entry_z,
                target_surface_z=target_z,
                measurement_face_to_cutting_edge_mm=tool_profile.measurement_face_to_cutting_edge_mm,
                deployment_length_al_mm=tool_profile.deployment_length_al_mm or 0.0,
                x_safety_clearance_mm=x_safety if x_safety is not None else 2.0,
                entry_clearance_mm=entry_clearance if entry_clearance is not None else 1.0,
                full_cut_overlap_mm=overlap if overlap is not None else 0.25,
            )
            a_z = heule_pos.a_measurement_face_z
            x_z = heule_pos.x_measurement_face_z
            b_z = heule_pos.b_measurement_face_z
            c_z = heule_pos.c_measurement_face_z
            d_z = heule_pos.d_measurement_face_z
        except ValueError as exc:
            notes.append(str(exc))

    required = required_bsf_safe_z(heule_pos) if heule_pos is not None else None
    safe_eval = evaluate_bsf_safe_z_status(
        heule_pos=heule_pos,
        safe_z=safe_z,
        end_safe_z=end_safe_z,
    )

    nc_blocked = (
        entry_z is None
        or exit_z is None
        or target_z is None
        or tool_profile is None
        or a_z is None
    )

    return BSFGeometryHelpSnapshot(
        entry_edge_z=entry_z,
        exit_edge_z=exit_z,
        target_surface_z=target_z,
        raw_surface_z=raw_surface_z,
        sink_depth=sink_depth,
        tool_profile=tool_profile,
        material_removal=material_removal,
        programmed_measurement_face_z_target=programmed_target,
        a_z=a_z,
        x_z=x_z,
        b_z=b_z,
        c_z=c_z,
        d_z=d_z,
        nc_blocked=nc_blocked,
        notes=notes,
        safe_z=safe_z,
        end_safe_z=end_safe_z,
        required_safe_z=required,
        safe_status=safe_eval.status,
        safe_headline=safe_eval.headline,
        x_safety_clearance=x_safety,
        entry_clearance=entry_clearance,
        full_cut_overlap=overlap,
    )


def format_help_info(snapshot: BSFGeometryHelpSnapshot) -> str:
    designation = snapshot.tool_profile.designation if snapshot.tool_profile is not None else "—"
    offset = (
        fmt_mm(snapshot.tool_profile.measurement_face_to_cutting_edge_mm)
        if snapshot.tool_profile is not None
        else "—"
    )
    speed = (
        "—"
        if snapshot.tool_profile is None or snapshot.tool_profile.activation_speed_rpm is None
        else f"{snapshot.tool_profile.activation_speed_rpm:d} U/min"
    )
    examples = "\n".join(
        f"  {ex['name']}: Eintritt {ex['entry_edge_z']:+.1f} / "
        f"Austritt {ex['exit_edge_z']:+.1f} / Ziel {ex['target_surface_z']:+.1f}"
        for ex in snapshot.z0_examples
    )
    return (
        "AKTUELLE GEOMETRIE\n\n"
        "Werkstuecknullpunkt\n"
        "Z0 kann an einer beliebigen, beim Einrichten definierten Werkstueckflaeche liegen.\n"
        f"Z0                      {fmt_axis_z(snapshot.z0)}\n"
        "Alle Z-Werte beziehen sich direkt auf den aktiven Werkstuecknullpunkt.\n"
        "Werkzeug kommt von +Z, Durchfahrt in -Z, Rueckwaertssenken in +Z.\n\n"
        "Werkstueck (direkt)\n"
        f"Eintrittskante          {fmt_axis_z(snapshot.entry_edge_z)}\n"
        f"Austrittskante/Senkseite {fmt_axis_z(snapshot.exit_edge_z)}\n"
        f"Ziel-Senkflaeche        {fmt_axis_z(snapshot.target_surface_z)}\n"
        f"Rohflaeche              {fmt_axis_z(snapshot.raw_surface_z)}\n"
        f"Senktiefe (abgeleitet)  {fmt_mm(snapshot.sink_depth)}\n"
        f"Materialabtrag          {fmt_mm(snapshot.material_removal)}\n\n"
        "Werkzeug\n"
        f"HEULE Werkzeug          {designation}\n"
        f"Vermessung              {MEASUREMENT_LABEL}\n"
        f"Vermessflaeche -> Schneide {offset}\n"
        f"Richtung                {MEASUREMENT_OFFSET_DIRECTION}\n"
        f"Aktivierungsdrehzahl    {speed}\n\n"
        "NC Positionen (Vermessflaeche)\n"
        f"A                       {fmt_axis_z(snapshot.a_z)}\n"
        f"X                       {fmt_axis_z(snapshot.x_z)}\n"
        f"B                       {fmt_axis_z(snapshot.b_z)}\n"
        f"C                       {fmt_axis_z(snapshot.c_z)}\n"
        f"D / Vermesspunkt        {fmt_axis_z(snapshot.d_z)}\n"
        f"Ziel reale Schneide     {fmt_axis_z(snapshot.target_surface_z)}\n"
        f"Stoerkontur E           {snapshot.stoerkontur_e_nc_model}\n\n"
        "Z0-Beispiele (identische Relativgeometrie)\n"
        f"{examples}\n"
        "Nur die absoluten Zahlen aendern sich. Abstaende und HEULE-Prozess bleiben gleich."
    )
