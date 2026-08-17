"""CERATIZIT Herstellerblatt – reine Referenzdaten (keine Interpolation).

Kernlochtiefe hier ist die Tabellen-Solltiefe im Bauteil,
NICHT die NC-Werkzeugspitzenposition des Beispielprogramms.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class HoleType(str, Enum):
    BLIND = "BLIND"
    THROUGH = "THROUGH"  # Dulo / Durchgangsloch


@dataclass(frozen=True)
class ManufacturerDepthReference:
    thread_size: str
    thread_depth: float
    hole_type: HoleType
    core_hole_depth: Optional[float] = None
    note: str = ""


# Aus CERATIZIT-Herstellerblatt (Benutzerreferenz). Nicht interpolieren.
MANUFACTURER_DEPTH_REFERENCES: List[ManufacturerDepthReference] = [
    ManufacturerDepthReference("M6", 12.0, HoleType.BLIND, 18.0),
    ManufacturerDepthReference("M6", 16.0, HoleType.THROUGH, None, "Dulo"),
    ManufacturerDepthReference("M10", 17.0, HoleType.BLIND, 27.0),
    ManufacturerDepthReference("M10", 25.0, HoleType.BLIND, 30.0),
    ManufacturerDepthReference("M16x1.5", 20.0, HoleType.BLIND, 28.0),
    ManufacturerDepthReference("M16x1.5", 25.0, HoleType.BLIND, 32.0),
    ManufacturerDepthReference("M16", 20.0, HoleType.THROUGH, None, "Dulo"),
    ManufacturerDepthReference("M16", 26.0, HoleType.BLIND, 34.0),
    ManufacturerDepthReference("M16", 26.0, HoleType.BLIND, 36.0, "zweite Tabellenzeile"),
    ManufacturerDepthReference("M16", 35.0, HoleType.THROUGH, None, "Dulo"),
    ManufacturerDepthReference("M16", 50.0, HoleType.BLIND, 55.0),
]


def references_for_size(thread_size: str) -> List[ManufacturerDepthReference]:
    return [r for r in MANUFACTURER_DEPTH_REFERENCES if r.thread_size == thread_size]
