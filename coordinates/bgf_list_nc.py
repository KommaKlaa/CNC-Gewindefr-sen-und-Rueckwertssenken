"""NC-Emission fuer BGF-Koordinatenlisten (numerisch aufgeloeste surface_z)."""

from __future__ import annotations

from typing import Callable, List, Sequence

from bgf_surface import DEFAULT_APPROACH_CLEARANCE, above_surface

from .bgf_position import BGFCoordinatePosition
from .nc import fmt_axis, format_xy_rapid


def emit_bgf_coordinate_program_body(
    positions: Sequence[BGFCoordinatePosition],
    *,
    safe_z: float,
    end_safe_z: float,
    sequence_for_position: Callable[[BGFCoordinatePosition], List[str]],
    approach_clearance: float = DEFAULT_APPROACH_CLEARANCE,
) -> List[str]:
    """Pro Position: XY auf safe_z, Anfahrt approach_z, Herstellersequenz, Zurueck safe_z.

    approach_z = surface_z + approach_clearance (global fuer alle Positionen).
    sequence_for_position liefert die Herstellerbahn inkl. Axial-Shift-Tiefen der Position.
    """
    lines: List[str] = []
    lines.append("; --- KOORDINATENLISTE BGF ---")
    lines.append(f"L {fmt_axis('Z', safe_z)} R0 FMAX ; sicheres Z vor XY-Fahrten")

    for idx, pos in enumerate(positions, start=1):
        lines.append(
            f"; POSITION {idx}  X={pos.x:g} Y={pos.y:g} surface_z={pos.surface_z:g} "
            f"Gewindetiefe={pos.thread_depth:g} clearance={approach_clearance:g}"
        )
        lines.append(format_xy_rapid(pos.x, pos.y))
        z_app = above_surface(pos.surface_z, approach_clearance)
        lines.append(f"L {fmt_axis('Z', z_app)} R0 FMAX M13")
        lines.extend(sequence_for_position(pos))
        lines.append(f"L {fmt_axis('Z', safe_z)} R0 FMAX ; Rueckzug vor naechster XY-Fahrt")

    lines.append(f"L {fmt_axis('Z', end_safe_z)} R0 FMAX")
    return lines
