"""Read-only Anzeige der aktuellen BSF-Geometrie (Tab Aktuelle Werte)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from bsf_workpiece_geometry import Z0_EXAMPLES
from help_views.bsf_geometry_model import BSFGeometryHelpSnapshot, fmt_axis_z, fmt_mm
from ui.bsf_safe_status import STATUS_OK, STATUS_TOO_LOW, fmt_axis_z as fmt_safe_z

_COLOR = {
    "A": "#1f883d",
    "X": "#0969da",
    "B": "#8250df",
    "C": "#bf3989",
    "D": "#cf222e",
    "Z0": "#1f2328",
    "target": "#1f883d",
    "safe_ok": "#1f883d",
    "safe_warn": "#bf8700",
    "safe_bad": "#cf222e",
}


class BSFCurrentValuesPanel:
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_use_current: Callable[[], None],
        on_use_example: Callable[[int], None],
    ) -> None:
        self.frame = ttk.Frame(master)
        self._on_use_current = on_use_current
        self._on_use_example = on_use_example
        self._mode_var = tk.StringVar(value="Aktuelle GUI-Werte")

        top = ttk.LabelFrame(self.frame, text="Quelle", padding=6)
        top.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(top, text="Aktuelle Geometrie", command=self._on_use_current).pack(fill=tk.X, pady=2)
        for idx, ex in enumerate(Z0_EXAMPLES):
            ttk.Button(top, text=ex["name"], command=lambda i=idx: self._on_use_example(i)).pack(fill=tk.X, pady=2)
        ttk.Label(top, textvariable=self._mode_var, foreground="#57606a", wraplength=900).pack(anchor=tk.W, pady=(4, 0))

        body = ttk.Frame(self.frame)
        body.pack(fill=tk.BOTH, expand=True)
        self._sections: dict[str, ttk.LabelFrame] = {}
        for key, title in (
            ("werkstueck", "WERKSTUECK"),
            ("werkzeug", "WERKZEUG"),
            ("prozess", "PROZESSPOSITIONEN"),
            ("sicherheit", "SICHERHEIT"),
        ):
            lf = ttk.LabelFrame(body, text=title, padding=8)
            lf.pack(fill=tk.X, pady=(0, 8), anchor=tk.N)
            self._sections[key] = lf

        self._rows: dict[str, tuple[ttk.Label, ttk.Label]] = {}

    def pack(self, **kwargs) -> None:
        self.frame.pack(**kwargs)

    def set_mode_label(self, text: str) -> None:
        self._mode_var.set(text)

    def _row(self, section: str, label: str, *, color: str = "#1f2328") -> ttk.Label:
        lf = self._sections[section]
        row = ttk.Frame(lf)
        row.pack(fill=tk.X, pady=2)
        left = ttk.Label(row, text=label, width=22, anchor=tk.W)
        left.pack(side=tk.LEFT)
        right = ttk.Label(row, text="—", anchor=tk.W, foreground=color)
        right.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._rows[f"{section}:{label}"] = (left, right)
        return right

    def update_snapshot(self, snap: Optional[BSFGeometryHelpSnapshot]) -> None:
        for lf in self._sections.values():
            for child in lf.winfo_children():
                child.destroy()
        self._rows.clear()
        if snap is None:
            return

        tool = snap.tool_profile
        self._set("werkstueck", "Z0", fmt_axis_z(snap.z0), _COLOR["Z0"])
        self._set("werkstueck", "Eintritt", fmt_axis_z(snap.entry_edge_z))
        self._set("werkstueck", "Austritt", fmt_axis_z(snap.exit_edge_z))
        self._set("werkstueck", "Ziel-Senkflaeche", fmt_axis_z(snap.target_surface_z), _COLOR["target"])
        self._set("werkstueck", "Rohflaeche", fmt_axis_z(snap.raw_surface_z))
        self._set("werkstueck", "Senktiefe", fmt_mm(snap.sink_depth))
        self._set("werkstueck", "Materialabtrag", fmt_mm(snap.material_removal))

        self._set("werkzeug", "Typ", tool.designation if tool else "—")
        self._set("werkzeug", "Hs", fmt_mm(tool.measurement_face_to_cutting_edge_mm if tool else None))
        self._set("werkzeug", "AL", fmt_mm(tool.deployment_length_al_mm if tool else None))
        spindle = tool.activation_speed_rpm if tool else None
        self._set("werkzeug", "Aktivierungsdrehzahl", f"{int(spindle)} U/min" if spindle else "—")

        self._set("prozess", "A", fmt_axis_z(snap.a_z), _COLOR["A"])
        self._set("prozess", "X", fmt_axis_z(snap.x_z), _COLOR["X"])
        self._set("prozess", "B", fmt_axis_z(snap.b_z), _COLOR["B"])
        self._set("prozess", "C", fmt_axis_z(snap.c_z), _COLOR["C"])
        self._set("prozess", "D", fmt_axis_z(snap.d_z), _COLOR["D"])

        safe_color = _COLOR["safe_ok"]
        if snap.safe_status == STATUS_TOO_LOW:
            safe_color = _COLOR["safe_bad"]
        elif snap.safe_status != STATUS_OK:
            safe_color = _COLOR["safe_warn"]
        self._set("sicherheit", "Safe-Z", fmt_safe_z(snap.safe_z), safe_color)
        self._set("sicherheit", "Min-Safe-Z", fmt_safe_z(snap.required_safe_z), _COLOR["safe_warn"])
        reserve = "—"
        if snap.required_safe_z is not None and snap.safe_z is not None:
            reserve = f"{float(snap.safe_z) - float(snap.required_safe_z):.3f} mm"
        self._set("sicherheit", "Reserve", reserve)
        status = "OK" if snap.safe_status == STATUS_OK else ("ZU NIEDRIG" if snap.safe_status == STATUS_TOO_LOW else snap.safe_status)
        self._set("sicherheit", "Status", status, safe_color)
        self._set("sicherheit", "End-Safe", fmt_safe_z(snap.end_safe_z))

        if snap.notes:
            notes = ttk.LabelFrame(self.frame, text="HINWEISE", padding=8)
            notes.pack(fill=tk.X, pady=(0, 8))
            for n in snap.notes:
                ttk.Label(notes, text=f"• {n}", wraplength=900, foreground="#57606a").pack(anchor=tk.W)

    def _set(self, section: str, label: str, value: str, color: str = "#1f2328") -> None:
        lf = self._sections[section]
        row = ttk.Frame(lf)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=22, anchor=tk.W).pack(side=tk.LEFT)
        ttk.Label(row, text=value, anchor=tk.W, foreground=color).pack(side=tk.LEFT, fill=tk.X, expand=True)
