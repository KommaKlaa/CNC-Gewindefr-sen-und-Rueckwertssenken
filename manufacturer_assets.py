"""Lokale Hersteller-Assets (ohne Download/Netzwerk)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app_paths import resource_path

HEULE_BSF_PROCESS_REFERENCE_REL = "assets/manufacturer/heule/bsf_process_reference.png"

HEULE_ATTRIBUTION_TEXT = (
    "Abbildung/Quelle: HEULE – Herstellerunterlage "
    "'Prozessablauf BSF / Anwendungs- und Programmierbeispiel'."
)
HEULE_DISCLAIMER_TEXT = (
    "Die dargestellten Herstellerwerte sind Beispielwerte und gelten "
    "nicht automatisch fuer das aktuell ausgewaehlte Werkzeug."
)
HEULE_MISSING_ASSET_TEXT = "Originale HEULE-Herstellerabbildung ist lokal nicht installiert."


def get_heule_bsf_reference_image_path() -> Optional[Path]:
    """Gibt den absoluten Pfad zum lokalen Originalasset zurueck, falls vorhanden."""
    path = resource_path(HEULE_BSF_PROCESS_REFERENCE_REL)
    if path.is_file():
        return path
    return None
