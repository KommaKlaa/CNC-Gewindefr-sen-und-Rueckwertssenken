"""Read-only Snapshot fuer die HEULE-BSF-Senkgeometrie-Hilfe.

Consumer der Domain ``bsf_blade.py`` – keine eigenen Z-Formeln.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from bsf_blade import (
    FINISH_EDGE,
    MEASUREMENT_LABELS,
    MEASUREMENT_PLACEHOLDER,
    BladeMeasurementReference,
    apply_blade_offset,
    blade_reference_offset,
    calculate_workpiece_bsf_z,
    parse_blade_thickness,
    parse_measurement_reference,
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
    if snapshot.blade_thickness is None:
        parts.append("Schwertdicke fehlt")
    if snapshot.measurement_reference is None:
        parts.append("Vermessreferenz fehlt")
    return " · ".join(parts)


@dataclass(frozen=True)
class BSFGeometryHelpSnapshot:
    bund_thickness: Optional[float]
    sink_depth: Optional[float]
    clearance: Optional[float]
    blade_thickness: Optional[float]
    measurement_reference: Optional[BladeMeasurementReference]
    measurement_label: str
    z0_is_flange_bottom: bool
    z0_label: str
    finish_edge: BladeMeasurementReference
    workpiece_z_sink_finish: Optional[float]
    workpiece_z_clearance: Optional[float]
    programmed_z_sink_finish: Optional[float]
    programmed_z_clearance: Optional[float]
    nc_blocked: bool
    notes: List[str] = field(default_factory=list)

    @property
    def finish_edge_label(self) -> str:
        return MEASUREMENT_LABELS[self.finish_edge]


def build_bsf_geometry_help_snapshot(
    *,
    bund_text: str,
    sink_text: str,
    clearance_text: str,
    blade_text: str,
    measurement_label: str,
    z0_label: str,
) -> BSFGeometryHelpSnapshot:
    """Baut den Hilfesnapshot aus GUI-Texten. Keine Dialoge, keine erfundenen Werte."""
    bund = _parse_optional_mm(bund_text)
    sink = _parse_optional_mm(sink_text)
    clearance = _parse_optional_mm(clearance_text)

    blade_ok, blade_thickness, _ = parse_blade_thickness(blade_text)
    if not blade_ok:
        blade_thickness = None

    meas_ok, meas_ref, _ = parse_measurement_reference(measurement_label)
    if not meas_ok:
        meas_ref = None
        shown_meas = ""
        if (measurement_label or "").strip() in ("", MEASUREMENT_PLACEHOLDER):
            shown_meas = ""
        else:
            shown_meas = (measurement_label or "").strip()
    else:
        shown_meas = MEASUREMENT_LABELS[meas_ref]

    z0_is_bottom = z0_label != Z0_TOP_LABEL
    z0_shown = Z0_BOTTOM_LABEL if z0_is_bottom else Z0_TOP_LABEL

    notes: List[str] = []
    if bund is None:
        notes.append("Bunddicke fehlt")
    if sink is None:
        notes.append("Senk-Fertigmaß fehlt")
    if clearance is None:
        notes.append("Freifahrt fehlt")
    if blade_thickness is None:
        notes.append("Schwertdicke fehlt")
    if meas_ref is None:
        notes.append("Vermessreferenz fehlt")

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
        workpiece_sink = wp["z_sink_finish"]
        workpiece_clear = wp["z_clearance"]
        if blade_thickness is not None and meas_ref is not None:
            offset = blade_reference_offset(blade_thickness, meas_ref)
            programmed = apply_blade_offset(wp, offset)
            programmed_sink = programmed["z_sink_finish"]
            programmed_clear = programmed["z_clearance"]

    nc_blocked = (not workpiece_ok) or blade_thickness is None or meas_ref is None

    return BSFGeometryHelpSnapshot(
        bund_thickness=bund,
        sink_depth=sink,
        clearance=clearance,
        blade_thickness=blade_thickness,
        measurement_reference=meas_ref,
        measurement_label=shown_meas,
        z0_is_flange_bottom=z0_is_bottom,
        z0_label=z0_shown,
        finish_edge=FINISH_EDGE,
        workpiece_z_sink_finish=workpiece_sink,
        workpiece_z_clearance=workpiece_clear,
        programmed_z_sink_finish=programmed_sink,
        programmed_z_clearance=programmed_clear,
        nc_blocked=nc_blocked,
        notes=notes,
    )


def format_help_info(snapshot: BSFGeometryHelpSnapshot) -> str:
    z0_short = "Unterkante Bund" if snapshot.z0_is_flange_bottom else "Oberkante Bund"
    meas = short_edge_label(snapshot.measurement_label)
    finish = short_edge_label(snapshot.finish_edge_label)
    return (
        "AKTUELLE GEOMETRIE\n\n"
        "Werkstück\n"
        f"Bunddicke               {fmt_mm(snapshot.bund_thickness)}\n"
        f"Senk-Fertigmaß          {fmt_mm(snapshot.sink_depth)}\n"
        f"Freifahrt               {fmt_mm(snapshot.clearance)}\n"
        f"Z0                      {z0_short}\n\n"
        "Werkzeug\n"
        f"Schwertdicke            {fmt_mm(snapshot.blade_thickness)}\n"
        f"Vermessung              {meas}\n"
        f"Fertigkante             {finish}\n\n"
        "NC\n"
        f"Finish-Z                {fmt_axis_z(snapshot.programmed_z_sink_finish)}\n"
        f"Freifahrt-Z             {fmt_axis_z(snapshot.programmed_z_clearance)}"
    )
