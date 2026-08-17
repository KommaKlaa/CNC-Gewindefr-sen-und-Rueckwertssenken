"""NC-Positionsausgabe fuer freie XY-Koordinatenlisten (iTNC 530 Klartext)."""

from __future__ import annotations

from typing import List, Sequence

from .model import XYCoordinate


def fmt_axis(axis: str, value: float, decimals: int = 4) -> str:
    sign = "+" if value >= 0 else ""
    return f"{axis}{sign}{value:.{decimals}f}"


def format_xy_rapid(x: float, y: float) -> str:
    """Eilgang-Positionierung in der XY-Ebene (ohne Z)."""
    return f"L {fmt_axis('X', x)} {fmt_axis('Y', y)} R0 FMAX"


def emit_coordinate_calls(
    coords: Sequence[XYCoordinate],
    *,
    sub_label: int = 100,
) -> List[str]:
    """Erzeugt Positionsbloecke mit CALL LBL in Listenreihenfolge.

    Voraussetzung: Vor dem ersten XY-Satz und nach jedem Unterprogramm
    befindet sich das Werkzeug auf safe_z (durch Aufrufer / LBL-Sequenz).
    """
    lines: List[str] = []
    lines.append("; --- KOORDINATENLISTE ---")
    for idx, c in enumerate(coords, start=1):
        lines.append(f"; POSITION {idx}")
        lines.append(format_xy_rapid(c.x, c.y))
        lines.append(f"CALL LBL {sub_label}")
    return lines
