"""Paste-Parser fuer BGF-Koordinatenlisten (3/4/5 Spalten)."""

from __future__ import annotations

from typing import List, Optional

from .bgf_position import BGFCoordinatePosition
from .parser import CoordinateParseError, _split_fields, parse_number


def parse_bgf_coordinate_line(
    line: str,
    line_no: int,
    *,
    default_thread_depth: float,
) -> Optional[BGFCoordinatePosition]:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("#"):
        return None

    parts = [p for p in _split_fields(stripped) if p != ""]
    n = len(parts)
    if n < 3 or n > 5:
        raise CoordinateParseError(
            [
                f"Zeile {line_no}: erwartete 3, 4 oder 5 Werte "
                f"(X;Y;Z[;Gewindetiefe[;Kernloch]]), gefunden {n} "
                f"(Zeile: '{stripped}')"
            ]
        )

    def _num(token: str, field: str) -> float:
        try:
            return parse_number(token, line_no=line_no, raw_line=stripped)
        except CoordinateParseError:
            raise CoordinateParseError(
                [f'Zeile {line_no} ist ungueltig:\n{field} = "{token}"']
            ) from None

    x = _num(parts[0], "X")
    y = _num(parts[1], "Y")
    surface_z = _num(parts[2], "Z Oberflaeche")

    if n == 3:
        thread_depth = float(default_thread_depth)
        core = None
    elif n == 4:
        thread_depth = _num(parts[3], "Gewindetiefe")
        core = None
    else:
        thread_depth = _num(parts[3], "Gewindetiefe")
        core_raw = parts[4].strip()
        if core_raw == "":
            core = None
        else:
            core = _num(parts[4], "Kernlochtiefe")

    return BGFCoordinatePosition(
        x=x,
        y=y,
        surface_z=surface_z,
        thread_depth=thread_depth,
        core_hole_depth=core,
    )


def parse_bgf_coordinate_text(
    text: str,
    *,
    default_thread_depth: float,
) -> List[BGFCoordinatePosition]:
    errors: List[str] = []
    result: List[BGFCoordinatePosition] = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for idx, line in enumerate(lines, start=1):
        try:
            pos = parse_bgf_coordinate_line(
                line, idx, default_thread_depth=default_thread_depth
            )
        except CoordinateParseError as exc:
            errors.extend(exc.messages)
            continue
        if pos is not None:
            result.append(pos)

    if errors:
        raise CoordinateParseError(errors)
    if not result:
        raise CoordinateParseError(["Keine gueltigen Koordinaten gefunden."])
    return result
