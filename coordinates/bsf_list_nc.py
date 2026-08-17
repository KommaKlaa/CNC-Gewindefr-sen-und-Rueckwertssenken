"""NC-Koerper fuer HEULE-BSF-Koordinatenliste (inline, gleiche Sequenz wie Einzelposition)."""

from __future__ import annotations

from typing import Callable, List, Sequence

from .bsf_position import BSFCoordinatePosition


def emit_bsf_coordinate_program_body(
    positions: Sequence[BSFCoordinatePosition],
    *,
    sequence_lines: Sequence[str],
    safe_z: float,
    fmt_axis: Callable[..., str],
) -> List[str]:
    """Pro Position: vollstaendige BSF-Sequenz, XY nur auf safe_z.

    Erste Position: X/Y zusammen mit safe_z (wie Einzelposition).
    Folgende Positionen: nur X/Y, Z bleibt auf dem Sequenz-Ende (safe_z).
    Aufrufer haengt end_safe_z / M30 an.
    """
    lines: List[str] = []
    lines.append("; --- KOORDINATENLISTE BSF ---")
    lines.append("; POSITIONIERUNG: KOORDINATENLISTE")
    lines.append(f"; ANZAHL POSITIONEN: {len(positions)}")
    for idx, pos in enumerate(positions, start=1):
        lines.append(
            f"; POSITION {idx}  {fmt_axis('X', pos.x)} {fmt_axis('Y', pos.y)}"
        )
        if idx == 1:
            lines.append(
                f"L {fmt_axis('X', pos.x)} {fmt_axis('Y', pos.y)} "
                f"{fmt_axis('Z', safe_z)} R0 FMAX"
            )
        else:
            lines.append(f"L {fmt_axis('X', pos.x)} {fmt_axis('Y', pos.y)} R0 FMAX")
        lines.extend(sequence_lines)
    return lines
