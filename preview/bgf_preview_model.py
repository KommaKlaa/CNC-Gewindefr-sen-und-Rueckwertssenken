"""Read-only Preview-Modell fuer BGF-Positionsvorschau."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from bgf_depth import BGFDepthPolicy, BGFDepthRequest, DepthGateStatus, evaluate_bgf_depth
from bgf_surface import above_surface
from coordinates.bgf_list_validation import (
    find_duplicate_xyz,
    validate_bgf_coordinate_list,
)
from coordinates.bgf_position import BGFCoordinatePosition
from coordinates.circle_positions import compute_circle_xy_positions


@dataclass
class PreviewPoint:
    index: int  # 1-based NC-Reihenfolge
    x: float
    y: float
    surface_z: float
    thread_depth: float
    core_hole_depth: Optional[float]
    ok_for_nc: bool
    status_code: DepthGateStatus
    status_label: str
    depth_mode_label: str = ""
    nc_mill_start_depth: Optional[float] = None
    nc_drill_depth: Optional[float] = None
    deepest_milling_depth: Optional[float] = None
    drill_reserve: Optional[float] = None
    thread_end_z: Optional[float] = None
    safe_z_ok: bool = True
    is_duplicate_xyz: bool = False
    xy_overlap_count: int = 1
    marker: str = "✓"  # ✓ / ! / ✕


@dataclass
class PreviewSnapshot:
    mode_label: str
    thread_size: str
    article_no: str
    tool_radius: float
    tool_number: int
    program_name: str
    approach_clearance: float
    safe_z: float
    end_safe_z: float
    points: List[PreviewPoint] = field(default_factory=list)
    nc_allowed: bool = False
    blocked_count: int = 0
    warnings: List[str] = field(default_factory=list)
    circle_info: Optional[str] = None
    process_kind: str = "BGF"  # "BGF" | "BSF"
    # Legacy BSF-Bezugsebenenfelder (nicht mehr Anzeigequelle)
    bsf_bund_thickness: Optional[float] = None
    bsf_clearance: Optional[float] = None
    bsf_reference_z: Optional[float] = None
    bsf_tool_designation: str = ""
    bsf_measurement_face_to_edge_mm: Optional[float] = None
    # Aktuelles direktes Z0-/RawRef-Modell
    bsf_entry_edge_z: Optional[float] = None
    bsf_exit_edge_z: Optional[float] = None
    bsf_raw_surface_z: Optional[float] = None
    bsf_target_surface_z: Optional[float] = None
    bsf_process_surface_z: Optional[float] = None
    bsf_process_surface_source: Optional[str] = None
    bsf_sink_depth: Optional[float] = None
    bsf_material_removal: Optional[float] = None
    bsf_a_measurement_face_z: Optional[float] = None
    bsf_x_measurement_face_z: Optional[float] = None
    bsf_b_measurement_face_z: Optional[float] = None
    bsf_c_measurement_face_z: Optional[float] = None
    bsf_d_measurement_face_z: Optional[float] = None
    bsf_target_cutting_edge_z: Optional[float] = None
    bsf_hs_mm: Optional[float] = None
    bsf_al_mm: Optional[float] = None
    bsf_activation_speed_rpm: Optional[int] = None
    bsf_required_safe_z: Optional[float] = None
    bsf_safe_reserve_mm: Optional[float] = None
    bsf_safe_status: str = ""
    bsf_safe_status_code: str = ""
    bsf_geometry_complete: bool = False
    bsf_geometry_missing: List[str] = field(default_factory=list)
    bsf_end_mode: str = ""


def _marker_for(*, depth_ok: bool, safe_ok: bool, is_dup: bool) -> str:
    if not depth_ok or not safe_ok:
        return "✕"
    if is_dup:
        return "!"
    return "✓"


def _unsafe_position_indices(
    positions: Sequence[BGFCoordinatePosition],
    *,
    safe_z: float,
    end_safe_z: float,
    approach_clearance: float,
) -> set:
    unsafe: set = set()
    for idx, pos in enumerate(positions, start=1):
        approach_z = above_surface(pos.surface_z, approach_clearance)
        if safe_z < approach_z or end_safe_z < approach_z:
            unsafe.add(idx)
    return unsafe


def build_preview_from_positions(
    positions: Sequence[BGFCoordinatePosition],
    *,
    policy: BGFDepthPolicy,
    safe_z: float,
    end_safe_z: float,
    approach_clearance: float,
    mode_label: str,
    thread_size: str,
    article_no: str,
    tool_radius: float,
    tool_number: int,
    program_name: str,
    circle_info: Optional[str] = None,
) -> PreviewSnapshot:
    validation = validate_bgf_coordinate_list(
        positions,
        policy,
        safe_z=safe_z,
        end_safe_z=end_safe_z,
        approach_clearance=approach_clearance,
    )
    dup_keys = set(find_duplicate_xyz(positions))
    unsafe = _unsafe_position_indices(
        positions,
        safe_z=safe_z,
        end_safe_z=end_safe_z,
        approach_clearance=approach_clearance,
    )

    xy_groups: Dict[Tuple[float, float], List[int]] = defaultdict(list)
    for idx, pos in enumerate(positions, start=1):
        xy_groups[(pos.x, pos.y)].append(idx)

    points: List[PreviewPoint] = []
    for row in validation.positions:
        pos = row.position
        idx = row.index
        ev = evaluate_bgf_depth(
            BGFDepthRequest(pos.thread_depth, pos.core_hole_depth),
            policy,
            surface_z=pos.surface_z,
        )
        safe_ok = idx not in unsafe
        status_label = row.status_label
        if not safe_ok:
            status_label = "Anfahr-Z > Sicherheits-Z"
        is_dup = (pos.x, pos.y, pos.surface_z) in dup_keys
        visual_ok = row.ok_for_nc and safe_ok
        points.append(
            PreviewPoint(
                index=idx,
                x=pos.x,
                y=pos.y,
                surface_z=pos.surface_z,
                thread_depth=pos.thread_depth,
                core_hole_depth=pos.core_hole_depth,
                ok_for_nc=visual_ok,
                status_code=row.status_code,
                status_label=status_label,
                depth_mode_label=ev.depth_mode_label or "",
                nc_mill_start_depth=ev.nc_mill_start_depth,
                nc_drill_depth=ev.nc_drill_depth,
                deepest_milling_depth=ev.deepest_milling_depth,
                drill_reserve=ev.drill_reserve,
                thread_end_z=ev.thread_end_z,
                safe_z_ok=safe_ok,
                is_duplicate_xyz=is_dup,
                xy_overlap_count=len(xy_groups[(pos.x, pos.y)]),
                marker=_marker_for(depth_ok=row.ok_for_nc, safe_ok=safe_ok, is_dup=is_dup),
            )
        )

    warnings = list(validation.warnings)
    for (x, y), idxs in xy_groups.items():
        if len(idxs) > 1:
            warnings.append(f"{len(idxs)} Positionen auf gleicher XY-Lage ({x:g}|{y:g})")

    blocked = sum(1 for p in points if not p.ok_for_nc)
    return PreviewSnapshot(
        mode_label=mode_label,
        thread_size=thread_size,
        article_no=article_no,
        tool_radius=tool_radius,
        tool_number=tool_number,
        program_name=program_name,
        approach_clearance=approach_clearance,
        safe_z=safe_z,
        end_safe_z=end_safe_z,
        points=points,
        nc_allowed=validation.ok_for_nc,
        blocked_count=blocked,
        warnings=warnings,
        circle_info=circle_info,
    )


def build_circle_positions_for_preview(
    *,
    center_x: float,
    center_y: float,
    diameter: float,
    count: int,
    start_angle_deg: float,
    thread_depth: float,
    core_hole_depth: Optional[float],
    surface_z: float = 0.0,
) -> List[BGFCoordinatePosition]:
    xy = compute_circle_xy_positions(
        center_x=center_x,
        center_y=center_y,
        diameter=diameter,
        count=count,
        start_angle_deg=start_angle_deg,
    )
    return [
        BGFCoordinatePosition(
            x=x,
            y=y,
            surface_z=surface_z,
            thread_depth=thread_depth,
            core_hole_depth=core_hole_depth,
        )
        for x, y in xy
    ]


def build_bsf_preview_from_xy(
    positions: Sequence,
    *,
    nc_allowed: bool,
    mode_label: str,
    tool_number: int,
    program_name: str,
    safe_z: float,
    end_safe_z: float,
    tool_designation: str = "",
    measurement_face_to_edge_mm: Optional[float] = None,
    circle_info: Optional[str] = None,
    extra_warnings: Optional[List[str]] = None,
    entry_edge_z: Optional[float] = None,
    exit_edge_z: Optional[float] = None,
    raw_surface_z: Optional[float] = None,
    target_surface_z: Optional[float] = None,
    process_surface_z: Optional[float] = None,
    process_surface_source: Optional[str] = None,
    sink_depth: Optional[float] = None,
    material_removal: Optional[float] = None,
    a_measurement_face_z: Optional[float] = None,
    x_measurement_face_z: Optional[float] = None,
    b_measurement_face_z: Optional[float] = None,
    c_measurement_face_z: Optional[float] = None,
    d_measurement_face_z: Optional[float] = None,
    target_cutting_edge_z: Optional[float] = None,
    hs_mm: Optional[float] = None,
    al_mm: Optional[float] = None,
    activation_speed_rpm: Optional[int] = None,
    required_safe_z: Optional[float] = None,
    safe_reserve_mm: Optional[float] = None,
    safe_status: str = "",
    safe_status_code: str = "",
    geometry_complete: bool = False,
    geometry_missing: Optional[List[str]] = None,
    end_mode: str = "",
) -> PreviewSnapshot:
    """Read-only Preview fuer HEULE BSF (X/Y + kanonische Z0-Geometrie)."""
    from coordinates.model import XYCoordinate
    from coordinates.validation import find_duplicate_xy, validate_coordinates

    xy_coords = [XYCoordinate(x=float(p.x), y=float(p.y), active=True) for p in positions]
    validation = validate_coordinates(xy_coords) if xy_coords else None
    dup_keys = set(find_duplicate_xy(xy_coords)) if xy_coords else set()

    xy_groups: Dict[Tuple[float, float], List[int]] = defaultdict(list)
    for idx, pos in enumerate(positions, start=1):
        xy_groups[(float(pos.x), float(pos.y))].append(idx)

    list_ok = True
    warnings: List[str] = list(extra_warnings or [])
    if validation is not None:
        list_ok = validation.ok
        for w in validation.warnings:
            if w not in warnings:
                warnings.append(w)
        for err in validation.errors:
            if err not in warnings:
                warnings.append(err)
    elif not positions:
        list_ok = False
        warnings.append("Keine Positionen in der Koordinatenliste.")

    program_ok = bool(nc_allowed) and list_ok and bool(positions)

    points: List[PreviewPoint] = []
    for idx, pos in enumerate(positions, start=1):
        x, y = float(pos.x), float(pos.y)
        is_dup = (x, y) in dup_keys
        overlap = len(xy_groups[(x, y)])
        ok_point = program_ok
        if is_dup:
            status_label = "Doppelte XY-Position"
        elif ok_point:
            status_label = "OK"
        else:
            status_label = "NC nicht freigegeben"
        points.append(
            PreviewPoint(
                index=idx,
                x=x,
                y=y,
                surface_z=0.0,
                thread_depth=0.0,
                core_hole_depth=None,
                ok_for_nc=ok_point,
                status_code=DepthGateStatus.TEMPLATE_OK if ok_point else DepthGateStatus.INVALID,
                status_label=status_label,
                is_duplicate_xyz=is_dup,
                xy_overlap_count=overlap,
                marker=_marker_for(depth_ok=ok_point, safe_ok=True, is_dup=is_dup),
            )
        )

    blocked = sum(1 for p in points if not p.ok_for_nc)
    return PreviewSnapshot(
        mode_label=mode_label,
        thread_size="BSF",
        article_no="",
        tool_radius=0.0,
        tool_number=tool_number,
        program_name=program_name,
        approach_clearance=0.0,
        safe_z=safe_z,
        end_safe_z=end_safe_z,
        points=points,
        nc_allowed=program_ok,
        blocked_count=blocked,
        warnings=warnings,
        circle_info=circle_info,
        process_kind="BSF",
        bsf_tool_designation=tool_designation,
        bsf_measurement_face_to_edge_mm=measurement_face_to_edge_mm,
        bsf_entry_edge_z=entry_edge_z,
        bsf_exit_edge_z=exit_edge_z,
        bsf_raw_surface_z=raw_surface_z,
        bsf_target_surface_z=target_surface_z,
        bsf_process_surface_z=process_surface_z,
        bsf_process_surface_source=process_surface_source,
        bsf_sink_depth=sink_depth,
        bsf_material_removal=material_removal,
        bsf_a_measurement_face_z=a_measurement_face_z,
        bsf_x_measurement_face_z=x_measurement_face_z,
        bsf_b_measurement_face_z=b_measurement_face_z,
        bsf_c_measurement_face_z=c_measurement_face_z,
        bsf_d_measurement_face_z=d_measurement_face_z,
        bsf_target_cutting_edge_z=target_cutting_edge_z,
        bsf_hs_mm=hs_mm,
        bsf_al_mm=al_mm,
        bsf_activation_speed_rpm=activation_speed_rpm,
        bsf_required_safe_z=required_safe_z,
        bsf_safe_reserve_mm=safe_reserve_mm,
        bsf_safe_status=safe_status,
        bsf_safe_status_code=safe_status_code,
        bsf_geometry_complete=geometry_complete,
        bsf_geometry_missing=list(geometry_missing or []),
        bsf_end_mode=end_mode,
    )
