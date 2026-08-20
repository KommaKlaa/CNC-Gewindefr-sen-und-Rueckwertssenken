"""Freigegebene App-Hilfsgrafiken (nicht vertrauliche HEULE-Originale)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app_paths import resource_path

BSF_GEOMETRY_REFERENCE_REL = "assets/help/bsf_heule_geometry_reference.png"

BSF_HELP_MISSING_TEXT = "BSF-Geometriehilfe konnte nicht geladen werden."

BSF_HELP_EXAMPLE_NOTE = (
    "Beispielhafte Darstellung.\n"
    "Die aktuellen Z-Werte ergeben sich aus dem aktiven Werkstuecknullpunkt "
    "und den Eingaben im BSF-Bereich."
)

BSF_HELP_Z0_NOTE = (
    "Z0 kann beim Einrichten an einer anderen Werkstueckflaeche liegen. "
    "Dadurch aendern sich die absoluten Z-Werte, nicht jedoch die Prozessgeometrie."
)

BSF_HELP_ATTRIBUTION = (
    "Grafik nach HEULE-Prozessreferenz, fuer die Anwendung schematisch aufbereitet."
)


def get_bsf_geometry_reference_image_path() -> Optional[Path]:
    path = resource_path(BSF_GEOMETRY_REFERENCE_REL)
    if path.is_file():
        return path
    return None


def help_image_scaler_mode() -> str:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return "TK_ONLY"
    return "PIL"
