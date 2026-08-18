"""Read-only Snapshot fuer die HEULE-BSF-Senkgeometrie-Hilfe."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from bsf_blade import apply_workpiece_reference_z, calculate_workpiece_bsf_z, parse_reference_z
from heule_bsf_tools import (
    BSFToolProfile,
    MEASUREMENT_LABEL,
    MEASUREMENT_OFFSET_DIRECTION,
    profile_by_designation,
    programmed_measurement_face_z_for_cutting_edge,
)

Z0_BOTTOM_LABEL = "Z0 ist Unterkante Bund"
Z0_TOP_LABEL = "Z0 ist Oberkante Bund"


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


def short_edge_label(label: str) -> str:
    text = (label or "").strip()
    if not text:
        return "—"
    return text.split(" (")[0]


def status_headline(snapshot: "BSFGeometryHelpSnapshot") -> str:
    return "NC-STATUS: BLOCKIERT" if snapshot.nc_blocked else "NC-STATUS: FREIGEGEBEN"


def status_detail(snapshot: "BSFGeometryHelpSnapshot") -> str:
    parts: List[str] = []
    if snapshot.bund_thickness is None:
        parts.append("Bunddicke fehlt")
    if snapshot.sink_depth is None:
        parts.append("Senk-Fertigmaß fehlt")
    if snapshot.clearance is None:
        parts.append("Freifahrt fehlt")
    if snapshot.tool_profile is None:
        parts.append("HEULE Werkzeug fehlt")
    if snapshot.reference_z is None:
        parts.append("Z-Lage Bezugsebene fehlt")
    return " · ".join(parts)


@dataclass(frozen=True)
class BSFGeometryHelpSnapshot:
    bund_thickness: Optional[float]
    sink_depth: Optional[float]
    clearance: Optional[float]
    tool_profile: Optional[BSFToolProfile]
    z0_is_flange_bottom: bool
    z0_label: str
    reference_z: Optional[float]
    workpiece_z_sink_finish: Optional[float]
    workpiece_z_clearance: Optional[float]
    programmed_measurement_face_z_sink_finish: Optional[float]
    programmed_measurement_face_z_clearance: Optional[float]
    nc_blocked: bool
    notes: List[str] = field(default_factory=list)


def build_bsf_geometry_help_snapshot(
    *,
    bund_text: str,
    sink_text: str,
    clearance_text: str,
    z0_label: str,
    reference_z_text: str = "0",
    tool_designation: str = "",
) -> BSFGeometryHelpSnapshot:
    """Baut den Hilfesnapshot aus GUI-Texten. Keine Dialoge, keine erfundenen Werte."""
    bund = _parse_optional_mm(bund_text)
    sink = _parse_optional_mm(sink_text)
    clearance = _parse_optional_mm(clearance_text)
    tool_profile = profile_by_designation(tool_designation)

    z0_is_bottom = z0_label != Z0_TOP_LABEL
    z0_shown = Z0_BOTTOM_LABEL if z0_is_bottom else Z0_TOP_LABEL

    ok_ref, reference_z, _ = parse_reference_z(reference_z_text if (reference_z_text or "").strip() else "0")
    if not ok_ref:
        reference_z = None

    notes: List[str] = []
    if bund is None:
        notes.append("Bunddicke fehlt")
    if sink is None:
        notes.append("Senk-Fertigmaß fehlt")
    if clearance is None:
        notes.append("Freifahrt fehlt")
    if tool_profile is None:
        notes.append("HEULE Werkzeug fehlt")
    if reference_z is None:
        notes.append("Z-Lage Bezugsebene fehlt")

    workpiece_sink = None
    workpiece_clear = None
    programmed_sink = None
    programmed_clear = None

    workpiece_ok = None not in (bund, sink, clearance)
    if workpiece_ok:
        wp = calculate_workpiece_bsf_z(
            bund,
            sink,
            clearance,
            z0_is_flange_bottom=z0_is_bottom,
        )
        if reference_z is not None:
            wp = apply_workpiece_reference_z(wp, reference_z)
        workpiece_sink = wp["z_sink_finish"]
        workpiece_clear = wp["z_clearance"]
        if tool_profile is not None:
            programmed_sink = programmed_measurement_face_z_for_cutting_edge(workpiece_sink, tool_profile)
            programmed_clear = programmed_measurement_face_z_for_cutting_edge(workpiece_clear, tool_profile)

    nc_blocked = (not workpiece_ok) or tool_profile is None or reference_z is None

    return BSFGeometryHelpSnapshot(
        bund_thickness=bund,
        sink_depth=sink,
        clearance=clearance,
        tool_profile=tool_profile,
        z0_is_flange_bottom=z0_is_bottom,
        z0_label=z0_shown,
        reference_z=reference_z,
        workpiece_z_sink_finish=workpiece_sink,
        workpiece_z_clearance=workpiece_clear,
        programmed_measurement_face_z_sink_finish=programmed_sink,
        programmed_measurement_face_z_clearance=programmed_clear,
        nc_blocked=nc_blocked,
        notes=notes,
    )


def format_help_info(snapshot: BSFGeometryHelpSnapshot) -> str:
    z0_short = "Unterkante Bund" if snapshot.z0_is_flange_bottom else "Oberkante Bund"
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
    return (
        "AKTUELLE GEOMETRIE\n\n"
        "Werkstück\n"
        f"Bunddicke               {fmt_mm(snapshot.bund_thickness)}\n"
        f"Senk-Fertigmaß          {fmt_mm(snapshot.sink_depth)}\n"
        f"Freifahrt               {fmt_mm(snapshot.clearance)}\n"
        f"Bezugsebene             {z0_short}\n"
        f"Z-Lage                  {fmt_axis_z(snapshot.reference_z)}\n\n"
        "Werkzeug\n"
        f"HEULE Werkzeug          {designation}\n"
        f"Vermessung              {MEASUREMENT_LABEL}\n"
        f"Vermessfläche -> Schneide {offset}\n"
        f"Richtung                {MEASUREMENT_OFFSET_DIRECTION}\n"
        f"Aktivierungsdrehzahl    {speed}\n\n"
        "NC\n"
        f"Schneidenziel Finish    {fmt_axis_z(snapshot.workpiece_z_sink_finish)}\n"
        f"Schneidenziel Freifahrt {fmt_axis_z(snapshot.workpiece_z_clearance)}\n"
        f"Vermesspunkt-Z Finish   {fmt_axis_z(snapshot.programmed_measurement_face_z_sink_finish)}\n"
        f"Vermesspunkt-Z Freifahrt {fmt_axis_z(snapshot.programmed_measurement_face_z_clearance)}"
    )
