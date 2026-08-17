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
    bsf_bund_thickness: Optional[float] = None
    bsf_sink_depth: Optional[float] = None
    bsf_clearance: Optional[float] = None
    bsf_blade_thickness: Optional[float] = None
    bsf_measurement_label: str = ""


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
    bund_thickness: Optional[float] = None,
    sink_depth: Optional[float] = None,
    clearance: Optional[float] = None,
    blade_thickness: Optional[float] = None,
    measurement_label: str = "",
    circle_info: Optional[str] = None,
    extra_warnings: Optional[List[str]] = None,
) -> PreviewSnapshot:
    """Read-only Preview fuer HEULE BSF (X/Y, keine BGF-Tiefen)."""
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
            status_label = "NC blockiert"
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
        bsf_bund_thickness=bund_thickness,
        bsf_sink_depth=sink_depth,
        bsf_clearance=clearance,
        bsf_blade_thickness=blade_thickness,
        bsf_measurement_label=measurement_label,
    )
