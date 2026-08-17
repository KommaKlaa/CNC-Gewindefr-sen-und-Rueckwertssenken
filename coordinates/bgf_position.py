"""BGF-Koordinatenlisten-Positionen (X/Y/Oberflaeche/Gewindetiefe)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BGFCoordinatePosition:
    x: float
    y: float
    surface_z: float
    thread_depth: float
    core_hole_depth: Optional[float] = None
