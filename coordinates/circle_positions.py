"""Teilkreis-XY-Positionen (Heidenhain LP PR / PA Semantik).

Winkel: Grad, positiv gegen den Uhrzeigersinn.
PA=0 entlang +X, PA=90 entlang +Y.

Dies ist dieselbe Semantik wie im NC-Teilkreis-Schleifenkopf
(LP PR+radius PA+Q1).
"""

from __future__ import annotations

import math
from typing import List, Tuple


def compute_circle_xy_positions(
    *,
    center_x: float,
    center_y: float,
    diameter: float,
    count: int,
    start_angle_deg: float,
) -> List[Tuple[float, float]]:
    """Liefert (x, y) in NC-Bearbeitungsreihenfolge."""
    if count <= 0:
        raise ValueError("Anzahl Bohrungen muss groesser 0 sein.")
    if diameter <= 0:
        raise ValueError("Teilkreis-Durchmesser muss groesser 0 sein.")

    radius = diameter / 2.0
    step = 360.0 / float(count)
    result: List[Tuple[float, float]] = []
    for i in range(count):
        angle = start_angle_deg + i * step
        rad = math.radians(angle)
        x = center_x + radius * math.cos(rad)
        y = center_y + radius * math.sin(rad)
        result.append((x, y))
    return result
