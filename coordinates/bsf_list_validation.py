"""Validierung einer HEULE-BSF-Koordinatenliste (nur X/Y, programmweites Gate)."""

from __future__ import annotations

from typing import List, Sequence

from .bsf_position import BSFCoordinatePosition
from .model import XYCoordinate
from .validation import CoordinateValidationResult, find_duplicate_xy, validate_coordinates


def as_xy(positions: Sequence[BSFCoordinatePosition]) -> List[XYCoordinate]:
    return [XYCoordinate(x=p.x, y=p.y, active=True) for p in positions]


def validate_bsf_coordinate_list(
    positions: Sequence[BSFCoordinatePosition],
) -> CoordinateValidationResult:
    return validate_coordinates(as_xy(positions))


def bsf_position_status_label(pos: BSFCoordinatePosition, positions: Sequence[BSFCoordinatePosition]) -> str:
    dups = set(find_duplicate_xy(as_xy(positions)))
    if (pos.x, pos.y) in dups:
        return "Doppelte XY-Position"
    return "OK"
