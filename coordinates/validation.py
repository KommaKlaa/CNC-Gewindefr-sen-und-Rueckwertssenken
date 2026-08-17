"""Validierung von XY-Koordinatenlisten."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from .model import XYCoordinate


@dataclass
class CoordinateValidationResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    active: List[XYCoordinate] = field(default_factory=list)


def find_duplicate_xy(coords: Sequence[XYCoordinate]) -> List[Tuple[float, float]]:
    """Findet doppelte aktive XY-Paare (Reihenfolge der ersten Funde)."""
    seen = set()
    duplicates: List[Tuple[float, float]] = []
    for c in coords:
        if not c.active:
            continue
        key = (c.x, c.y)
        if key in seen:
            if key not in duplicates:
                duplicates.append(key)
        else:
            seen.add(key)
    return duplicates


def validate_coordinates(coords: Sequence[XYCoordinate]) -> CoordinateValidationResult:
    errors: List[str] = []
    warnings: List[str] = []
    active: List[XYCoordinate] = []

    for idx, c in enumerate(coords, start=1):
        if not c.active:
            continue
        if not isinstance(c.x, (int, float)) or not isinstance(c.y, (int, float)):
            errors.append(f"Position {idx}: X/Y nicht numerisch.")
            continue
        if not math.isfinite(float(c.x)) or not math.isfinite(float(c.y)):
            errors.append(f"Position {idx}: X/Y ist NaN oder Infinity.")
            continue
        active.append(XYCoordinate(x=float(c.x), y=float(c.y), active=True))

    if not active:
        errors.append("Mindestens eine aktive Koordinate ist erforderlich.")

    duplicates = find_duplicate_xy(active)
    if duplicates:
        sample = ", ".join(f"({x:g}|{y:g})" for x, y in duplicates[:5])
        more = "" if len(duplicates) <= 5 else f" u.a. ({len(duplicates)} Duplikat-Paare)"
        warnings.append(f"Die Koordinatenliste enthaelt doppelte Positionen: {sample}{more}")

    return CoordinateValidationResult(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        active=active,
    )
