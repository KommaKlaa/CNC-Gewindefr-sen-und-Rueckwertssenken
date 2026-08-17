"""HEULE-BSF-Koordinatenlisten-Positionen (nur X/Y)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BSFCoordinatePosition:
    x: float
    y: float
