"""Rohteil-Z-Ausdehnung fuer BLK FORM.

Getrennt von der Bearbeitungsflaeche (surface_z). Keine NC-Bahnlogik.
"""

from __future__ import annotations

from typing import Iterable, Tuple

SURFACE_OUTSIDE_STOCK_MESSAGE = "Bohrungsanfang Z liegt außerhalb der Rohteilhöhe."


def blk_form_z_extents(raw_stock_top_z: float, blank_height: float) -> Tuple[float, float]:
    """z_min, z_max fuer BLK FORM. Nur raw_stock_top_z und blank_height."""
    z_max = raw_stock_top_z
    z_min = raw_stock_top_z - blank_height
    return z_min, z_max


def is_surface_inside_stock(surface_z: float, raw_stock_top_z: float, blank_height: float) -> bool:
    z_min, z_max = blk_form_z_extents(raw_stock_top_z, blank_height)
    return z_min <= surface_z <= z_max


def all_surfaces_inside_stock(
    surfaces: Iterable[float],
    raw_stock_top_z: float,
    blank_height: float,
) -> bool:
    return all(
        is_surface_inside_stock(surface_z, raw_stock_top_z, blank_height) for surface_z in surfaces
    )
