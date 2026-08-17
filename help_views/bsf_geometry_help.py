"""HEULE-BSF-Senkgeometrie-Hilfe – visuelle Darstellung (read-only)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional

from app_paths import apply_window_icon
from bsf_blade import BladeMeasurementReference, FINISH_EDGE, MEASUREMENT_LABELS
from help_views.bsf_geometry_model import (
    BSFGeometryHelpSnapshot,
    fmt_axis_z,
    fmt_mm,
    format_help_info,
    short_edge_label,
    status_detail,
    status_headline,
)

_COLOR_BG = "#eef1f4"
_COLOR_FLANGE_A = "#c5ccd4"
_COLOR_FLANGE_B = "#b3bbc4"
_COLOR_FLANGE_LINE = "#2f353b"
_COLOR_TOOL = "#6d747c"
_COLOR_BLADE = "#f0b429"
_COLOR_FINISH = "#1a7f37"
_COLOR_MEAS = "#0969da"
_COLOR_Z0 = "#cf222e"
_COLOR_AXIS = "#57606a"
_COLOR_SINK = "#1a7f37"
_COLOR_CLEAR = "#8250df"
_COLOR_TEXT = "#1f2328"
_COLOR_CHAMFER = "#d8ead8"
_COLOR_OK = "#1a7f37"
_COLOR_BLOCK = "#cf222e"


class BSFGeometryHelpWindow:
    def __init__(
        self,
        master: tk.Misc,
        *,
        snapshot_provider: Callable[[], BSFGeometryHelpSnapshot],
    ) -> None:
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

        detail_frame = ttk.LabelFrame(body, text="Schwertdetail", padding=4)
        detail_frame.grid(row=0, column=1, sticky="nsew", pady=(0, 6))
        self.detail_canvas = tk.Canvas(
            detail_frame, background="#f7f8fa", highlightthickness=0, height=220
        )
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
            ("z0", "Z0", False),
            ("sec_tool", "Werkzeug", True),
            ("blade", "Schwertdicke", False),
            ("meas", "Vermessung", False),
            ("finish", "Fertigkante", False),
            ("sec_nc", "NC", True),
            ("finish_z", "Finish-Z", False),
            ("clear_z", "Freifahrt-Z", False),
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
        z0 = "Unterkante Bund" if s.z0_is_flange_bottom else "Oberkante Bund"
        self._info_vars["bund"].set(fmt_mm(s.bund_thickness))
        self._info_vars["sink"].set(fmt_mm(s.sink_depth))
        self._info_vars["clear"].set(fmt_mm(s.clearance))
        self._info_vars["z0"].set(z0)
        self._info_vars["blade"].set(fmt_mm(s.blade_thickness))
        self._info_vars["meas"].set(short_edge_label(s.measurement_label))
        self._info_vars["finish"].set(short_edge_label(s.finish_edge_label))
        self._info_vars["finish_z"].set(fmt_axis_z(s.programmed_z_sink_finish))
        self._info_vars["clear_z"].set(fmt_axis_z(s.programmed_z_clearance))

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
        self._draw_blade_detail(w, h)

    def _draw_main_cross_section(self, w: float, h: float) -> None:
        s = self.snapshot
        assert s is not None

        # Kompakte Z-Orientierung oben links – keine Achse durch das Fenster.
        self.canvas.create_text(
            12,
            14,
            text="+Z ↑ zur Spindel",
            fill=_COLOR_SINK,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
            tags=("z_compass",),
        )
        self.canvas.create_text(
            12,
            30,
            text="-Z ↓ zur Werkzeugspitze",
            fill=_COLOR_AXIS,
            anchor="w",
            font=("Segoe UI", 9),
            tags=("z_compass",),
        )
        self.canvas.create_text(
            w - 12,
            14,
            text="SCHEMATISCH – NICHT MASSSTÄBLICH",
            fill=_COLOR_AXIS,
            anchor="e",
            font=("Segoe UI", 8),
            tags=("legend",),
        )

        left_zone = 88.0
        right_zone = 210.0
        top_pad = 48.0
        bot_pad = 18.0
        usable_h = max(120.0, h - top_pad - bot_pad)
        flange_h = usable_h * 0.68  # 60–75 % der verfügbaren Schnitthöhe
        tool_above = usable_h * 0.10
        blade_h = max(22.0, usable_h * 0.08)
        clear_h = max(28.0, usable_h * 0.08)
        y_top = top_pad + tool_above
        y_bot = y_top + flange_h
        y_blade_top = y_bot
        y_blade_bot = y_blade_top + blade_h
        y_clear = y_blade_bot + clear_h * 0.55

        inner_w = max(120.0, w - left_zone - right_zone)
        cx = left_zone + inner_w * 0.48
        flange_half = min(inner_w * 0.46, w * 0.28)
        hole_half = max(14.0, flange_half * 0.18)
        left = cx - flange_half
        right = cx + flange_half
        hole_l = cx - hole_half
        hole_r = cx + hole_half
        shank_half = max(7.0, hole_half * 0.38)

        y_spindle = y_top - tool_above - 4

        # Werkzeugschaft durch die Bohrung bis ins Schwert
        self.canvas.create_rectangle(
            cx - shank_half,
            y_spindle,
            cx + shank_half,
            y_blade_bot,
            fill=_COLOR_TOOL,
            outline=_COLOR_FLANGE_LINE,
            tags=("tool",),
        )
        self.canvas.create_text(
            cx,
            y_spindle - 10,
            text="SPINDEL / Werkzeug",
            fill=_COLOR_TEXT,
            font=("Segoe UI", 8, "bold"),
            tags=("tool",),
        )
        self.canvas.create_text(
            cx + shank_half + 10,
            y_top - 16,
            text="↑ SENKEN +Z",
            fill=_COLOR_SINK,
            anchor="w",
            font=("Segoe UI", 10, "bold"),
            tags=("sink_arrow",),
        )

        # Bund links/rechts in zwei Grautönen
        self.canvas.create_rectangle(
            left, y_top, hole_l, y_bot, fill=_COLOR_FLANGE_A, outline=_COLOR_FLANGE_LINE, width=2, tags=("flange",)
        )
        self.canvas.create_rectangle(
            hole_r, y_top, right, y_bot, fill=_COLOR_FLANGE_B, outline=_COLOR_FLANGE_LINE, width=2, tags=("flange",)
        )
        self._hatch(left, y_top, hole_l, y_bot, tag="hatch")
        self._hatch(hole_r, y_top, right, y_bot, tag="hatch")
        self.canvas.create_line(hole_l, y_top, hole_l, y_bot, fill=_COLOR_AXIS, dash=(3, 2), tags=("hole",))
        self.canvas.create_line(hole_r, y_top, hole_r, y_bot, fill=_COLOR_AXIS, dash=(3, 2), tags=("hole",))
        self.canvas.create_text(
            cx,
            y_top + flange_h * 0.42,
            text="Bohrung",
            fill=_COLOR_AXIS,
            font=("Segoe UI", 8),
            tags=("hole",),
        )

        # Rueckwaertige Senkflaeche: Fasen an der Bund-Unterseite, seitlich der Bohrung
        chamfer_w = max(22.0, hole_half * 0.9)
        chamfer_h = max(18.0, flange_h * 0.12)
        self.canvas.create_polygon(
            hole_l,
            y_bot - chamfer_h,
            hole_l,
            y_bot,
            hole_l - chamfer_w,
            y_bot,
            fill=_COLOR_CHAMFER,
            outline=_COLOR_FINISH,
            width=2,
            tags=("sink_finish",),
        )
        self.canvas.create_polygon(
            hole_r,
            y_bot - chamfer_h,
            hole_r,
            y_bot,
            hole_r + chamfer_w,
            y_bot,
            fill=_COLOR_CHAMFER,
            outline=_COLOR_FINISH,
            width=2,
            tags=("sink_finish",),
        )

        # Schematisches Schwert, verbunden unter dem Bund
        blade_half = hole_half + 26
        self.canvas.create_rectangle(
            cx - blade_half,
            y_blade_top,
            cx + blade_half,
            y_blade_bot,
            fill=_COLOR_BLADE,
            outline=_COLOR_FLANGE_LINE,
            width=2,
            tags=("blade",),
        )
        self.canvas.create_text(
            cx,
            (y_blade_top + y_blade_bot) / 2,
            text="Schwert",
            fill=_COLOR_TEXT,
            font=("Segoe UI", 8, "bold"),
            tags=("blade",),
        )

        # Freifahrt kompakt, nicht 1:1
        self.canvas.create_line(
            cx,
            y_blade_bot,
            cx,
            y_clear,
            fill=_COLOR_CLEAR,
            width=2,
            arrow=tk.LAST,
            tags=("clearance",),
        )
        self.canvas.create_oval(cx - 5, y_clear - 5, cx + 5, y_clear + 5, fill=_COLOR_CLEAR, outline="", tags=("clearance",))
        self.canvas.create_text(
            cx + 12,
            y_clear,
            text=f"Freifahrt  {fmt_mm(s.clearance)}\nsichere Messerposition",
            fill=_COLOR_CLEAR,
            anchor="w",
            font=("Segoe UI", 8),
            tags=("clearance",),
        )

        # Bunddicke links
        dim_x = left - 28
        self.canvas.create_line(left, y_top, dim_x - 8, y_top, fill=_COLOR_TEXT, tags=("bund_dim",))
        self.canvas.create_line(left, y_bot, dim_x - 8, y_bot, fill=_COLOR_TEXT, tags=("bund_dim",))
        self.canvas.create_line(dim_x, y_top, dim_x, y_bot, fill=_COLOR_TEXT, arrow=tk.BOTH, tags=("bund_dim",))
        self.canvas.create_text(
            dim_x - 8,
            (y_top + y_bot) / 2,
            text=fmt_mm(s.bund_thickness).replace(" mm", "\nmm") if s.bund_thickness is not None else "—",
            fill=_COLOR_TEXT,
            anchor="e",
            font=("Segoe UI", 8, "bold"),
            tags=("bund_dim",),
        )

        # Rechte Leader: Werkstückbeschriftungen, vertikal gestaffelt
        label_x = right + 18
        self._leader(right, y_top, label_x, y_top - 2, "Oberkante Bund", _COLOR_TEXT, "label_wp")
        self._leader(right, y_bot, label_x, y_bot + 16, "Unterkante Bund", _COLOR_TEXT, "label_wp")
        self._leader(
            hole_r + chamfer_w,
            y_bot - 2,
            label_x,
            y_bot + 38,
            "Senk-Fertigfläche",
            _COLOR_FINISH,
            "sink_finish",
        )

        # Z0 links, getrennt von den rechten Labels
        z0_y = y_bot if s.z0_is_flange_bottom else y_top
        z0_caption = "Z0 · Unterkante Bund" if s.z0_is_flange_bottom else "Z0 · Oberkante Bund"
        self.canvas.create_line(
            left - 6,
            z0_y,
            right + 6,
            z0_y,
            fill=_COLOR_Z0,
            width=2,
            dash=(7, 3),
            tags=("z0",),
        )
        self.canvas.create_oval(left - 11, z0_y - 4, left - 3, z0_y + 4, fill=_COLOR_Z0, outline="", tags=("z0",))
        z0_text_y = z0_y - 14 if s.z0_is_flange_bottom else z0_y + 14
        self.canvas.create_text(
            left - 14,
            z0_text_y,
            text=z0_caption,
            fill=_COLOR_Z0,
            anchor="e",
            font=("Segoe UI", 8, "bold"),
            tags=("z0",),
        )

    def _leader(self, x0: float, y0: float, x1: float, y1: float, text: str, color: str, tag: str) -> None:
        self.canvas.create_line(x0, y0, x1, y1, fill=color, tags=(tag,))
        self.canvas.create_line(x1, y1, x1 + 12, y1, fill=color, tags=(tag,))
        self.canvas.create_text(
            x1 + 16,
            y1,
            text=text,
            fill=color,
            anchor="w",
            font=("Segoe UI", 8),
            tags=(tag,),
        )

    def _hatch(self, x1: float, y1: float, x2: float, y2: float, *, tag: str) -> None:
        if x2 <= x1 or y2 <= y1:
            return
        step = 9
        start = int(x1 - (y2 - y1))
        end = int(x2)
        for x in range(start, end, step):
            xa, ya = x, y2
            xb, yb = x + (y2 - y1), y1
            cx1, cy1, cx2, cy2 = self._clip_45(xa, ya, xb, yb, x1, y1, x2, y2)
            if cx1 is None:
                continue
            self.canvas.create_line(cx1, cy1, cx2, cy2, fill="#9aa3ad", tags=(tag,))

    @staticmethod
    def _clip_45(xa, ya, xb, yb, x1, y1, x2, y2):
        pts = []
        for t in (0.0, 1.0):
            x = xa + t * (xb - xa)
            y = ya + t * (yb - ya)
            if x1 - 0.5 <= x <= x2 + 0.5 and y1 - 0.5 <= y <= y2 + 0.5:
                pts.append((x, y))
        # Schnitt mit Rechteckkanten
        dx, dy = xb - xa, yb - ya
        if abs(dx) < 1e-9:
            return None, None, None, None
        for edge, val in (("x", x1), ("x", x2), ("y", y1), ("y", y2)):
            if edge == "x":
                t = (val - xa) / dx
                y = ya + t * dy
                if 0 <= t <= 1 and y1 - 0.5 <= y <= y2 + 0.5:
                    pts.append((val, y))
            else:
                t = (val - ya) / dy if abs(dy) > 1e-9 else -1
                x = xa + t * dx
                if 0 <= t <= 1 and x1 - 0.5 <= x <= x2 + 0.5:
                    pts.append((x, val))
        # eindeutige Endpunkte
        uniq = []
        for p in pts:
            if not any(abs(p[0] - q[0]) < 0.8 and abs(p[1] - q[1]) < 0.8 for q in uniq):
                uniq.append(p)
        if len(uniq) < 2:
            return None, None, None, None
        uniq.sort()
        return uniq[0][0], uniq[0][1], uniq[-1][0], uniq[-1][1]

    def _draw_blade_detail(self, w: float, h: float) -> None:
        s = self.snapshot
        assert s is not None
        cx = w * 0.46
        blade_w = min(w * 0.62, 220)
        blade_h = min(h * 0.38, 90)
        y_top = h * 0.34
        y_bot = y_top + blade_h
        left = cx - blade_w / 2
        right = cx + blade_w / 2
        shank = 10

        self.detail_canvas.create_rectangle(
            cx - shank, 12, cx + shank, y_top, fill=_COLOR_TOOL, outline=_COLOR_FLANGE_LINE, tags=("detail_tool",)
        )
        self.detail_canvas.create_text(cx, 14, text="Werkzeug", fill=_COLOR_TEXT, font=("Segoe UI", 8), tags=("detail_tool",))
        self.detail_canvas.create_rectangle(
            left, y_top, right, y_bot, fill=_COLOR_BLADE, outline=_COLOR_FLANGE_LINE, width=2, tags=("detail_blade",)
        )
        self.detail_canvas.create_text(
            cx, (y_top + y_bot) / 2, text="SCHWERT", fill=_COLOR_TEXT, font=("Segoe UI", 9, "bold"), tags=("detail_blade",)
        )

        # Dicke
        dim_x = right + 16
        self.detail_canvas.create_line(dim_x, y_top, dim_x, y_bot, fill=_COLOR_TEXT, arrow=tk.BOTH, tags=("detail_dim",))
        self.detail_canvas.create_text(
            dim_x + 8,
            (y_top + y_bot) / 2,
            text=fmt_mm(s.blade_thickness),
            fill=_COLOR_TEXT,
            anchor="w",
            font=("Segoe UI", 8, "bold"),
            tags=("detail_dim",),
        )

        finish_is_spindle = FINISH_EDGE is BladeMeasurementReference.SPINDLE_SIDE_EDGE
        y_finish = y_top if finish_is_spindle else y_bot
        y_other = y_bot if finish_is_spindle else y_top
        other_ref = (
            BladeMeasurementReference.TOOL_TIP_SIDE_EDGE
            if finish_is_spindle
            else BladeMeasurementReference.SPINDLE_SIDE_EDGE
        )

        self.detail_canvas.create_line(left, y_finish, right, y_finish, fill=_COLOR_FINISH, width=3, tags=("finish_edge",))
        self.detail_canvas.create_text(
            left - 6,
            y_finish - 12,
            text="FERTIGKANTE",
            fill=_COLOR_FINISH,
            anchor="e",
            font=("Segoe UI", 8, "bold"),
            tags=("finish_edge",),
        )
        self.detail_canvas.create_text(
            left,
            y_finish + (10 if finish_is_spindle else -10),
            text=MEASUREMENT_LABELS[FINISH_EDGE],
            fill=_COLOR_FINISH,
            anchor="w",
            font=("Segoe UI", 8),
            tags=("finish_edge",),
        )
        self.detail_canvas.create_text(
            left,
            y_other + (12 if y_other > y_finish else -12),
            text=MEASUREMENT_LABELS[other_ref],
            fill=_COLOR_AXIS,
            anchor="w",
            font=("Segoe UI", 8),
            tags=("detail_blade",),
        )

        meas = s.measurement_reference
        if meas is not None:
            y_meas = y_top if meas is BladeMeasurementReference.SPINDLE_SIDE_EDGE else y_bot
            self.detail_canvas.create_line(
                right,
                y_meas,
                min(w - 8, right + 28),
                y_meas,
                fill=_COLOR_MEAS,
                width=2,
                arrow=tk.FIRST,
                tags=("measurement_edge",),
            )
            meas_y = y_meas - 16 if meas is BladeMeasurementReference.SPINDLE_SIDE_EDGE else y_meas + 16
            self.detail_canvas.create_text(
                cx,
                meas_y,
                text="← WERKZEUG HIER VERMESSEN",
                fill=_COLOR_MEAS,
                font=("Segoe UI", 8, "bold"),
                tags=("measurement_edge",),
            )


def open_bsf_geometry_help_window(
    master: tk.Misc,
    snapshot_provider: Callable[[], BSFGeometryHelpSnapshot],
) -> BSFGeometryHelpWindow:
    return BSFGeometryHelpWindow(master, snapshot_provider=snapshot_provider)
