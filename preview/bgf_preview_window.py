"""Tkinter Toplevel – BGF Positionsvorschau (read-only)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional, Sequence

from app_paths import apply_window_icon
from preview.bgf_preview_model import PreviewPoint, PreviewSnapshot
from preview.bgf_preview_transform import (
    ViewTransform,
    canvas_is_ready_for_fit,
    fit_transform,
    resolve_view_after_resize,
)


# Zoom-Grenzen relativ zum Auto-Fit-Massstab
_MIN_ZOOM = 0.1
_MAX_ZOOM = 20.0

_COLOR_OK = "#1a7f37"
_COLOR_WARN = "#b54708"
_COLOR_BLOCK = "#cf222e"
_COLOR_AXIS = "#57606a"
_COLOR_ORDER = "#0969da"
_COLOR_BG = "#f6f8fa"
_COLOR_DUP_RING = "#9a6700"


def _fmt3(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.3f}"


def _fmt4(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.4f}"


class BGFPreviewWindow:
    def __init__(
        self,
        master: tk.Misc,
        *,
        snapshot_provider: Callable[[], PreviewSnapshot],
    ) -> None:
        self._provider = snapshot_provider
        self.win = tk.Toplevel(master)
        self.win.title("Positionsvorschau")
        self.win.minsize(900, 650)
        self.win.geometry("980x700")
        apply_window_icon(self.win)

        self.snapshot: Optional[PreviewSnapshot] = None
        self.transform: Optional[ViewTransform] = None
        self._base_scale: float = 1.0
        self._show_order = tk.BooleanVar(value=True)
        self._selected_indices: List[int] = []  # 1-based
        self._hit_radius_px = 10.0
        self._pan_last = None
        self._panning = False
        self._item_to_index = {}  # canvas item id -> index
        self._user_view_changed = False
        self._initial_fit_done = False
        self._fit_retry_id = None

        self._build_ui()
        self.refresh()
        self.win.bind("<Configure>", self._on_configure)

    def _build_ui(self) -> None:
        top = ttk.Frame(self.win, padding=8)
        top.pack(fill=tk.X)

        self.header_tool = ttk.Label(top, text="", font=("Segoe UI", 11, "bold"))
        self.header_tool.pack(anchor=tk.W)
        self.header_prog = ttk.Label(top, text="")
        self.header_prog.pack(anchor=tk.W)
        self.header_nc = ttk.Label(top, text="", font=("Segoe UI", 10, "bold"))
        self.header_nc.pack(anchor=tk.W)
        self.header_warn = ttk.Label(top, text="", foreground="#9a6700")
        self.header_warn.pack(anchor=tk.W)

        toolbar = ttk.Frame(self.win, padding=(8, 0))
        toolbar.pack(fill=tk.X)
        ttk.Checkbutton(
            toolbar,
            text="Bearbeitungsreihenfolge anzeigen",
            variable=self._show_order,
            command=self._redraw,
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(toolbar, text="Alles anzeigen", command=self.fit_to_positions).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Aktualisieren", command=self.refresh).pack(side=tk.LEFT, padx=3)
        self.scale_label = ttk.Label(toolbar, text="")
        self.scale_label.pack(side=tk.RIGHT)

        body = ttk.Frame(self.win, padding=8)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        canvas_frame = ttk.Frame(body)
        canvas_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.canvas = tk.Canvas(canvas_frame, background=_COLOR_BG, highlightthickness=1)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        detail_frame = ttk.LabelFrame(body, text="Position", padding=8)
        detail_frame.grid(row=0, column=1, sticky="nsew")
        self.detail = tk.Text(detail_frame, width=36, height=28, wrap=tk.WORD, font=("Consolas", 10))
        self.detail.pack(fill=tk.BOTH, expand=True)
        self.detail.configure(state=tk.DISABLED)

        self.canvas.bind("<Configure>", lambda e: self._on_canvas_resize())
        self.canvas.bind("<Button-1>", self._on_left_click)
        self.canvas.bind("<B1-Motion>", self._on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_left_release)
        self.canvas.bind("<Button-2>", self._on_pan_start)
        self.canvas.bind("<B2-Motion>", self._on_pan_move)
        self.canvas.bind("<Button-3>", self._on_pan_start)
        self.canvas.bind("<B3-Motion>", self._on_pan_move)
        # Windows Mausrad
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        # Linux
        self.canvas.bind("<Button-4>", lambda e: self._zoom_at(1.1, e.x, e.y))
        self.canvas.bind("<Button-5>", lambda e: self._zoom_at(1 / 1.1, e.x, e.y))

        self._shift_pan = False
        self.win.bind("<KeyPress-Shift_L>", lambda e: setattr(self, "_shift_pan", True))
        self.win.bind("<KeyPress-Shift_R>", lambda e: setattr(self, "_shift_pan", True))
        self.win.bind("<KeyRelease-Shift_L>", lambda e: setattr(self, "_shift_pan", False))
        self.win.bind("<KeyRelease-Shift_R>", lambda e: setattr(self, "_shift_pan", False))

    def refresh(self) -> None:
        self.snapshot = self._provider()
        self._update_headers()
        self._user_view_changed = False
        self._initial_fit_done = False
        self._schedule_fit()
        if self._selected_indices:
            self._show_details(self._selected_indices)
        else:
            self._clear_details()

    def _schedule_fit(self) -> None:
        """Initiales Auto-Fit erst nach Layout; bei zu kleinem Canvas erneut versuchen."""
        try:
            self.win.after_idle(self._try_fit_when_ready)
        except tk.TclError:
            pass

    def _try_fit_when_ready(self) -> None:
        if self.snapshot is None:
            return
        w = float(self.canvas.winfo_width())
        h = float(self.canvas.winfo_height())
        if not canvas_is_ready_for_fit(w, h):
            try:
                self._fit_retry_id = self.win.after(50, self._try_fit_when_ready)
            except tk.TclError:
                pass
            return
        self.fit_to_positions()
        self._initial_fit_done = True

    def fit_all(self) -> None:
        """Alias fuer Tests und Button: dieselbe Fit-Berechnung wie Initial-Fit."""
        self.fit_to_positions()

    def fit_to_positions(self) -> None:
        """Zentrale Fit-Funktion: initialer Auto-Fit und Button „Alles anzeigen“."""
        if self.snapshot is None:
            return
        w = float(self.canvas.winfo_width())
        h = float(self.canvas.winfo_height())
        if not canvas_is_ready_for_fit(w, h):
            self._schedule_fit()
            return
        pts = [(p.x, p.y) for p in self.snapshot.points]
        self.transform = fit_transform(pts, w, h)
        self._base_scale = self.transform.scale
        self._user_view_changed = False
        self._initial_fit_done = True
        self._redraw()

    def _on_configure(self, event) -> None:
        pass

    def _on_canvas_resize(self) -> None:
        if self.snapshot is None:
            return
        w = float(self.canvas.winfo_width())
        h = float(self.canvas.winfo_height())
        pts = [(p.x, p.y) for p in self.snapshot.points]
        resolved = resolve_view_after_resize(
            pts,
            w,
            h,
            self.transform,
            user_view_changed=self._user_view_changed,
        )
        if resolved is None:
            self._schedule_fit()
            return
        if not self._user_view_changed:
            self.transform = resolved
            self._base_scale = resolved.scale
            self._initial_fit_done = True
        else:
            self.transform = resolved
        self._redraw()

    def _update_headers(self) -> None:
        s = self.snapshot
        if s is None:
            return
        if s.process_kind == "BSF":
            self.win.title("BSF Positionsvorschau")
            tool = s.bsf_tool_designation or "Bitte HEULE-Werkzeug auswaehlen"
            offset = "—" if s.bsf_measurement_face_to_edge_mm is None else f"{s.bsf_measurement_face_to_edge_mm:.3f} mm"
            extra = f"  |  {s.circle_info}" if s.circle_info else ""
            self.header_tool.config(text="HEULE BSF")
            self.header_prog.config(
                text=(
                    f"Werkzeug T{s.tool_number}    Positionen: {len(s.points)}    "
                    f"HEULE: {tool}    Vermessung: Werkzeug-Stirnfläche    "
                    f"Vermessfläche -> Schneide: {offset}{extra}"
                )
            )
        else:
            self.win.title("BGF Positionsvorschau")
            self.header_tool.config(
                text=(
                    f"CERATIZIT BGF {s.thread_size}    "
                    f"Artikel {s.article_no}    "
                    f"Werkzeugradius R+{s.tool_radius:.4f} mm"
                )
            )
            extra = f"  |  {s.circle_info}" if s.circle_info else ""
            self.header_prog.config(
                text=(
                    f"Programm: {s.program_name}    Werkzeug T{s.tool_number}    "
                    f"Positionen: {len(s.points)}    Modus: {s.mode_label}{extra}"
                )
            )
        if s.nc_allowed:
            self.header_nc.config(text="NC-STATUS: FREIGEGEBEN", foreground=_COLOR_OK)
        else:
            if s.process_kind == "BSF":
                msg = "NC-STATUS: NICHT FREIGEGEBEN"
            else:
                msg = "NC-STATUS: BLOCKIERT"
            if s.blocked_count:
                msg += f"    {s.blocked_count} problematische Positionen"
            self.header_nc.config(text=msg, foreground=_COLOR_BLOCK)
        warn = "  |  ".join(s.warnings[:4]) if s.warnings else ""
        self.header_warn.config(text=warn)

    def _relative_zoom(self) -> float:
        if self.transform is None or self._base_scale <= 0:
            return 1.0
        return self.transform.scale / self._base_scale

    def _redraw(self) -> None:
        self.canvas.delete("all")
        self._item_to_index.clear()
        if self.snapshot is None or self.transform is None:
            return

        t = self.transform
        w, h = t.canvas_w, t.canvas_h
        self.scale_label.config(text=f"Zoom {self._relative_zoom():.2f}x")

        # Achsen durch Ursprung
        ox, oy = t.world_to_canvas(0.0, 0.0)
        self.canvas.create_line(0, oy, w, oy, fill=_COLOR_AXIS, width=1)
        self.canvas.create_line(ox, 0, ox, h, fill=_COLOR_AXIS, width=1)
        self.canvas.create_oval(ox - 4, oy - 4, ox + 4, oy + 4, fill="#24292f", outline="")
        self.canvas.create_text(ox + 18, oy - 12, text="X0 / Y0", fill="#24292f", anchor="w", font=("Segoe UI", 9))
        self.canvas.create_text(w - 16, oy - 10, text="+X", fill=_COLOR_AXIS, anchor="e", font=("Segoe UI", 9, "bold"))
        self.canvas.create_text(ox + 10, 14, text="+Y", fill=_COLOR_AXIS, anchor="w", font=("Segoe UI", 9, "bold"))

        points = self.snapshot.points
        if self._show_order.get() and len(points) >= 2:
            for a, b in zip(points, points[1:]):
                x1, y1 = t.world_to_canvas(a.x, a.y)
                x2, y2 = t.world_to_canvas(b.x, b.y)
                self.canvas.create_line(x1, y1, x2, y2, fill=_COLOR_ORDER, width=1, dash=(4, 3))

        for p in points:
            self._draw_point(p)

    def _point_color(self, p: PreviewPoint) -> str:
        if not p.ok_for_nc:
            return _COLOR_BLOCK
        if p.is_duplicate_xyz or p.xy_overlap_count > 1:
            return _COLOR_WARN
        return _COLOR_OK

    def _draw_point(self, p: PreviewPoint) -> None:
        assert self.transform is not None
        cx, cy = self.transform.world_to_canvas(p.x, p.y)
        r = 6
        color = self._point_color(p)
        selected = p.index in self._selected_indices
        outline = "#000000" if selected else color
        width = 2 if selected else 1
        oval = self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r, fill=color, outline=outline, width=width, tags=("pos",)
        )
        self._item_to_index[oval] = p.index
        if p.is_duplicate_xyz or p.xy_overlap_count > 1:
            ring = self.canvas.create_oval(
                cx - r - 4,
                cy - r - 4,
                cx + r + 4,
                cy + r + 4,
                outline=_COLOR_DUP_RING,
                width=2,
                tags=("pos",),
            )
            self._item_to_index[ring] = p.index
        label = f"{p.index} {p.marker}"
        if p.xy_overlap_count > 1:
            label = f"{p.index} {p.marker}×{p.xy_overlap_count}"
        txt = self.canvas.create_text(
            cx + 10,
            cy - 10,
            text=label,
            fill="#24292f",
            anchor="w",
            font=("Segoe UI", 9, "bold"),
            tags=("pos",),
        )
        self._item_to_index[txt] = p.index

    def _find_indices_at(self, cx: float, cy: float) -> List[int]:
        if self.snapshot is None or self.transform is None:
            return []
        # Zuerst Canvas-Hit
        items = self.canvas.find_overlapping(cx - 3, cy - 3, cx + 3, cy + 3)
        found = []
        for it in items:
            idx = self._item_to_index.get(it)
            if idx and idx not in found:
                found.append(idx)
        if found:
            return found
        # Fallback Distanz in Pixel
        best: List[int] = []
        best_d = self._hit_radius_px
        for p in self.snapshot.points:
            px, py = self.transform.world_to_canvas(p.x, p.y)
            d = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
            if d <= best_d + 1e-9:
                if abs(d - best_d) < 1e-6:
                    best.append(p.index)
                elif d < best_d:
                    best_d = d
                    best = [p.index]
        # Alle exakt gleiche XY mitnehmen
        if best and self.snapshot:
            by_idx = {p.index: p for p in self.snapshot.points}
            ref = by_idx[best[0]]
            for p in self.snapshot.points:
                if abs(p.x - ref.x) < 1e-12 and abs(p.y - ref.y) < 1e-12:
                    if p.index not in best:
                        best.append(p.index)
        return best

    def _on_left_click(self, event) -> None:
        if self._shift_pan:
            self._panning = True
            self._pan_last = (event.x, event.y)
            return
        idxs = self._find_indices_at(event.x, event.y)
        if idxs:
            self._panning = False
            self._selected_indices = idxs
            self._show_details(idxs)
            self._redraw()
        else:
            self._panning = True
            self._pan_last = (event.x, event.y)

    def _on_left_drag(self, event) -> None:
        if self._panning or self._shift_pan:
            self._do_pan(event.x, event.y)

    def _on_left_release(self, event) -> None:
        self._pan_last = None
        self._panning = False

    def _on_pan_start(self, event) -> None:
        self._panning = True
        self._pan_last = (event.x, event.y)

    def _on_pan_move(self, event) -> None:
        if not self._panning:
            return
        self._do_pan(event.x, event.y)

    def _do_pan(self, x: int, y: int) -> None:
        if self.transform is None or self._pan_last is None:
            return
        dx = x - self._pan_last[0]
        dy = y - self._pan_last[1]
        self._pan_last = (x, y)
        self.transform = self.transform.pan(dx, dy)
        self._user_view_changed = True
        self._redraw()

    def _on_wheel(self, event) -> None:
        factor = 1.1 if event.delta > 0 else 1 / 1.1
        self._zoom_at(factor, event.x, event.y)

    def _zoom_at(self, factor: float, cx: float, cy: float) -> None:
        if self.transform is None:
            return
        rel = self._relative_zoom() * factor
        if rel < _MIN_ZOOM or rel > _MAX_ZOOM:
            return
        self.transform = self.transform.zoom_at(factor, cx, cy)
        self._user_view_changed = True
        self._redraw()

    def _clear_details(self) -> None:
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self.detail.insert(tk.END, "Position anklicken fuer Details.")
        self.detail.configure(state=tk.DISABLED)

    def _show_details(self, indices: Sequence[int]) -> None:
        if self.snapshot is None:
            return
        by_idx = {p.index: p for p in self.snapshot.points}
        lines: List[str] = []
        if len(indices) > 1:
            lines.append(f"{len(indices)} Positionen auf gleicher XY-Lage\n")
        for i, idx in enumerate(indices):
            p = by_idx.get(idx)
            if p is None:
                continue
            if i:
                lines.append("\n────────────\n")
            lines.append(self._format_point_detail(p))
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self.detail.insert(tk.END, "\n".join(lines))
        self.detail.configure(state=tk.DISABLED)

    def _format_point_detail(self, p: PreviewPoint) -> str:
        if self.snapshot is not None and self.snapshot.process_kind == "BSF":
            return self._format_bsf_point_detail(p)
        core = "—" if p.core_hole_depth is None else f"{p.core_hole_depth:.3f} mm"
        mode = p.depth_mode_label or "—"
        mill = "—" if p.nc_mill_start_depth is None else f"{p.nc_mill_start_depth:.3f} mm"
        drill = "—" if p.nc_drill_depth is None else f"{p.nc_drill_depth:.3f} mm"
        deepest = "—" if p.deepest_milling_depth is None else f"{p.deepest_milling_depth:.3f} mm"
        reserve = "—" if p.drill_reserve is None else f"{p.drill_reserve:.3f} mm"
        end_z = "—" if p.thread_end_z is None else f"{_fmt3(p.thread_end_z)} mm"
        nc = "NC freigegeben" if p.ok_for_nc else "NC blockiert"
        dup = "\nDuplikat XYZ: ja" if p.is_duplicate_xyz else ""
        ov = f"\nXY-Ueberlappung: {p.xy_overlap_count} Positionen" if p.xy_overlap_count > 1 else ""
        return (
            f"Position {p.index}  {p.marker}\n\n"
            f"X:\n{_fmt3(p.x)} mm\n\n"
            f"Y:\n{_fmt3(p.y)} mm\n\n"
            f"Bohrungsanfang Z:\n{_fmt3(p.surface_z)} mm\n\n"
            f"Gewindetiefe:\n{p.thread_depth:.3f} mm\n\n"
            f"Kernlochtiefe:\n{core}\n\n"
            f"Tiefenmodus:\n{mode}\n\n"
            f"Frässtarttiefe:\n{mill}\n\n"
            f"NC-Bohrtiefe:\n{drill}\n\n"
            f"Tiefste Fraestiefe:\n{deepest}\n\n"
            f"Bohrreserve:\n{reserve}\n\n"
            f"thread_end_z:\n{end_z}\n\n"
            f"Status:\n{p.status_label}\n{nc}"
            f"{dup}{ov}"
        )

    def _format_bsf_point_detail(self, p: PreviewPoint) -> str:
        s = self.snapshot
        if s is None:
            return f"Position {p.index}\n\nX: {_fmt3(p.x)} mm\nY: {_fmt3(p.y)} mm"

        def _z(v: Optional[float]) -> str:
            if v is None:
                return "—"
            return f"Z{v:+.3f}"

        def _mm(v: Optional[float]) -> str:
            if v is None:
                return "—"
            return f"{v:.3f} mm"

        ov = f"\nXY-Ueberlappung: {p.xy_overlap_count} Positionen" if p.xy_overlap_count > 1 else ""
        dup = "\nDoppelte XY-Position: ja" if p.is_duplicate_xyz else ""

        lines = [
            f"Position {p.index}",
            "",
            f"X: {_fmt3(p.x)} mm",
            f"Y: {_fmt3(p.y)} mm",
            "",
        ]

        if not s.bsf_geometry_complete:
            lines.append("WERKSTUECK / Z-GEOMETRIE")
            lines.append("BSF-Z-Geometrie unvollstaendig")
            if s.bsf_geometry_missing:
                lines.append("Fehlend: " + ", ".join(s.bsf_geometry_missing))
            lines.append("")
            lines.append("SICHERHEIT")
            lines.append(f"Sicherheits-Z: {_z(s.safe_z)}")
            lines.append(f"End-Sicherheits-Z: {_z(s.end_safe_z)}")
            lines.append(f"Mindest-Sicherheits-Z: {_z(s.bsf_required_safe_z)}")
            lines.append(f"Reserve: {_mm(s.bsf_safe_reserve_mm)}")
            lines.append(f"Status: {s.bsf_safe_status or 'NC nicht freigegeben'}")
            lines.append(dup + ov)
            return "\n".join(lines)

        raw_txt = (
            "nicht angegeben"
            if s.bsf_raw_surface_z is None
            else _z(s.bsf_raw_surface_z)
        )
        from bsf_workpiece_geometry import PROCESS_SURFACE_RAW

        if s.bsf_process_surface_source == PROCESS_SURFACE_RAW:
            process_label = f"Rohflaeche / Ist-Z {_z(s.bsf_process_surface_z)}"
        elif s.bsf_process_surface_z is not None:
            process_label = f"Austrittskante {_z(s.bsf_process_surface_z)}"
        else:
            process_label = "—"

        material = (
            "—"
            if s.bsf_material_removal is None
            else f"{s.bsf_material_removal:.3f} mm"
        )
        tool = s.bsf_tool_designation or "—"
        rpm = (
            "—"
            if s.bsf_activation_speed_rpm is None
            else f"{s.bsf_activation_speed_rpm:d} U/min"
        )

        lines.extend(
            [
                "WERKSTUECK / Z-GEOMETRIE",
                "",
                "Werkstuecknullpunkt:",
                "Z0.000",
                "",
                "Bohrungs-Eintrittskante:",
                _z(s.bsf_entry_edge_z),
                "",
                "Bohrungs-Austrittskante / Senkseite:",
                _z(s.bsf_exit_edge_z),
                "",
                "Rohflaeche / Ist-Z:",
                raw_txt,
                "",
                "Ziel-Senkflaeche:",
                _z(s.bsf_target_surface_z),
                "",
                "X/B/C Bezugsflaeche:",
                process_label,
                "",
                "Senktiefe:",
                _mm(s.bsf_sink_depth),
                "",
                "Materialabtrag:",
                material,
                "",
                "PROZESSPOSITIONEN",
                "",
                "Sicherheitsposition vor Bohrung:",
                _z(s.bsf_a_measurement_face_z),
                "",
                "Freifahrposition zum Messer-Ausklappen:",
                _z(s.bsf_x_measurement_face_z),
                "",
                "Anfahrposition vor Senkflaeche:",
                _z(s.bsf_b_measurement_face_z),
                "",
                "Schnittbeginn:",
                _z(s.bsf_c_measurement_face_z),
                "",
                "Fertigposition Senkung:",
                _z(s.bsf_d_measurement_face_z),
                "",
                "Zielposition reale Schneide:",
                _z(s.bsf_target_cutting_edge_z),
                "",
                "WERKZEUG",
                "",
                f"Werkzeug: {tool}",
                "Vermessung: Werkzeug-Stirnflaeche",
                f"Hs: {_mm(s.bsf_hs_mm)}",
                f"AL: {_mm(s.bsf_al_mm)}",
                f"Aktivierungsdrehzahl: {rpm}",
                "",
                "SICHERHEIT",
                "",
                f"Sicherheits-Z: {_z(s.safe_z)}",
                f"End-Sicherheits-Z: {_z(s.end_safe_z)}",
                f"Mindest-Sicherheits-Z: {_z(s.bsf_required_safe_z)}",
                f"Reserve: {_mm(s.bsf_safe_reserve_mm)}",
                f"Status: {s.bsf_safe_status or ('NC freigegeben' if p.ok_for_nc else 'NC nicht freigegeben')}",
            ]
        )
        lines.append(dup + ov)
        return "\n".join(lines)


def open_bgf_preview(master: tk.Misc, snapshot_provider: Callable[[], PreviewSnapshot]) -> BGFPreviewWindow:
    return BGFPreviewWindow(master, snapshot_provider=snapshot_provider)
