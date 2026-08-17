"""Validierung einer BGF-Koordinatenliste (programmweites Safety-Gate)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from bgf_depth import BGFDepthPolicy, BGFDepthRequest, DepthGateStatus, evaluate_bgf_depth
from bgf_surface import above_surface

from .bgf_position import BGFCoordinatePosition


STATUS_LABELS = {
    DepthGateStatus.TEMPLATE_OK: "Template OK",
    DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK: "Variable Tiefe OK (Axial-Shift)",
    DepthGateStatus.VARIABLE_BLOCKED: "Tiefe ueber Template blockiert",
    DepthGateStatus.MAX_THREAD_DEPTH_UNVALIDATED: "Freigabegrenze fehlt",
    DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX: "Gewindetiefe > Freigabegrenze",
    DepthGateStatus.CORE_HOLE_EXCEEDED: "Gewindetiefe > Kernlochtiefe",
    DepthGateStatus.INVALID_SHIFTED_GEOMETRY: "Unplausible Shift-Geometrie",
    DepthGateStatus.INVALID: "Ungueltige Eingabe",
}


@dataclass
class PositionDepthStatus:
    index: int  # 1-based
    position: BGFCoordinatePosition
    ok_for_nc: bool
    status_code: DepthGateStatus
    status_label: str
    messages: List[str] = field(default_factory=list)


@dataclass
class BGFCoordinateListValidation:
    ok_for_nc: bool
    positions: List[PositionDepthStatus] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def status_label_for(status: DepthGateStatus) -> str:
    return STATUS_LABELS.get(status, status.value)


def find_duplicate_xyz(
    positions: Sequence[BGFCoordinatePosition],
) -> List[Tuple[float, float, float]]:
    seen = set()
    dups: List[Tuple[float, float, float]] = []
    for p in positions:
        key = (p.x, p.y, p.surface_z)
        if key in seen:
            if key not in dups:
                dups.append(key)
        else:
            seen.add(key)
    return dups


def validate_safe_z_against_surfaces(
    safe_z: float,
    end_safe_z: float,
    positions: Sequence[BGFCoordinatePosition],
    *,
    approach_clearance: float,
) -> List[str]:
    """safe_z / end_safe_z muessen >= max(approach_z) sein.

    approach_z = surface_z + approach_clearance
    """
    errors: List[str] = []
    if not positions:
        return errors

    for idx, pos in enumerate(positions, start=1):
        approach_z = above_surface(pos.surface_z, approach_clearance)
        if safe_z < approach_z:
            errors.append(
                f"Sicherheits-Z {safe_z:.3f} mm liegt unter dem erforderlichen "
                f"Anfahr-Z {approach_z:.3f} mm der Position {idx}."
            )
        if end_safe_z < approach_z:
            errors.append(
                f"End-Sicherheits-Z {end_safe_z:.3f} mm liegt unter dem erforderlichen "
                f"Anfahr-Z {approach_z:.3f} mm der Position {idx}."
            )
    return errors


def validate_bgf_coordinate_list(
    positions: Sequence[BGFCoordinatePosition],
    policy: BGFDepthPolicy,
    *,
    safe_z: float,
    end_safe_z: float,
    approach_clearance: float,
) -> BGFCoordinateListValidation:
    result = BGFCoordinateListValidation(ok_for_nc=False)

    if not positions:
        result.errors.append("Keine Bearbeitungspositionen vorhanden.")
        return result

    safe_errors = validate_safe_z_against_surfaces(
        safe_z,
        end_safe_z,
        positions,
        approach_clearance=approach_clearance,
    )
    result.errors.extend(safe_errors)

    dups = find_duplicate_xyz(positions)
    if dups:
        sample = ", ".join(f"({x:g}|{y:g}|Z{z:g})" for x, y, z in dups[:5])
        result.warnings.append(f"Die Koordinatenliste enthaelt doppelte Positionen: {sample}")

    for idx, pos in enumerate(positions, start=1):
        ev = evaluate_bgf_depth(
            BGFDepthRequest(pos.thread_depth, pos.core_hole_depth),
            policy,
            surface_z=pos.surface_z,
        )
        row = PositionDepthStatus(
            index=idx,
            position=pos,
            ok_for_nc=ev.ok_for_nc,
            status_code=ev.status,
            status_label=status_label_for(ev.status),
            messages=list(ev.messages),
        )
        result.positions.append(row)
        if not ev.ok_for_nc:
            detail = ev.messages[0] if ev.messages else row.status_label
            result.errors.append(f"Position {idx}:\n{detail}")

    # Programmweites Gate: eine blockierte Position / unsicheres Z blockiert das gesamte Programm.
    result.ok_for_nc = (not safe_errors) and all(p.ok_for_nc for p in result.positions)
    return result
