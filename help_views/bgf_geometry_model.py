"""Read-only Snapshot fuer die CERATIZIT-BGF-Gewindegeometrie-Hilfe.

Consumer von ``bgf_depth`` / ``bgf_surface`` – keine eigenen Tiefenformeln.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from bgf_depth import (
    BGFDepthEvaluation,
    BGFDepthPolicy,
    BGFDepthRequest,
    DepthGateStatus,
    evaluate_bgf_depth,
)
from bgf_surface import above_surface, absolute_from_surface, validate_approach_clearance


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


def fmt_xy(value: Optional[float]) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.3f}"


def fmt_radius(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"R+{value:.4f} mm"


def status_headline(snapshot: "BGFGeometryHelpSnapshot") -> str:
    if snapshot.empty_list:
        return "NC-STATUS: —"
    return "NC-STATUS: BLOCKIERT" if snapshot.nc_blocked else "NC-STATUS: FREIGEGEBEN"


def status_detail(snapshot: "BGFGeometryHelpSnapshot") -> str:
    if snapshot.empty_list:
        return "Keine Position vorhanden"
    if snapshot.nc_blocked:
        if snapshot.status is not None:
            return f"Grund: {snapshot.status.value}"
        if snapshot.notes:
            return "Grund: " + " · ".join(snapshot.notes)
        return "Grund: —"
    if snapshot.is_template:
        return "TIEFENMODUS: CERATIZIT HERSTELLER-TEMPLATE"
    if snapshot.status is DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK:
        return "TIEFENMODUS: AXIALE TEMPLATE-VERSCHIEBUNG"
    if snapshot.depth_mode_label:
        return f"TIEFENMODUS: {snapshot.depth_mode_label.upper()}"
    return ""


@dataclass(frozen=True)
class BGFHelpToolView:
    size: str
    article_no: str
    radius: float
    pitch: float
    predrill_depth: Optional[float] = None


@dataclass(frozen=True)
class BGFHelpPositionView:
    x: Optional[float] = None
    y: Optional[float] = None
    surface_z: Optional[float] = None
    thread_depth: Optional[float] = None
    core_hole_depth: Optional[float] = None


@dataclass(frozen=True)
class BGFHelpSource:
    """GUI-Quelle. Navigation im Hilfefenster ist lokal und aendert diese Quelle nicht."""

    tool: BGFHelpToolView
    policy: BGFDepthPolicy
    approach_clearance: Optional[float]
    mode: str
    positions: Tuple[BGFHelpPositionView, ...]
    initial_index: int = 0
    circle_diameter: Optional[float] = None
    circle_count: Optional[int] = None


@dataclass(frozen=True)
class BGFGeometryHelpSnapshot:
    tool_size: str
    article_no: str
    radius: float
    pitch: float
    predrill_depth: Optional[float]
    approved_max_thread_depth: Optional[float]
    template_thread_depth: float
    template_mill_start_depth: float
    template_drill_depth: float
    surface_z: Optional[float]
    thread_depth: Optional[float]
    core_hole_depth: Optional[float]
    approach_clearance: Optional[float]
    approach_z: Optional[float]
    thread_end_z: Optional[float]
    mill_start_depth: Optional[float]
    mill_start_z: Optional[float]
    deepest_milling_depth: Optional[float]
    deepest_milling_z: Optional[float]
    drill_depth: Optional[float]
    drill_z: Optional[float]
    drill_reserve: Optional[float]
    depth_delta: Optional[float]
    template_mill_start_z: Optional[float]
    template_drill_z: Optional[float]
    core_hole_z: Optional[float]
    predrill_z: Optional[float]
    predrill_shifted: bool
    is_template: bool
    show_template_overlay: bool
    nc_blocked: bool
    ok_for_nc: bool
    status: Optional[DepthGateStatus]
    depth_mode_label: str
    mode: str
    position_index: int
    position_count: int
    x: Optional[float]
    y: Optional[float]
    circle_diameter: Optional[float]
    circle_count: Optional[int]
    empty_list: bool
    notes: List[str] = field(default_factory=list)


def _z_if_surface(surface_z: Optional[float], z_value: Optional[float]) -> Optional[float]:
    if surface_z is None:
        return None
    return z_value


def build_bgf_geometry_help_snapshot(
    *,
    tool_size: str,
    article_no: str,
    radius: float,
    pitch: float,
    predrill_depth: Optional[float],
    policy: BGFDepthPolicy,
    surface_z: Optional[float],
    thread_depth: Optional[float],
    core_hole_depth: Optional[float] = None,
    approach_clearance: Optional[float] = None,
    x: Optional[float] = None,
    y: Optional[float] = None,
    mode: str = "Einzelposition",
    position_index: int = 1,
    position_count: int = 1,
    circle_diameter: Optional[float] = None,
    circle_count: Optional[int] = None,
    empty_list: bool = False,
) -> BGFGeometryHelpSnapshot:
    """Baut den Hilfesnapshot aus Domainresultaten. Keine Dialoge, keine Shift-Formeln."""
    notes: List[str] = []
    if empty_list:
        notes.append("Keine Position vorhanden")
    if thread_depth is None and not empty_list:
        notes.append("Gewindetiefe fehlt")
    if surface_z is None and not empty_list:
        notes.append("Z Oberfläche fehlt")

    approach_z = None
    if surface_z is not None and approach_clearance is not None:
        if validate_approach_clearance(approach_clearance) is None:
            approach_z = above_surface(surface_z, approach_clearance)

    core_hole_z = None
    if surface_z is not None and core_hole_depth is not None:
        core_hole_z = absolute_from_surface(surface_z, core_hole_depth)

    predrill_z = None
    if surface_z is not None and predrill_depth is not None:
        predrill_z = absolute_from_surface(surface_z, predrill_depth)

    evaluation: Optional[BGFDepthEvaluation] = None
    if thread_depth is not None:
        eval_surface = 0.0 if surface_z is None else surface_z
        evaluation = evaluate_bgf_depth(
            BGFDepthRequest(thread_depth, core_hole_depth),
            policy,
            surface_z=eval_surface,
        )

    mill_start_depth = evaluation.nc_mill_start_depth if evaluation is not None else None
    drill_depth = evaluation.nc_drill_depth if evaluation is not None else None
    deepest_milling_depth = evaluation.deepest_milling_depth if evaluation is not None else None
    drill_reserve = evaluation.drill_reserve if evaluation is not None else None
    is_template = bool(evaluation.is_template) if evaluation is not None else False
    ok_for_nc = bool(evaluation.ok_for_nc) if evaluation is not None else False
    status = evaluation.status if evaluation is not None else None
    depth_mode_label = evaluation.depth_mode_label if evaluation is not None else ""
    nc_blocked = (not ok_for_nc) or empty_list

    if evaluation is not None and evaluation.ok_for_nc:
        depth_delta = 0.0 if evaluation.is_template else evaluation.depth_delta
    else:
        depth_delta = None

    thread_end_z = None
    mill_start_z = None
    drill_z = None
    deepest_milling_z = None
    template_mill_start_z = None
    template_drill_z = None
    if evaluation is not None:
        thread_end_z = _z_if_surface(surface_z, evaluation.thread_end_z)
        mill_start_z = _z_if_surface(surface_z, evaluation.nc_mill_start_z)
        drill_z = _z_if_surface(surface_z, evaluation.nc_drill_z)
        template_mill_start_z = _z_if_surface(surface_z, evaluation.template_nc_mill_start_z)
        template_drill_z = _z_if_surface(surface_z, evaluation.template_nc_drill_z)
        if surface_z is not None and deepest_milling_depth is not None:
            deepest_milling_z = absolute_from_surface(surface_z, deepest_milling_depth)

    show_overlay = bool(
        evaluation is not None
        and evaluation.ok_for_nc
        and not evaluation.is_template
        and template_mill_start_z is not None
        and mill_start_z is not None
    )

    return BGFGeometryHelpSnapshot(
        tool_size=tool_size,
        article_no=article_no,
        radius=radius,
        pitch=pitch,
        predrill_depth=predrill_depth,
        approved_max_thread_depth=policy.approved_max_thread_depth,
        template_thread_depth=policy.template_thread_depth,
        template_mill_start_depth=policy.template_mill_start_depth,
        template_drill_depth=policy.template_drill_depth,
        surface_z=surface_z,
        thread_depth=thread_depth,
        core_hole_depth=core_hole_depth,
        approach_clearance=approach_clearance,
        approach_z=approach_z,
        thread_end_z=thread_end_z,
        mill_start_depth=mill_start_depth,
        mill_start_z=mill_start_z,
        deepest_milling_depth=deepest_milling_depth,
        deepest_milling_z=deepest_milling_z,
        drill_depth=drill_depth,
        drill_z=drill_z,
        drill_reserve=drill_reserve,
        depth_delta=depth_delta,
        template_mill_start_z=template_mill_start_z,
        template_drill_z=template_drill_z,
        core_hole_z=core_hole_z,
        predrill_z=predrill_z,
        predrill_shifted=False,
        is_template=is_template,
        show_template_overlay=show_overlay,
        nc_blocked=nc_blocked,
        ok_for_nc=ok_for_nc,
        status=status,
        depth_mode_label=depth_mode_label,
        mode=mode,
        position_index=position_index,
        position_count=position_count,
        x=x,
        y=y,
        circle_diameter=circle_diameter,
        circle_count=circle_count,
        empty_list=empty_list,
        notes=notes,
    )


def snapshot_from_source(source: BGFHelpSource, index: int) -> BGFGeometryHelpSnapshot:
    tool = source.tool
    if not source.positions:
        return build_bgf_geometry_help_snapshot(
            tool_size=tool.size,
            article_no=tool.article_no,
            radius=tool.radius,
            pitch=tool.pitch,
            predrill_depth=tool.predrill_depth,
            policy=source.policy,
            surface_z=None,
            thread_depth=None,
            core_hole_depth=None,
            approach_clearance=source.approach_clearance,
            mode=source.mode,
            position_index=0,
            position_count=0,
            circle_diameter=source.circle_diameter,
            circle_count=source.circle_count,
            empty_list=True,
        )
    n = len(source.positions)
    i = max(0, min(int(index), n - 1))
    pos = source.positions[i]
    return build_bgf_geometry_help_snapshot(
        tool_size=tool.size,
        article_no=tool.article_no,
        radius=tool.radius,
        pitch=tool.pitch,
        predrill_depth=tool.predrill_depth,
        policy=source.policy,
        surface_z=pos.surface_z,
        thread_depth=pos.thread_depth,
        core_hole_depth=pos.core_hole_depth,
        approach_clearance=source.approach_clearance,
        x=pos.x,
        y=pos.y,
        mode=source.mode,
        position_index=i + 1,
        position_count=n,
        circle_diameter=source.circle_diameter,
        circle_count=source.circle_count,
        empty_list=False,
    )


def format_help_info(snapshot: BGFGeometryHelpSnapshot) -> str:
    core = fmt_mm(snapshot.core_hole_depth) if snapshot.core_hole_depth is not None else "—"
    return (
        "AKTUELLE GEOMETRIE\n\n"
        "Werkzeug\n"
        f"Gewinde                  {snapshot.tool_size}\n"
        f"Artikel                  {snapshot.article_no}\n"
        f"Radius                   {fmt_radius(snapshot.radius)}\n\n"
        "Werkstück\n"
        f"Z Oberfläche             {fmt_axis_z(snapshot.surface_z)}\n"
        f"Gewindetiefe             {fmt_mm(snapshot.thread_depth)}\n"
        f"Gewindeende              {fmt_axis_z(snapshot.thread_end_z)}\n"
        f"Kernlochtiefe Soll       {core}\n\n"
        "Sicherheit\n"
        f"Sicherheitsabstand        {fmt_mm(snapshot.approach_clearance)}\n"
        f"Anfahr-Z                 {fmt_axis_z(snapshot.approach_z)}\n\n"
        "NC\n"
        f"Frässtarttiefe           {fmt_mm(snapshot.mill_start_depth)}\n"
        f"Frässtart-Z              {fmt_axis_z(snapshot.mill_start_z)}\n"
        f"Tiefste Fräsposition     {fmt_axis_z(snapshot.deepest_milling_z)}\n"
        f"NC-Bohrtiefe             {fmt_mm(snapshot.drill_depth)}\n"
        f"NC-Bohr-Z                {fmt_axis_z(snapshot.drill_z)}\n"
        f"Bohrreserve               {fmt_mm(snapshot.drill_reserve)}"
    )


def parse_help_mm(text: str) -> Optional[float]:
    return _parse_optional_mm(text)


def source_positions_from_rows(rows: Sequence) -> Tuple[BGFHelpPositionView, ...]:
    out: List[BGFHelpPositionView] = []
    for row in rows:
        out.append(
            BGFHelpPositionView(
                x=getattr(row, "x", None),
                y=getattr(row, "y", None),
                surface_z=getattr(row, "surface_z", None),
                thread_depth=getattr(row, "thread_depth", None),
                core_hole_depth=getattr(row, "core_hole_depth", None),
            )
        )
    return tuple(out)
