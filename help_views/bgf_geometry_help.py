"""CERATIZIT-BGF-Gewindegeometrie-Hilfe – visuelle Darstellung (read-only)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

from app_paths import apply_window_icon
from ui.scrollable import ScrollableFrame
from help_views.bgf_geometry_model import (
    BGFGeometryHelpSnapshot,
    BGFHelpSource,
    fmt_axis_z,
    fmt_mm,
    fmt_radius,
    fmt_xy,
    format_help_info,
    snapshot_from_source,
    status_detail,
    status_headline,
)

_COLOR_BG = "#eef1f4"
_COLOR_WP_A = "#c5ccd4"
_COLOR_WP_B = "#b3bbc4"
_COLOR_WP_LINE = "#2f353b"
_COLOR_HOLE = "#dfe3e8"
_COLOR_THREAD = "#c5d4c8"
_COLOR_AXIS = "#57606a"
_COLOR_TEXT = "#1f2328"
_COLOR_SURFACE = "#1f2328"
_COLOR_APPROACH = "#8250df"
_COLOR_THREAD_DIM = "#1a7f37"
_COLOR_MILL = "#0969da"
_COLOR_DEEP = "#0d7377"
_COLOR_DRILL = "#cf222e"
_COLOR_CORE = "#9a6700"
_COLOR_PREDRILL = "#bc4c00"
_COLOR_TEMPLATE = "#8c959f"
_COLOR_OK = "#1a7f37"
_COLOR_BLOCK = "#cf222e"


class BGFGeometryHelpWindow:
    def __init__(
        self,
        master: tk.Misc,
        *,
        source_provider: Callable[[], BGFHelpSource],
    ) -> None:
        self._provider = source_provider
        self.win = tk.Toplevel(master)
        self.win.title("CERATIZIT BGF – Gewinde- und Tiefengeometrie")
        self.win.minsize(1000, 650)
        self.win.geometry("1100x720")
        apply_window_icon(self.win)

        self._source: Optional[BGFHelpSource] = None
        self._index: Optional[int] = None
        self.snapshot: Optional[BGFGeometryHelpSnapshot] = None
        self._info_vars: Dict[str, tk.StringVar] = {}
        self._build_ui()
        self.refresh()
        self.canvas.bind("<Configure>", lambda _e: self._redraw_main())
        self.detail_canvas.bind("<Configure>", lambda _e: self._redraw_detail())

    def _build_ui(self) -> None:
        header = ttk.Frame(self.win, padding=(10, 6, 10, 2))
        header.pack(fill=tk.X)
        ttk.Label(
            header,
            text="CERATIZIT BGF – Gewindegeometrie   ·   READ ONLY",
            font=("Segoe UI", 11, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Button(header, text="Aktualisieren", command=self.refresh).pack(side=tk.RIGHT)

        self.tool_line = ttk.Label(self.win, text="", font=("Segoe UI", 9))
        self.tool_line.pack(anchor=tk.W, padx=10)
        self.approved_line = ttk.Label(self.win, text="", foreground=_COLOR_AXIS)
        self.approved_line.pack(anchor=tk.W, padx=10, pady=(0, 2))

        nav = ttk.Frame(self.win, padding=(10, 0, 10, 2))
        nav.pack(fill=tk.X)
        self.btn_prev = ttk.Button(nav, text="< Vorherige", command=lambda: self._nav(-1), width=14)
        self.btn_prev.pack(side=tk.LEFT)
        self.nav_label = ttk.Label(nav, text="", font=("Segoe UI", 9, "bold"))
        self.nav_label.pack(side=tk.LEFT, padx=16)
        self.btn_next = ttk.Button(nav, text="Nächste >", command=lambda: self._nav(1), width=14)
        self.btn_next.pack(side=tk.LEFT)
        self.xy_label = ttk.Label(nav, text="", foreground=_COLOR_AXIS)
        self.xy_label.pack(side=tk.LEFT, padx=16)

        status = ttk.Frame(self.win, padding=(10, 0, 10, 4))
        status.pack(fill=tk.X)
        self.status_head = ttk.Label(status, text="", font=("Segoe UI", 10, "bold"))
        self.status_head.pack(anchor=tk.W)
        self.status_sub = ttk.Label(status, text="", foreground=_COLOR_AXIS)
        self.status_sub.pack(anchor=tk.W)

        body = ttk.Frame(self.win, padding=(8, 0, 8, 8))
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=7)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=4)
        body.rowconfigure(1, weight=6)

        self.canvas = tk.Canvas(body, background=_COLOR_BG, highlightthickness=1, highlightbackground="#c8cdd2")
        self.canvas.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))

        detail_frame = ttk.LabelFrame(body, text="TIEFENDETAIL", padding=4)
        detail_frame.grid(row=0, column=1, sticky="nsew", pady=(0, 6))
        self.detail_canvas = tk.Canvas(
            detail_frame, background="#f7f8fa", highlightthickness=0, height=220
        )
        self.detail_canvas.pack(fill=tk.BOTH, expand=True)

        info_frame = ttk.LabelFrame(body, text="Aktuelle Geometrie", padding=4)
        info_frame.grid(row=1, column=1, sticky="nsew")
        info_scroll = ScrollableFrame(info_frame, height=180)
        info_scroll.pack(fill=tk.BOTH, expand=True)
        self._build_info_panel(info_scroll.body)

    def _build_info_panel(self, parent: ttk.Frame) -> None:
        rows = [
            ("sec_tool", "Werkzeug", True),
            ("thread", "Gewinde", False),
            ("article", "Artikel", False),
            ("radius", "Radius", False),
            ("sec_wp", "Werkstück", True),
            ("surface", "Bohrungsanfang Z", False),
            ("tdepth", "Gewindetiefe", False),
            ("tend", "Gewindeende", False),
            ("core", "Kernlochtiefe Soll", False),
            ("sec_safe", "Sicherheit", True),
            ("clear", "Sicherheitsabstand", False),
            ("approach", "Anfahr-Z", False),
            ("sec_nc", "NC", True),
            ("mill_d", "Frässtarttiefe", False),
            ("mill_z", "Frässtart-Z", False),
            ("deep_z", "Tiefste Fräsposition", False),
            ("drill_d", "NC-Bohrtiefe", False),
            ("drill_z", "NC-Bohr-Z", False),
            ("reserve", "Bohrreserve", False),
        ]
        for r, (key, caption, section) in enumerate(rows):
            if section:
                ttk.Label(parent, text=caption, font=("Segoe UI", 9, "bold")).grid(
                    row=r, column=0, columnspan=2, sticky=tk.W, pady=(6 if r else 0, 1)
                )
                continue
            ttk.Label(parent, text=caption, foreground=_COLOR_AXIS).grid(
                row=r, column=0, sticky=tk.W, padx=(8, 12), pady=0
            )
            var = tk.StringVar(value="—")
            self._info_vars[key] = var
            ttk.Label(parent, textvariable=var).grid(row=r, column=1, sticky=tk.W, pady=0)
        parent.columnconfigure(1, weight=1)

    def refresh(self) -> None:
        source = self._provider()
        self._source = source
        if self._index is None:
            self._index = source.initial_index
        if not source.positions:
            self._index = 0
        else:
            self._index = max(0, min(self._index, len(source.positions) - 1))
        self._apply_snapshot()

    def _nav(self, delta: int) -> None:
        if self._source is None or len(self._source.positions) <= 1:
            return
        n = len(self._source.positions)
        self._index = max(0, min((self._index or 0) + delta, n - 1))
        self._apply_snapshot()

    def _apply_snapshot(self) -> None:
        if self._source is None:
            return
        self.snapshot = snapshot_from_source(self._source, self._index or 0)
        self._update_header()
        self._update_status()
        self._update_info()
        self._redraw_main()
        self._redraw_detail()

    def _update_header(self) -> None:
        s = self.snapshot
        if s is None:
            return
        self.tool_line.config(
            text=(
                f"CERATIZIT BGF {s.tool_size}    Artikel {s.article_no}    "
                f"Werkzeugradius {fmt_radius(s.radius)}    Steigung {fmt_mm(s.pitch)}"
            )
        )
        self.approved_line.config(
            text=f"Freigegebene max. Gewindetiefe: {fmt_mm(s.approved_max_thread_depth)}"
        )
        can_nav = s.mode == "Koordinatenliste" and s.position_count > 1
        self.btn_prev.config(state=tk.NORMAL if can_nav else tk.DISABLED)
        self.btn_next.config(state=tk.NORMAL if can_nav else tk.DISABLED)
        if s.empty_list:
            self.nav_label.config(text="Keine Position vorhanden")
            self.xy_label.config(text="")
        elif s.mode == "Koordinatenliste":
            self.nav_label.config(text=f"Position {s.position_index} / {s.position_count}")
            self.xy_label.config(text=f"X {fmt_xy(s.x)}    Y {fmt_xy(s.y)}")
        elif s.mode == "Teilkreis":
            dia = f"{s.circle_diameter:g}" if s.circle_diameter is not None else "—"
            npos = str(s.circle_count) if s.circle_count is not None else "—"
            self.nav_label.config(text=f"Positionierung: Teilkreis Ø{dia} / {npos} Positionen")
            self.xy_label.config(text="")
        else:
            self.nav_label.config(text="Einzelposition")
            xy = ""
            if s.x is not None or s.y is not None:
                xy = f"X {fmt_xy(s.x)}    Y {fmt_xy(s.y)}"
            self.xy_label.config(text=xy)

    def _update_status(self) -> None:
        s = self.snapshot
        if s is None:
            return
        blocked = s.nc_blocked and not s.empty_list
        self.status_head.config(
            text=status_headline(s),
            foreground=_COLOR_BLOCK if blocked or s.empty_list else _COLOR_OK,
        )
        self.status_sub.config(text=status_detail(s))

    def _update_info(self) -> None:
        s = self.snapshot
        if s is None:
            return
        self._info_vars["thread"].set(s.tool_size)
        self._info_vars["article"].set(s.article_no)
        self._info_vars["radius"].set(fmt_radius(s.radius))
        self._info_vars["surface"].set(fmt_axis_z(s.surface_z))
        self._info_vars["tdepth"].set(fmt_mm(s.thread_depth))
        self._info_vars["tend"].set(fmt_axis_z(s.thread_end_z))
        self._info_vars["core"].set(fmt_mm(s.core_hole_depth) if s.core_hole_depth is not None else "—")
        self._info_vars["clear"].set(fmt_mm(s.approach_clearance))
        self._info_vars["approach"].set(fmt_axis_z(s.approach_z))
        self._info_vars["mill_d"].set(fmt_mm(s.mill_start_depth))
        self._info_vars["mill_z"].set(fmt_axis_z(s.mill_start_z))
        self._info_vars["deep_z"].set(fmt_axis_z(s.deepest_milling_z))
        self._info_vars["drill_d"].set(fmt_mm(s.drill_depth))
        self._info_vars["drill_z"].set(fmt_axis_z(s.drill_z))
        self._info_vars["reserve"].set(fmt_mm(s.drill_reserve))

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
        self._draw_depth_detail(w, h)

    def _draw_main_cross_section(self, w: float, h: float) -> None:
        s = self.snapshot
        assert s is not None

        self.canvas.create_text(
            12,
            14,
            text="+Z ↑ aus dem Werkstück",
            fill=_COLOR_THREAD_DIM,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
            tags=("z_compass",),
        )
        self.canvas.create_text(
            12,
            30,
            text="-Z ↓ ins Werkstück",
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
        if s.show_template_overlay:
            self.canvas.create_text(
                w - 12,
                30,
                text="gestrichelt = Hersteller-Template    durchgezogen = aktuelle NC-Geometrie",
                fill=_COLOR_TEMPLATE,
                anchor="e",
                font=("Segoe UI", 8),
                tags=("legend", "template_overlay"),
            )

        if s.empty_list:
            self.canvas.create_text(
                w / 2,
                h / 2,
                text="Keine Position vorhanden",
                fill=_COLOR_AXIS,
                font=("Segoe UI", 12, "bold"),
                tags=("empty",),
            )
            return

        left_zone = 118.0
        right_zone = 240.0
        top_pad = 52.0
        bot_pad = 22.0
        usable_h = max(160.0, h - top_pad - bot_pad)
        inner_w = max(140.0, w - left_zone - right_zone)
        cx = left_zone + inner_w * 0.48
        wp_half = min(inner_w * 0.46, w * 0.28)
        hole_half = max(16.0, wp_half * 0.22)
        left = cx - wp_half
        right = cx + wp_half
        hole_l = cx - hole_half
        hole_r = cx + hole_half

        levels = self._collect_levels(s)
        y_top = top_pad
        y_bot = top_pad + usable_h
        ymap = _schematic_ymap(levels, y_top, y_bot)

        y_surface = ymap.get("surface", y_top + usable_h * 0.18)
        lowest_keys = [k for k in ("core", "tpl_drill", "drill", "deepest", "thread_end") if k in ymap]
        y_lowest = max((ymap[k] for k in lowest_keys), default=y_bot - 8)
        y_wp_bot = min(y_bot - 4, max(y_lowest + 18, y_surface + usable_h * 0.55))

        # Werkstück links/rechts
        self.canvas.create_rectangle(
            left, y_surface, hole_l, y_wp_bot, fill=_COLOR_WP_A, outline=_COLOR_WP_LINE, width=2, tags=("workpiece",)
        )
        self.canvas.create_rectangle(
            hole_r, y_surface, right, y_wp_bot, fill=_COLOR_WP_B, outline=_COLOR_WP_LINE, width=2, tags=("workpiece",)
        )
        self._hatch(left, y_surface, hole_l, y_wp_bot, tag="hatch")
        self._hatch(hole_r, y_surface, right, y_wp_bot, tag="hatch")

        # Bohrung
        self.canvas.create_rectangle(
            hole_l, y_surface, hole_r, y_wp_bot, fill=_COLOR_HOLE, outline="", tags=("hole",)
        )
        self.canvas.create_line(hole_l, y_surface, hole_l, y_wp_bot, fill=_COLOR_AXIS, dash=(3, 2), tags=("hole",))
        self.canvas.create_line(hole_r, y_surface, hole_r, y_wp_bot, fill=_COLOR_AXIS, dash=(3, 2), tags=("hole",))

        y_thread_end = ymap.get("thread_end", y_surface + (y_wp_bot - y_surface) * 0.45)
        thread_inset = max(4.0, hole_half * 0.22)
        self.canvas.create_rectangle(
            hole_l + thread_inset,
            y_surface,
            hole_r - thread_inset,
            y_thread_end,
            fill=_COLOR_THREAD,
            outline=_COLOR_THREAD_DIM,
            tags=("thread",),
        )
        self.canvas.create_line(
            hole_l + thread_inset,
            y_thread_end,
            hole_r - thread_inset,
            y_thread_end,
            fill=_COLOR_THREAD_DIM,
            width=2,
            tags=("thread_end",),
        )
        self.canvas.create_text(
            cx,
            y_surface + max(14.0, (y_thread_end - y_surface) * 0.35),
            text="Gewinde",
            fill=_COLOR_AXIS,
            font=("Segoe UI", 8),
            tags=("thread",),
        )
        self.canvas.create_text(
            cx,
            (y_thread_end + y_wp_bot) / 2,
            text="Bohrung",
            fill=_COLOR_AXIS,
            font=("Segoe UI", 8),
            tags=("hole",),
        )

        # Oberfläche
        self.canvas.create_line(
            left - 10, y_surface, right + 10, y_surface, fill=_COLOR_SURFACE, width=3, tags=("surface",)
        )

        # Anfahr-Z
        if "approach" in ymap:
            y_ap = ymap["approach"]
            self.canvas.create_line(
                hole_l - 8, y_ap, hole_r + 8, y_ap, fill=_COLOR_APPROACH, width=2, tags=("approach",)
            )
            dim_x = left - 36
            self.canvas.create_line(dim_x, y_ap, dim_x, y_surface, fill=_COLOR_APPROACH, arrow=tk.BOTH, tags=("clearance_dim",))
            self.canvas.create_text(
                dim_x - 8,
                (y_ap + y_surface) / 2,
                text=fmt_mm(s.approach_clearance).replace(" mm", "\nmm"),
                fill=_COLOR_APPROACH,
                anchor="e",
                font=("Segoe UI", 8, "bold"),
                tags=("clearance_dim",),
            )

        # Gewindetiefe links
        dim_td = left - 64
        self.canvas.create_line(left, y_surface, dim_td - 6, y_surface, fill=_COLOR_THREAD_DIM, tags=("thread_dim",))
        self.canvas.create_line(left, y_thread_end, dim_td - 6, y_thread_end, fill=_COLOR_THREAD_DIM, tags=("thread_dim",))
        self.canvas.create_line(
            dim_td, y_surface, dim_td, y_thread_end, fill=_COLOR_THREAD_DIM, arrow=tk.BOTH, tags=("thread_dim",)
        )
        self.canvas.create_text(
            dim_td - 8,
            (y_surface + y_thread_end) / 2,
            text=fmt_mm(s.thread_depth),
            fill=_COLOR_THREAD_DIM,
            anchor="e",
            font=("Segoe UI", 8, "bold"),
            tags=("thread_dim",),
        )
        self.canvas.create_text(
            dim_td - 8,
            y_surface + 12,
            text="Gewindetiefe",
            fill=_COLOR_THREAD_DIM,
            anchor="e",
            font=("Segoe UI", 8),
            tags=("thread_dim",),
        )

        # Template-Overlay (gestrichelt, ohne Extra-Textwolke)
        if s.show_template_overlay:
            for key in ("tpl_mill", "tpl_drill"):
                if key not in ymap:
                    continue
                y = ymap[key]
                self.canvas.create_line(
                    hole_l - 6,
                    y,
                    hole_r + 6,
                    y,
                    fill=_COLOR_TEMPLATE,
                    width=2,
                    dash=(6, 4),
                    tags=("template_overlay",),
                )

        # Frässtart / tiefste Fräsposition / NC-Bohrposition
        if "mill" in ymap:
            y = ymap["mill"]
            self.canvas.create_line(cx, y_thread_end, cx, y, fill=_COLOR_MILL, width=2, tags=("mill_start",))
            self.canvas.create_oval(cx - 4, y - 4, cx + 4, y + 4, fill=_COLOR_MILL, outline="", tags=("mill_start",))
        if "deepest" in ymap:
            y = ymap["deepest"]
            y_from = ymap.get("mill", y_thread_end)
            self.canvas.create_line(cx, y_from, cx, y, fill=_COLOR_DEEP, width=2, tags=("deepest",))
            self.canvas.create_rectangle(cx - 5, y - 3, cx + 5, y + 3, fill=_COLOR_DEEP, outline="", tags=("deepest",))
        if "drill" in ymap:
            y = ymap["drill"]
            y_from = ymap.get("deepest", ymap.get("mill", y_thread_end))
            self.canvas.create_line(cx, y_from, cx, y, fill=_COLOR_DRILL, width=2, tags=("drill",))
            self.canvas.create_oval(cx - 6, y - 6, cx + 6, y + 6, fill=_COLOR_DRILL, outline="", tags=("drill",))
            if "deepest" in ymap and s.drill_reserve is not None:
                y_d = ymap["deepest"]
                rx = hole_l - 14
                self.canvas.create_line(rx, y_d, rx, y, fill=_COLOR_DRILL, arrow=tk.BOTH, tags=("reserve_dim",))
                self.canvas.create_text(
                    rx - 4,
                    (y_d + y) / 2,
                    text=fmt_mm(s.drill_reserve).replace(" mm", "\nmm"),
                    fill=_COLOR_DRILL,
                    anchor="e",
                    font=("Segoe UI", 8),
                    tags=("reserve_dim",),
                )

        if "core" in ymap:
            y = ymap["core"]
            self.canvas.create_line(
                left + 8, y, right - 8, y, fill=_COLOR_CORE, width=2, dash=(10, 4), tags=("core_hole",)
            )

        if "predrill" in ymap:
            y = ymap["predrill"]
            self.canvas.create_line(
                hole_l, y, hole_r, y, fill=_COLOR_PREDRILL, width=2, tags=("predrill",)
            )

        # Rechte Leader, gestaffelt
        leaders: List[Tuple[float, str, str, str]] = []
        if "approach" in ymap:
            leaders.append((ymap["approach"], f"Anfahr-Z  {fmt_axis_z(s.approach_z)}", _COLOR_APPROACH, "approach"))
        leaders.append((y_surface, f"Bohrungsanfang Z = {fmt_axis_z(s.surface_z)}", _COLOR_SURFACE, "surface"))
        if "predrill" in ymap:
            leaders.append(
                (ymap["predrill"], f"Vorbohr-/Anbohrtiefe  {fmt_mm(s.predrill_depth)}", _COLOR_PREDRILL, "predrill")
            )
        if "mill" in ymap:
            leaders.append((ymap["mill"], f"Frässtart-Z  {fmt_axis_z(s.mill_start_z)}", _COLOR_MILL, "mill_start"))
        leaders.append((y_thread_end, f"Gewindeende  {fmt_axis_z(s.thread_end_z)}", _COLOR_THREAD_DIM, "thread_end"))
        if "deepest" in ymap:
            leaders.append(
                (ymap["deepest"], f"tiefste Fräsposition  {fmt_axis_z(s.deepest_milling_z)}", _COLOR_DEEP, "deepest")
            )
        if "drill" in ymap:
            leaders.append(
                (ymap["drill"], f"NC-Bohrposition  {fmt_axis_z(s.drill_z)}", _COLOR_DRILL, "drill")
            )
        if "core" in ymap:
            leaders.append(
                (ymap["core"], f"Kernlochtiefe Soll  {fmt_mm(s.core_hole_depth)}", _COLOR_CORE, "core_hole")
            )

        label_x = right + 20
        placed = _stagger_y([item[0] for item in leaders], 18.0, y_top + 8, y_bot - 8)
        for (y_geom, text, color, tag), y_text in zip(leaders, placed):
            self._leader(right, y_geom, label_x, y_text, text, color, tag)

    def _collect_levels(self, s: BGFGeometryHelpSnapshot) -> List[Tuple[str, float]]:
        levels: List[Tuple[str, float]] = []
        if s.approach_z is not None:
            levels.append(("approach", s.approach_z))
        if s.surface_z is not None:
            levels.append(("surface", s.surface_z))
        if s.predrill_z is not None:
            levels.append(("predrill", s.predrill_z))
        if s.mill_start_z is not None:
            levels.append(("mill", s.mill_start_z))
        if s.thread_end_z is not None:
            levels.append(("thread_end", s.thread_end_z))
        if s.deepest_milling_z is not None:
            levels.append(("deepest", s.deepest_milling_z))
        if s.drill_z is not None:
            levels.append(("drill", s.drill_z))
        if s.core_hole_z is not None:
            levels.append(("core", s.core_hole_z))
        if s.show_template_overlay:
            if s.template_mill_start_z is not None:
                levels.append(("tpl_mill", s.template_mill_start_z))
            if s.template_drill_z is not None:
                levels.append(("tpl_drill", s.template_drill_z))
        return levels

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
        dx, dy = xb - xa, yb - ya
        if abs(dx) < 1e-9:
            return None, None, None, None
        for t in (0.0, 1.0):
            x = xa + t * dx
            y = ya + t * dy
            if x1 - 0.5 <= x <= x2 + 0.5 and y1 - 0.5 <= y <= y2 + 0.5:
                pts.append((x, y))
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
        uniq = []
        for p in pts:
            if not any(abs(p[0] - q[0]) < 0.8 and abs(p[1] - q[1]) < 0.8 for q in uniq):
                uniq.append(p)
        if len(uniq) < 2:
            return None, None, None, None
        uniq.sort()
        return uniq[0][0], uniq[0][1], uniq[-1][0], uniq[-1][1]

    def _draw_depth_detail(self, w: float, h: float) -> None:
        s = self.snapshot
        assert s is not None
        x = 12
        y = 16
        self.detail_canvas.create_text(
            x,
            y,
            text="HERSTELLER-TEMPLATE",
            fill=_COLOR_TEXT,
            anchor="w",
            font=("Segoe UI", 8, "bold"),
            tags=("detail_template",),
        )
        self.detail_canvas.create_text(
            x,
            y + 18,
            text=f"Frässtart:       {fmt_mm(s.template_mill_start_depth)}",
            fill=_COLOR_AXIS,
            anchor="w",
            font=("Segoe UI", 8),
            tags=("detail_template",),
        )
        self.detail_canvas.create_text(
            x,
            y + 34,
            text=f"Bohrposition:    {fmt_mm(s.template_drill_depth)}",
            fill=_COLOR_AXIS,
            anchor="w",
            font=("Segoe UI", 8),
            tags=("detail_template",),
        )
        self.detail_canvas.create_text(
            x,
            y + 58,
            text="AKTUELL",
            fill=_COLOR_TEXT,
            anchor="w",
            font=("Segoe UI", 8, "bold"),
            tags=("detail_current",),
        )
        self.detail_canvas.create_text(
            x,
            y + 76,
            text=f"Frässtart:       {fmt_mm(s.mill_start_depth)}",
            fill=_COLOR_MILL,
            anchor="w",
            font=("Segoe UI", 8),
            tags=("detail_current",),
        )
        self.detail_canvas.create_text(
            x,
            y + 92,
            text=f"Bohrposition:    {fmt_mm(s.drill_depth)}",
            fill=_COLOR_DRILL,
            anchor="w",
            font=("Segoe UI", 8),
            tags=("detail_current",),
        )
        shift_txt = fmt_mm(s.depth_delta) if s.depth_delta is not None else "—"
        self.detail_canvas.create_text(
            x,
            y + 114,
            text=f"Verschiebung: {shift_txt}",
            fill=_COLOR_APPROACH,
            anchor="w",
            font=("Segoe UI", 8, "bold"),
            tags=("detail_shift",),
        )

        path_x = w * 0.58
        path_y = 18
        self.detail_canvas.create_text(
            path_x,
            path_y,
            text="Frässtart",
            fill=_COLOR_MILL,
            anchor="w",
            font=("Segoe UI", 8),
            tags=("incremental_path",),
        )
        self.detail_canvas.create_text(
            path_x,
            path_y + 16,
            text="↓",
            fill=_COLOR_AXIS,
            anchor="w",
            tags=("incremental_path",),
        )
        self.detail_canvas.create_text(
            path_x,
            path_y + 32,
            text="180° Einfahren",
            fill=_COLOR_AXIS,
            anchor="w",
            font=("Segoe UI", 8),
            tags=("incremental_path",),
        )
        self.detail_canvas.create_text(
            path_x,
            path_y + 48,
            text="↓",
            fill=_COLOR_AXIS,
            anchor="w",
            tags=("incremental_path",),
        )
        self.detail_canvas.create_text(
            path_x,
            path_y + 64,
            text="360° Gewindegang",
            fill=_COLOR_AXIS,
            anchor="w",
            font=("Segoe UI", 8),
            tags=("incremental_path",),
        )
        self.detail_canvas.create_text(
            path_x,
            path_y + 80,
            text="↓",
            fill=_COLOR_AXIS,
            anchor="w",
            tags=("incremental_path",),
        )
        self.detail_canvas.create_text(
            path_x,
            path_y + 96,
            text="180° Ausfahren",
            fill=_COLOR_AXIS,
            anchor="w",
            font=("Segoe UI", 8),
            tags=("incremental_path",),
        )
        self.detail_canvas.create_text(
            w / 2,
            h - 16,
            text="Inkrementelle CERATIZIT-Bahn unverändert",
            fill=_COLOR_THREAD_DIM,
            font=("Segoe UI", 8, "bold"),
            tags=("incremental_path",),
        )


def _schematic_ymap(levels: List[Tuple[str, float]], y_top: float, y_bot: float) -> Dict[str, float]:
    """Höheres Maschinen-Z liegt weiter oben. Abstände schematisch, nicht 1:1."""
    if not levels:
        return {}
    # identische Z teilen sich eine Zeile
    unique_z: List[float] = []
    for _, z in levels:
        if not any(abs(z - u) < 1e-6 for u in unique_z):
            unique_z.append(z)
    unique_z.sort(reverse=True)
    if len(unique_z) == 1:
        y_of = {unique_z[0]: (y_top + y_bot) / 2}
    else:
        span = y_bot - y_top
        y_of = {z: y_top + i * span / (len(unique_z) - 1) for i, z in enumerate(unique_z)}
    out: Dict[str, float] = {}
    for key, z in levels:
        for u, y in y_of.items():
            if abs(z - u) < 1e-6:
                out[key] = y
                break
    return out


def _stagger_y(values: List[float], gap: float, y_min: float, y_max: float) -> List[float]:
    if not values:
        return []
    order = sorted(range(len(values)), key=lambda i: values[i])
    ys = list(values)
    for k in range(1, len(order)):
        i = order[k]
        prev = order[k - 1]
        if ys[i] < ys[prev] + gap:
            ys[i] = ys[prev] + gap
    overflow = ys[order[-1]] - y_max if order else 0.0
    if overflow > 0:
        for i in order:
            ys[i] -= overflow
    underflow = y_min - ys[order[0]]
    if underflow > 0:
        for i in order:
            ys[i] += underflow
    return ys


def open_bgf_geometry_help_window(
    master: tk.Misc,
    source_provider: Callable[[], BGFHelpSource],
) -> BGFGeometryHelpWindow:
    return BGFGeometryHelpWindow(master, source_provider=source_provider)
