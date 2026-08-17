"""Datenmodell fuer Positionsmodi und XY-Koordinaten."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PositionMode(str, Enum):
    CIRCLE = "CIRCLE"
    SINGLE = "SINGLE"
    COORDINATES = "COORDINATES"


@dataclass(frozen=True)
class XYCoordinate:
    x: float
    y: float
    active: bool = True
