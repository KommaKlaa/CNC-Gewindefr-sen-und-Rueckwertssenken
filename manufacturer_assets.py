"""Lokale Hersteller-Assets (ohne Download/Netzwerk, ohne Repo-Commit)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from app_info import APP_NAME
from app_paths import resource_path
from safety_notice import load_settings, save_settings, user_settings_path

HEULE_BSF_PROCESS_REFERENCE_REL = "assets/manufacturer/heule/bsf_process_reference.png"
SETTINGS_KEY_HEULE_IMAGE = "heule_bsf_reference_image_path"
IMAGE_SCALER = "TK_ONLY"

HEULE_ATTRIBUTION_TEXT = (
    "Abbildung/Quelle: HEULE – Herstellerunterlage "
    "'Prozessablauf BSF / Anwendungs- und Programmierbeispiel'."
)
HEULE_DISCLAIMER_TEXT = (
    "Die dargestellten Herstellerwerte sind Beispielwerte und gelten "
    "nicht automatisch fuer das aktuell ausgewaehlte Werkzeug. "
    "Herstellerabbildung zur Prozessreferenz. Der tatsaechliche "
    "Werkstuecknullpunkt wird beim Einrichten festgelegt."
)
HEULE_MISSING_ASSET_TEXT = "Keine lokale HEULE-Herstellerabbildung ausgewaehlt."


def heule_local_asset_dir() -> Path:
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        return Path(appdata) / APP_NAME / "manufacturer" / "heule"
    return Path.home() / ".nc-code-generator" / "manufacturer" / "heule"


def get_bundled_heule_bsf_reference_image_path() -> Optional[Path]:
    path = resource_path(HEULE_BSF_PROCESS_REFERENCE_REL)
    if path.is_file():
        return path
    return None


def get_configured_heule_image_path() -> Optional[Path]:
    data = load_settings()
    raw = data.get(SETTINGS_KEY_HEULE_IMAGE)
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw.strip())
    if path.is_file():
        return path
    return None


def get_heule_bsf_reference_image_path() -> Optional[Path]:
    """Lokale Benutzerauswahl hat Vorrang vor optionalem Bundle-Asset."""
    configured = get_configured_heule_image_path()
    if configured is not None:
        return configured
    return get_bundled_heule_bsf_reference_image_path()


def set_heule_bsf_reference_image(source_path: Path, *, copy_to_appdata: bool = True) -> Path:
    """Speichert lokalen Pfad in settings.json; optional Kopie nach AppData."""
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(str(source))
    suffix = source.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("Nur PNG/JPG/JPEG erlaubt.")
    if copy_to_appdata:
        dest_dir = heule_local_asset_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"bsf_process_reference{suffix}"
        shutil.copy2(source, dest)
        stored = dest
    else:
        stored = source.resolve()
    data = load_settings()
    data[SETTINGS_KEY_HEULE_IMAGE] = str(stored)
    save_settings(data)
    return stored


def clear_heule_bsf_reference_image(*, delete_local_copy: bool = False) -> None:
    data = load_settings()
    raw = data.pop(SETTINGS_KEY_HEULE_IMAGE, None)
    save_settings(data)
    if delete_local_copy and isinstance(raw, str):
        path = Path(raw)
        try:
            if path.is_file() and heule_local_asset_dir() in path.parents:
                path.unlink()
        except OSError:
            pass


def image_scaler_mode() -> str:
    return IMAGE_SCALER
