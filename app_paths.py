"""Zentrale Resource-Pfade fuer App-Assets.

Primaerer Packaging-Weg: Nuitka Standalone.
Direkter Python-Start bleibt unveraendert.
"""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from pathlib import Path
from typing import Iterable, List

logger = logging.getLogger(__name__)

APP_ICON_ICO_REL = "assets/app_icon.ico"
APP_ICON_PNG_REL = "assets/app_icon.png"


def _unique_bases(bases: Iterable[Path]) -> List[Path]:
    seen = set()
    out: List[Path] = []
    for base in bases:
        resolved = base.resolve()
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def runtime_base_candidates() -> List[Path]:
    """Moegliche Wurzeln fuer Assets: Nuitka-Dist, Legacy-Bundle, Sourcebaum."""
    bases: List[Path] = []
    frozen = bool(getattr(sys, "frozen", False))
    compiled = globals().get("__compiled__") is not None
    meipass = getattr(sys, "_MEIPASS", None)

    if compiled or (frozen and not meipass):
        bases.append(Path(sys.executable).resolve().parent)
    if frozen and meipass:
        bases.append(Path(meipass))
    bases.append(Path(__file__).resolve().parent)
    if frozen or compiled:
        bases.append(Path(sys.executable).resolve().parent)
    return _unique_bases(bases)


def resource_path(relative_path: str) -> Path:
    """Absoluter Asset-Pfad, unabhaengig vom aktuellen Working Directory.

    Reihenfolge:
    1. Nuitka-Standalone (sys.frozen / __compiled__) neben der EXE
    2. optionales Legacy-Bundle-Verzeichnis (sys._MEIPASS), falls gesetzt
    3. Sourcebaum neben dieser Datei
    """
    rel = Path(relative_path)
    candidates = runtime_base_candidates()
    for base in candidates:
        path = (base / rel).resolve()
        if path.exists():
            return path
    return (candidates[0] / rel).resolve()


def apply_window_icon(window, *, ico_relative: str = APP_ICON_ICO_REL) -> bool:
    """Setzt das Programm-Icon. Fehlende Datei oder Tcl-Fehler: still, kein Absturz."""
    ico = resource_path(ico_relative)
    if not ico.is_file():
        logger.debug("App-Icon nicht gefunden: %s", ico)
        return False
    try:
        path = str(ico)
        window.iconbitmap(path)
        try:
            window.iconbitmap(default=path)
        except tk.TclError:
            pass
        return True
    except (tk.TclError, OSError) as exc:
        logger.debug("App-Icon konnte nicht gesetzt werden: %s", exc)
        return False
