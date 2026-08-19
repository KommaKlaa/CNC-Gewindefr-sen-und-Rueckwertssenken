"""Rueckwaertskompatibler Wrapper fuer das neue BSF-Hilfefenster."""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from help_views.bsf_geometry_model import BSFGeometryHelpSnapshot, format_help_info
from ui.bsf_help_window import BSFHelpWindow, tool_detail_canvas_layout


class BSFGeometryHelpWindow(BSFHelpWindow):
    """Alias-Name fuer bestehende Aufrufer/Tests."""

    def info_dump(self) -> str:
        return format_help_info(self.snapshot) if self.snapshot is not None else ""


def open_bsf_geometry_help_window(master: tk.Misc, *, snapshot_provider: Callable[[], BSFGeometryHelpSnapshot]):
    return BSFGeometryHelpWindow(master, snapshot_provider=snapshot_provider)
