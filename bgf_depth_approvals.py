"""Software-freigegebene max. Gewindetiefen je BGF-Werkzeug (Artikel).

Diese Werte sind KEINE physikalisch garantierten Werkzeugmaxima.
Sie sind Software-Freigabegrenzen: bis zu dieser Gewindetiefe liegt fuer den
konkreten Artikel mindestens das im Projekt verwendete CERATIZIT-NC-Beispiel vor.

Spaeter hoehere Freigaben nur hier erhoehen – nicht in GUI/Generator-Logik.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple


# Key: (thread_size, article_no) -> approved_max_thread_depth [mm]
# Quelle: Hersteller-Beispiel-Gewindelaenge im vorliegenden NC-Template (BGF_DATA.thread_length).
APPROVED_MAX_THREAD_DEPTH_BY_TOOL: Dict[Tuple[str, str], float] = {
    ("M5", "5089805000"): 12.58,
    ("M6", "5089806000"): 14.69,
    ("M8", "5089808000"): 20.88,
    ("M10", "5089810000"): 25.06,
    ("M16", "5086916000"): 32.96,
    ("M16x1.5", "Sonderwerkzeug"): 32.60,
}


def approved_max_thread_depth(thread_size: str, article_no: str) -> Optional[float]:
    """Liefert die Software-Freigabegrenze oder None, wenn nicht hinterlegt."""
    return APPROVED_MAX_THREAD_DEPTH_BY_TOOL.get((thread_size, article_no))
