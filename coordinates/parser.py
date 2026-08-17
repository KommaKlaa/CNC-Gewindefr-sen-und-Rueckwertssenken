"""Parser fuer Copy&Paste-Koordinatenlisten.

Feldtrenner (bevorzugt, eindeutig):
- Tabulator
- Semikolon
- Whitespace

Dezimaltrenner innerhalb eines Feldes:
- Punkt, oder
- Komma (nur wenn das Feld keinen Punkt enthaelt)

Komma wird niemals gleichzeitig als Feld- und Dezimaltrenner verwendet.
Eine Zeile wie \"100,200\" ohne Tab/Semikolon/Whitespace-Trennung ist ungueltig.
"""

from __future__ import annotations

import math
import re
from typing import List

from .model import XYCoordinate


class CoordinateParseError(Exception):
    """Eine oder mehrere Zeilen konnten nicht geparst werden."""

    def __init__(self, messages: List[str]):
        self.messages = messages
        super().__init__("\n".join(messages))


_FIELD_SPLIT_WHITESPACE = re.compile(r"\s+")


def parse_number(token: str, *, line_no: int, raw_line: str) -> float:
    value = token.strip()
    if not value:
        raise CoordinateParseError(
            [f"Zeile {line_no}: leeres Zahlenfeld in '{raw_line}'"]
        )

    if "," in value and "." in value:
        raise CoordinateParseError(
            [
                f"Zeile {line_no}: gemischte Dezimaltrenner in '{value}' "
                f"(Zeile: '{raw_line}')"
            ]
        )

    if "," in value:
        value = value.replace(",", ".")

    try:
        number = float(value)
    except ValueError as exc:
        raise CoordinateParseError(
            [f"Zeile {line_no}: ungueltige Zahl '{token}' (Zeile: '{raw_line}')"]
        ) from exc

    if not math.isfinite(number):
        raise CoordinateParseError(
            [f"Zeile {line_no}: Zahl ist nicht endlich '{token}' (Zeile: '{raw_line}')"]
        )

    return number


def _split_fields(line: str) -> List[str]:
    if "\t" in line:
        return [part.strip() for part in line.split("\t")]
    if ";" in line:
        return [part.strip() for part in line.split(";")]
    return [part for part in _FIELD_SPLIT_WHITESPACE.split(line.strip()) if part]


def parse_coordinate_line(line: str, line_no: int) -> XYCoordinate | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("#") or stripped.startswith(";"):
        return None

    parts = _split_fields(stripped)
    parts = [p for p in parts if p != ""]

    if len(parts) == 2 and parts[0].upper() == "X" and parts[1].upper() == "Y":
        return None

    if len(parts) < 2:
        raise CoordinateParseError(
            [f"Zeile {line_no}: Y-Wert fehlt (Zeile: '{stripped}')"]
        )
    if len(parts) > 2:
        raise CoordinateParseError(
            [
                f"Zeile {line_no}: erwartete genau 2 Werte (X Y), "
                f"gefunden {len(parts)} (Zeile: '{stripped}')"
            ]
        )

    x = parse_number(parts[0], line_no=line_no, raw_line=stripped)
    y = parse_number(parts[1], line_no=line_no, raw_line=stripped)
    return XYCoordinate(x=x, y=y, active=True)


def parse_coordinate_text(text: str) -> List[XYCoordinate]:
    """Parst mehrzeiligen Paste-Text. Bei Fehlern: Abbruch mit allen Meldungen."""
    errors: List[str] = []
    result: List[XYCoordinate] = []

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for idx, line in enumerate(lines, start=1):
        try:
            coord = parse_coordinate_line(line, idx)
        except CoordinateParseError as exc:
            errors.extend(exc.messages)
            continue
        if coord is not None:
            result.append(coord)

    if errors:
        raise CoordinateParseError(errors)

    if not result:
        raise CoordinateParseError(["Keine gueltigen Koordinaten gefunden."])

    return result
