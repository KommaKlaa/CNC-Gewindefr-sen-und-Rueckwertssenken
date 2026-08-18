"""HEULE-BSF-Senkgeometrie-Hilfe – visuelle Darstellung (read-only)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional

from app_paths import apply_window_icon
from heule_bsf_tools import MEASUREMENT_LABEL
from help_views.bsf_geometry_model import (
    BSFGeometryHelpSnapshot,
    fmt_axis_z,
    fmt_mm,
    format_help_info,
    status_detail,
    status_headline,
)

_COLOR_BG = "#eef1f4"
_COLOR_FLANGE_A = "#c5ccd4"
_COLOR_FLANGE_B = "#b3bbc4"
_COLOR_FLANGE_LINE = "#2f353b"
_COLOR_TOOL = "#6d747c"
_COLOR_CUT = "#f0b429"
_COLOR_FINISH = "#1a7f37"
_COLOR_MEAS = "#0969da"
_COLOR_Z0 = "#cf222e"
_COLOR_AXIS = "#57606a"
_COLOR_TEXT = "#1f2328"
_COLOR_OK = "#1a7f37"
_COLOR_BLOCK = "#cf222e"


class BSFGeometryHelpWindow:
    def __init__(self, master: tk.Misc, *, snapshot_provider: Callable[[], BSFGeometryHelpSnapshot]) -> None:
        self._provider = snapshot_provider
        self.win = tk.Toplevel(master)
        self.win.title("HEULE BSF – Senkgeometrie")
        self.win.minsize(1000, 650)
        self.win.geometry("1100x720")
        apply_window_icon(self.win)

        self.snapshot: Optional[BSFGeometryHelpSnapshot] = None
        self._info_vars: Dict[str, tk.StringVar] = {}
        self._build_ui()
        self.refresh()
        self.canvas.bind("<Configure>", lambda _e: self._redraw_main())
        self.detail_canvas.bind("<Configure>", lambda _e: self._redraw_detail())

    def _build_ui(self) -> None:
        header = ttk.Frame(self.win, padding=(10, 8, 10, 4))
        header.pack(fill=tk.X)
        ttk.Label(
            header,
            text="HEULE BSF – Senkgeometrie   ·   READ ONLY",
            font=("Segoe UI", 11, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Button(header, text="Aktualisieren", command=self.refresh).pack(side=tk.RIGHT)

        status = ttk.Frame(self.win, padding=(10, 0, 10, 6))
        status.pack(fill=tk.X)
        self.status_head = ttk.Label(status, text="", font=("Segoe UI", 10, "bold"))
        self.status_head.pack(anchor=tk.W)
        self.status_sub = ttk.Label(status, text="", foreground=_COLOR_AXIS)
        self.status_sub.pack(anchor=tk.W)

        body = ttk.Frame(self.win, padding=(8, 0, 8, 8))
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=7)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=5)
        body.rowconfigure(1, weight=5)

        self.canvas = tk.Canvas(body, background=_COLOR_BG, highlightthickness=1, highlightbackground="#c8cdd2")
        self.canvas.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))

        detail_frame = ttk.LabelFrame(body, text="Werkzeugvermessung", padding=4)
        detail_frame.grid(row=0, column=1, sticky="nsew", pady=(0, 6))
        self.detail_canvas = tk.Canvas(detail_frame, background="#f7f8fa", highlightthickness=0, height=220)
        self.detail_canvas.pack(fill=tk.BOTH, expand=True)

        info_frame = ttk.LabelFrame(body, text="Aktuelle Geometrie", padding=8)
        info_frame.grid(row=1, column=1, sticky="nsew")
        self._build_info_panel(info_frame)

    def _build_info_panel(self, parent: ttk.Frame) -> None:
        rows = [
            ("sec_wp", "Werkstück", True),
            ("bund", "Bunddicke", False),
            ("sink", "Senk-Fertigmaß", False),
            ("clear", "Freifahrt", False),
            ("z0", "Bezugsebene", False),
            ("ref_z", "Z-Lage", False),
            ("sec_tool", "Werkzeug", True),
            ("tool", "HEULE Werkzeug", False),
            ("meas", "Vermessung", False),
            ("offset", "Halter -> Schneide", False),
            ("speed", "Aktivierungsdrehzahl", False),
            ("sec_nc", "NC", True),
            ("finish_z", "Schneidenziel Finish", False),
            ("clear_z", "Schneidenziel Freifahrt", False),
            ("holder_finish", "Halter-Z Finish", False),
            ("holder_clear", "Halter-Z Freifahrt", False),
        ]
        for r, (key, caption, section) in enumerate(rows):
            if section:
                ttk.Label(parent, text=caption, font=("Segoe UI", 9, "bold")).grid(
                    row=r, column=0, columnspan=2, sticky=tk.W, pady=(8 if r else 0, 2)
                )
                continue
            ttk.Label(parent, text=caption, foreground=_COLOR_AXIS).grid(
                row=r, column=0, sticky=tk.W, padx=(8, 12), pady=1
            )
            var = tk.StringVar(value="—")
            self._info_vars[key] = var
            ttk.Label(parent, textvariable=var).grid(row=r, column=1, sticky=tk.W, pady=1)
        parent.columnconfigure(1, weight=1)

    def refresh(self) -> None:
        self.snapshot = self._provider()
        self._update_status()
        self._update_info()
        self._redraw_main()
        self._redraw_detail()

    def _update_status(self) -> None:
        s = self.snapshot
        if s is None:
            return
        self.status_head.config(
            text=status_headline(s),
            foreground=_COLOR_BLOCK if s.nc_blocked else _COLOR_OK,
        )
        self.status_sub.config(text=status_detail(s))

    def _update_info(self) -> None:
        s = self.snapshot
        if s is None:
            return
        self._info_vars["bund"].set(fmt_mm(s.bund_thickness))
        self._info_vars["sink"].set(fmt_mm(s.sink_depth))
        self._info_vars["clear"].set(fmt_mm(s.clearance))
        self._info_vars["z0"].set("Unterkante Bund" if s.z0_is_flange_bottom else "Oberkante Bund")
        self._info_vars["ref_z"].set(fmt_axis_z(s.reference_z))
        self._info_vars["tool"].set(s.tool_profile.designation if s.tool_profile is not None else "—")
        self._info_vars["meas"].set(MEASUREMENT_LABEL)
        self._info_vars["offset"].set(
            fmt_mm(s.tool_profile.holder_to_cutting_edge_mm) if s.tool_profile is not None else "—"
        )
        self._info_vars["speed"].set(
            "—"
            if s.tool_profile is None or s.tool_profile.activation_speed_rpm is None
            else f"{s.tool_profile.activation_speed_rpm:d} U/min"
        )
        self._info_vars["finish_z"].set(fmt_axis_z(s.workpiece_z_sink_finish))
        self._info_vars["clear_z"].set(fmt_axis_z(s.workpiece_z_clearance))
        self._info_vars["holder_finish"].set(fmt_axis_z(s.programmed_holder_z_sink_finish))
        self._info_vars["holder_clear"].set(fmt_axis_z(s.programmed_holder_z_clearance))

    def info_dump(self) -> str:
        return format_help_info(self.snapshot) if self.snapshot is not None else ""

    def _redraw_main(self) -> None:
        self.canvas.delete("all")
        if self.snapshot is None:
            return
        w = float(self.canvas.winfo_width())
        h = float(self.canvas.winfo_height())
        if w < 80 or h < 80:
            return
        self._draw_main_cross_section(w, h)

    def _redraw_detail(self) -> None:
        self.detail_canvas.delete("all")
        if self.snapshot is None:
            return
        w = float(self.detail_canvas.winfo_width())
        h = float(self.detail_canvas.winfo_height())
        if w < 40 or h < 40:
            return
        self._draw_tool_detail(w, h)

    def _draw_main_cross_section(self, w: float, h: float) -> None:
        s = self.snapshot
        assert s is not None
        c = self.canvas

        c.create_text(12, 14, text="+Z ↑ zur Spindel", fill=_COLOR_FINISH, anchor="w", font=("Segoe UI", 9, "bold"))
        c.create_text(12, 30, text="-Z ↓ zur Werkzeugspitze", fill=_COLOR_AXIS, anchor="w", font=("Segoe UI", 9))
        c.create_text(w - 12, 14, text="SCHEMATISCH – NICHT MASSSTÄBLICH", fill=_COLOR_AXIS, anchor="e", font=("Segoe UI", 8))

        top = 90
        bottom = h - 90
        left = 130
        right = w - 210
        cx = (left + right) / 2
        hole_half = 22
        shaft_half = 10

        c.create_rectangle(left, top, cx - hole_half, bottom, fill=_COLOR_FLANGE_A, outline=_COLOR_FLANGE_LINE, tags=("flange",))
        c.create_rectangle(cx + hole_half, top, right, bottom, fill=_COLOR_FLANGE_B, outline=_COLOR_FLANGE_LINE, tags=("flange",))
        c.create_line(cx - hole_half, top, cx - hole_half, bottom, fill=_COLOR_AXIS, dash=(3, 2), tags=("hole",))
        c.create_line(cx + hole_half, top, cx + hole_half, bottom, fill=_COLOR_AXIS, dash=(3, 2), tags=("hole",))
        c.create_text(cx, (top + bottom) / 2, text="Bohrung", fill=_COLOR_AXIS, font=("Segoe UI", 8), tags=("hole",))

        c.create_rectangle(cx - shaft_half, top - 50, cx + shaft_half, bottom + 40, fill=_COLOR_TOOL, outline=_COLOR_FLANGE_LINE, tags=("tool",))
        c.create_text(cx, top - 62, text="SPINDEL / Werkzeug", fill=_COLOR_TEXT, font=("Segoe UI", 8, "bold"), tags=("tool",))
        c.create_text(cx + 40, top - 20, text="↑ SENKEN +Z", fill=_COLOR_FINISH, anchor="w", font=("Segoe UI", 10, "bold"), tags=("sink_arrow",))

        chamfer_w = 26
        chamfer_h = 18
        c.create_polygon(
            cx - hole_half, bottom - chamfer_h, cx - hole_half, bottom, cx - hole_half - chamfer_w, bottom,
            fill="#d8ead8", outline=_COLOR_FINISH, width=2, tags=("sink_finish",)
        )
        c.create_polygon(
            cx + hole_half, bottom - chamfer_h, cx + hole_half, bottom, cx + hole_half + chamfer_w, bottom,
            fill="#d8ead8", outline=_COLOR_FINISH, width=2, tags=("sink_finish",)
        )
        c.create_text(right + 14, bottom + 8, text="Senk-Fertigfläche", fill=_COLOR_FINISH, anchor="w", font=("Segoe UI", 8), tags=("sink_finish",))

        c.create_rectangle(cx - (hole_half + 26), bottom, cx + (hole_half + 26), bottom + 24, fill=_COLOR_CUT, outline=_COLOR_FLANGE_LINE, tags=("blade",))
        c.create_text(cx, bottom + 12, text="Schneide", fill=_COLOR_TEXT, font=("Segoe UI", 8, "bold"), tags=("blade",))

        dim_x = left - 28
        c.create_line(left, top, dim_x - 8, top, fill=_COLOR_TEXT, tags=("bund_dim",))
        c.create_line(left, bottom, dim_x - 8, bottom, fill=_COLOR_TEXT, tags=("bund_dim",))
        c.create_line(dim_x, top, dim_x, bottom, fill=_COLOR_TEXT, arrow=tk.BOTH, tags=("bund_dim",))
        c.create_text(
            dim_x - 8,
            (top + bottom) / 2,
            text=fmt_mm(s.bund_thickness).replace(" mm", "\nmm") if s.bund_thickness is not None else "—",
            fill=_COLOR_TEXT,
            anchor="e",
            font=("Segoe UI", 8, "bold"),
            tags=("bund_dim",),
        )

        c.create_text(right + 14, top, text="Oberkante Bund", fill=_COLOR_TEXT, anchor="w", font=("Segoe UI", 8))
        c.create_text(right + 14, bottom, text="Unterkante Bund", fill=_COLOR_TEXT, anchor="w", font=("Segoe UI", 8))

        z0_y = bottom if s.z0_is_flange_bottom else top
        edge = "Unterkante Bund" if s.z0_is_flange_bottom else "Oberkante Bund"
        caption = f"Bezugsebene · {edge}"
        if s.reference_z is not None:
            caption += f"\nZ-Lage {fmt_axis_z(s.reference_z)}"
        c.create_line(left - 6, z0_y, right + 6, z0_y, fill=_COLOR_Z0, width=2, dash=(7, 3), tags=("z0",))
        c.create_text(left - 12, z0_y - 14 if s.z0_is_flange_bottom else z0_y + 14, text=caption, fill=_COLOR_Z0, anchor="e", justify="right", font=("Segoe UI", 8, "bold"), tags=("z0",))

    def _draw_tool_detail(self, w: float, h: float) -> None:
        s = self.snapshot
        assert s is not None
        c = self.detail_canvas
        cx = w * 0.42
        y_meas = 55
        y_cut = h - 55
        label = s.tool_profile.designation if s.tool_profile is not None else "Kein Werkzeug"
        offset = "—" if s.tool_profile is None else fmt_mm(s.tool_profile.holder_to_cutting_edge_mm)

        c.create_text(cx, 16, text=label, fill=_COLOR_TEXT, font=("Segoe UI", 8, "bold"), tags=("tool_label",))
        c.create_line(cx, y_meas, cx, y_cut, fill=_COLOR_TOOL, width=14, tags=("tool",))
        c.create_line(cx - 36, y_meas, cx + 36, y_meas, fill=_COLOR_MEAS, width=3, tags=("measurement_face",))
        c.create_text(cx + 48, y_meas - 8, text="WERKZEUGVERMESSUNG", fill=_COLOR_MEAS, anchor="w", font=("Segoe UI", 8, "bold"), tags=("measurement_face",))
        c.create_text(cx + 48, y_meas + 8, text=MEASUREMENT_LABEL, fill=_COLOR_MEAS, anchor="w", font=("Segoe UI", 8), tags=("measurement_face",))

        c.create_line(cx - 24, y_cut, cx + 24, y_cut, fill=_COLOR_FINISH, width=3, tags=("finish_edge",))
        c.create_text(cx + 48, y_cut, text="FERTIGSCHNEIDE", fill=_COLOR_FINISH, anchor="w", font=("Segoe UI", 8, "bold"), tags=("finish_edge",))

        c.create_line(68, y_meas, 68, y_cut, fill=_COLOR_TEXT, arrow=tk.BOTH, tags=("offset_dim",))
        c.create_text(58, (y_meas + y_cut) / 2, text=offset.replace(" mm", "\nmm"), fill=_COLOR_TEXT, anchor="e", font=("Segoe UI", 8, "bold"), tags=("offset_dim",))


def open_bsf_geometry_help_window(master: tk.Misc, *, snapshot_provider: Callable[[], BSFGeometryHelpSnapshot]):
    return BSFGeometryHelpWindow(master, snapshot_provider=snapshot_provider)
