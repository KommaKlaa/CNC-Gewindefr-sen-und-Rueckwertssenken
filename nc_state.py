"""Erkennung von veraltetem NC-Text nach Parameteraenderung.

Kein Einfluss auf NC-Geometrie. Nur State-/Safety-Handling vor Export/Clipboard.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Sequence

NC_STATE_CURRENT = "CURRENT"
NC_STATE_STALE = "STALE"
NC_STATE_EMPTY = "EMPTY"

STATUS_CURRENT_TEXT = "NC-Code aktuell"
STATUS_STALE_TEXT = "NC-Code veraltet – bitte neu generieren"
STATUS_EMPTY_TEXT = "Kein NC-Code erzeugt"

STALE_ACTION_MESSAGE = (
    "Die Eingaben wurden seit der letzten NC-Generierung geändert.\n\n"
    "Der angezeigte NC-Code ist nicht mehr aktuell.\n\n"
    "Bitte zuerst 'NC-Code generieren' ausführen."
)


def _entry_text(app, key: str) -> str:
    widget = getattr(app, "entries", {}).get(key)
    if widget is None:
        return ""
    try:
        return str(widget.get())
    except Exception:
        return ""


def _var_text(var) -> str:
    if var is None:
        return ""
    try:
        return str(var.get())
    except Exception:
        return ""


def _bgf_rows(rows: Sequence[Any]) -> List[List[Any]]:
    out: List[List[Any]] = []
    for row in rows:
        out.append(
            [
                getattr(row, "x", None),
                getattr(row, "y", None),
                getattr(row, "surface_z", None),
                getattr(row, "thread_depth", None),
                getattr(row, "core_hole_depth", None),
            ]
        )
    return out


def _bsf_rows(rows: Sequence[Any]) -> List[List[Any]]:
    out: List[List[Any]] = []
    for row in rows:
        out.append([getattr(row, "x", None), getattr(row, "y", None)])
    return out


def collect_nc_input_payload(app) -> Dict[str, Any]:
    """Kanonischer Snapshot aller NC-relevanten Eingaben."""
    entries = {}
    for key in sorted(getattr(app, "entries", {})):
        entries[key] = _entry_text(app, key)
    return {
        "mode": _var_text(getattr(app, "mode_var", None)),
        "position_mode": _var_text(getattr(app, "position_mode_var", None)),
        "programmer": _var_text(getattr(app, "programmer_var", None)),
        "tool_num": _var_text(getattr(app, "_tool_num_var", None)),
        "bgf_size": _var_text(getattr(app, "bgf_size_var", None)),
        "output_tool_def": _var_text(getattr(app, "output_tool_def_var", None)),
        "bsf_tool_profile": _var_text(getattr(app, "bsf_tool_profile_var", None)),
        "z_reference": _var_text(getattr(app, "z0_var", None)),
        "reduce_approach": _var_text(getattr(app, "reduce_approach_var", None)),
        "m_activate": _var_text(getattr(app, "m_activate_var", None)),
        "m_deactivate": _var_text(getattr(app, "m_deactivate_var", None)),
        "m_activate_custom": _entry_like(getattr(app, "m_activate_custom", None)),
        "m_deactivate_custom": _entry_like(getattr(app, "m_deactivate_custom", None)),
        "entries": entries,
        "bgf_coord_rows": _bgf_rows(getattr(app, "coord_rows", []) or []),
        "bsf_coord_rows": _bsf_rows(getattr(app, "bsf_coord_rows", []) or []),
    }


def _entry_like(widget) -> str:
    if widget is None:
        return ""
    try:
        return str(widget.get())
    except Exception:
        return ""


def fingerprint_nc_inputs(app) -> str:
    payload = collect_nc_input_payload(app)
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class NcOutputGuard:
    def __init__(self) -> None:
        self.generated_input_fingerprint: Optional[str] = None

    def mark_generated(self, app) -> str:
        digest = fingerprint_nc_inputs(app)
        self.generated_input_fingerprint = digest
        return digest

    def clear(self) -> None:
        self.generated_input_fingerprint = None

    def nc_state(self, app, *, output_text: str = "") -> str:
        if not (output_text or "").strip() or self.generated_input_fingerprint is None:
            return NC_STATE_EMPTY
        if fingerprint_nc_inputs(app) != self.generated_input_fingerprint:
            return NC_STATE_STALE
        return NC_STATE_CURRENT

    def is_current(self, app, *, output_text: str = "") -> bool:
        return self.nc_state(app, output_text=output_text) == NC_STATE_CURRENT

    def status_text(self, app, *, output_text: str = "") -> str:
        state = self.nc_state(app, output_text=output_text)
        if state == NC_STATE_CURRENT:
            return STATUS_CURRENT_TEXT
        if state == NC_STATE_STALE:
            return STATUS_STALE_TEXT
        return STATUS_EMPTY_TEXT
