"""Z-Offset relativ zur Werkstueckoberflaeche fuer CERATIZIT-BGF-Templates.

Z_abs = surface_z + Z_template
wobei Z_template = -depth_below_surface fuer Bearbeitungstiefen.

approach_z = surface_z + approach_clearance  (via above_surface)
"""

from __future__ import annotations

import math
from typing import Optional


DEFAULT_APPROACH_CLEARANCE = 1.0


def absolute_from_surface(surface_z: float, depth_below_surface: float) -> float:
    """Absolute Maschinen-Z aus Oberflaeche und positiver Herstellertiefe.

    Semantik: Z_abs = surface_z - depth_below_surface
    Beispiel: surface_z=35, depth=27.87 -> 7.13
    """
    return surface_z - depth_below_surface


def above_surface(surface_z: float, clearance: float = DEFAULT_APPROACH_CLEARANCE) -> float:
    """Anfahr-/Rueckzug-Z: surface_z + approach_clearance (Default 1 mm)."""
    return surface_z + clearance


def at_surface(surface_z: float) -> float:
    """Z genau auf der Werkstueckoberflaeche (bisher Z+0 im Template)."""
    return surface_z


def validate_approach_clearance(clearance: float) -> Optional[str]:
    """None wenn gueltig; sonst Fehlermeldung. Muss endlich und > 0 sein."""
    if not isinstance(clearance, (int, float)) or not math.isfinite(float(clearance)):
        return "Sicherheitsabstand ueber Oberflaeche muss eine endliche Zahl sein."
    if float(clearance) <= 0:
        return "Sicherheitsabstand ueber Oberflaeche muss groesser 0 mm sein."
    return None
