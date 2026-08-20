"""BSF-Hilfe: Geometriehilfe (Referenz-PNG), Aktuelle Werte, Prozessablauf, HEULE Original."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable, Optional

from app_paths import apply_window_icon, resource_path
from bsf_workpiece_geometry import Z0_EXAMPLES
from help_assets import (
    BSF_GEOMETRY_REFERENCE_REL,
    BSF_HELP_ATTRIBUTION,
    BSF_HELP_EXAMPLE_NOTE,
    BSF_HELP_MISSING_TEXT,
    BSF_HELP_Z0_NOTE,
    get_bsf_geometry_reference_image_path,
    help_image_scaler_mode,
)
from help_views.bsf_geometry_model import (
    BSFGeometryHelpSnapshot,
    build_bsf_geometry_help_snapshot,
    fmt_axis_z,
    format_help_info,
)
from manufacturer_assets import (
    HEULE_ATTRIBUTION_TEXT,
    HEULE_DISCLAIMER_TEXT,
    HEULE_MISSING_ASSET_TEXT,
    clear_heule_bsf_reference_image,
    get_heule_bsf_reference_image_path,
    image_scaler_mode,
    set_heule_bsf_reference_image,
)
from ui.bsf_current_values_panel import BSFCurrentValuesPanel
from ui.bsf_process_animation import (
    PROCESS_STEPS,
    BSFProcessAnimator,
    draw_process_frame,
)
from ui.bsf_reference_image import BSFReferenceImagePanel


class BSFHelpWindow:
    def __init__(self, master: tk.Misc, *, snapshot_provider: Callable[[], BSFGeometryHelpSnapshot]) -> None:
        self._provider = snapshot_provider
        self.win = tk.Toplevel(master)
        self.win.title("HEULE BSF – Senkgeometrie")
        self.win.geometry("1320x940")
        self.win.minsize(1120, 780)
        apply_window_icon(self.win)
        self.snapshot: Optional[BSFGeometryHelpSnapshot] = None
        self._display_snapshot: Optional[BSFGeometryHelpSnapshot] = None
        self._orig_zoom = 1.0
        self._image_src = None
        self._img = None
        self._animator: Optional[BSFProcessAnimator] = None
        self._learning_mode: Optional[int] = None
        self.geom_info = tk.StringVar(value="")
        self._build_ui()
        self.refresh()
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        if self._animator is not None:
            self._animator.close()
        self.win.destroy()

    def _build_ui(self) -> None:
        top = ttk.Frame(self.win, padding=(10, 8))
        top.pack(fill=tk.X)
        ttk.Label(top, text="HEULE BSF Hilfe", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        ttk.Button(top, text="Aktualisieren", command=self.refresh).pack(side=tk.RIGHT)

        nb = ttk.Notebook(self.win)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.nb = nb

        self.tab_reference = ttk.Frame(nb, padding=6)
        self.tab_values = ttk.Frame(nb, padding=6)
        self.tab_process = ttk.Frame(nb, padding=6)
        self.tab_original = ttk.Frame(nb, padding=6)
        nb.add(self.tab_reference, text="Geometriehilfe")
        nb.add(self.tab_values, text="Aktuelle Werte")
        nb.add(self.tab_process, text="Prozessablauf")
        nb.add(self.tab_original, text="HEULE Original")

        # Rueckwaertskompatibilitaet fuer Tests
        self.tab_geom = self.tab_reference

        self._build_reference_tab()
        self._build_values_tab()
        self._build_process_tab()
        self._build_original_tab()

    def _build_reference_tab(self) -> None:
        self._ref_panel = BSFReferenceImagePanel(
            self.tab_reference,
            on_missing=lambda: self._ref_panel.msg.set(BSF_HELP_MISSING_TEXT),
        )
        self._ref_panel.pack(fill=tk.BOTH, expand=True)
        foot = ttk.Frame(self.tab_reference)
        foot.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(foot, text=BSF_HELP_EXAMPLE_NOTE, wraplength=1180, justify=tk.LEFT).pack(anchor=tk.W)
        ttk.Label(foot, text=BSF_HELP_Z0_NOTE, wraplength=1180, justify=tk.LEFT, foreground="#57606a").pack(
            anchor=tk.W, pady=(6, 0)
        )
        ttk.Label(foot, text=BSF_HELP_ATTRIBUTION, wraplength=1180, foreground="#57606a").pack(anchor=tk.W, pady=(6, 0))

    def _build_values_tab(self) -> None:
        self._values_panel = BSFCurrentValuesPanel(
            self.tab_values,
            on_use_current=self._use_current_geometry,
            on_use_example=self._use_z0_example,
        )
        self._values_panel.pack(fill=tk.BOTH, expand=True)

    def _build_process_tab(self) -> None:
        top = ttk.Frame(self.tab_process)
        top.pack(fill=tk.X, pady=(0, 4))
        self.badge_spindle = tk.StringVar(value="Spindel: —")
        self.badge_pressure = tk.StringVar(value="Druck/IK: —")
        self.badge_blade = tk.StringVar(value="Messer: —")
        self.badge_pos = tk.StringVar(value="Position: —")
        self.badge_z = tk.StringVar(value="Z: —")
        for var in (self.badge_spindle, self.badge_pressure, self.badge_blade, self.badge_pos, self.badge_z):
            ttk.Label(top, textvariable=var, padding=(6, 2)).pack(side=tk.LEFT, padx=4)

        self.proc_canvas = tk.Canvas(self.tab_process, background="#eef2f6")
        self.proc_canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas = self.proc_canvas
        self.geom_canvas = self.proc_canvas

        self.step_var = tk.StringVar(value=PROCESS_STEPS[0])
        ttk.Label(self.tab_process, textvariable=self.step_var, font=("Segoe UI", 10, "bold")).pack(
            anchor=tk.W, pady=(6, 2)
        )
        ttk.Label(
            self.tab_process,
            text="Darstellung schematisch – NC-Code vor Maschineneinsatz simulieren und pruefen.",
            foreground="#57606a",
        ).pack(anchor=tk.W, pady=(0, 8))

        row = ttk.Frame(self.tab_process)
        row.pack(fill=tk.X)
        ttk.Button(row, text="|< Anfang", command=lambda: self._animator.first()).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="< Zurueck", command=lambda: self._animator.prev()).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="Play/Pause", command=lambda: self._animator.toggle_play()).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="Weiter >", command=lambda: self._animator.next()).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="Ende >|", command=lambda: self._animator.last()).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="Aktuelle Geometrie", command=self._use_current_geometry).pack(side=tk.LEFT, padx=12)
        self._animator = BSFProcessAnimator(self.proc_canvas, self.step_var, on_redraw=self._draw_process_step)

    def _build_original_tab(self) -> None:
        tools = ttk.Frame(self.tab_original)
        tools.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(tools, text="HEULE-Original auswaehlen...", command=self._choose_heule_image).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(tools, text="Zoom +", command=lambda: self._set_orig_zoom(self._orig_zoom * 1.15)).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(tools, text="Zoom -", command=lambda: self._set_orig_zoom(self._orig_zoom / 1.15)).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(tools, text="100 %", command=lambda: self._set_orig_zoom(1.0)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tools, text="An Fenster", command=self._fit_original_image).pack(side=tk.LEFT, padx=2)
        ttk.Button(tools, text="Pfad entfernen", command=self._clear_heule_image).pack(side=tk.LEFT, padx=2)
        ttk.Label(tools, text=f"Scaler: {image_scaler_mode()}", foreground="#57606a").pack(side=tk.RIGHT)

        holder = ttk.Frame(self.tab_original)
        holder.pack(fill=tk.BOTH, expand=True)
        self.orig_canvas = tk.Canvas(holder, background="#f6f8fa")
        sy = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=self.orig_canvas.yview)
        sx = ttk.Scrollbar(holder, orient=tk.HORIZONTAL, command=self.orig_canvas.xview)
        self.orig_canvas.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.orig_canvas.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.orig_canvas.bind("<Configure>", lambda _e: self._render_original_image())

        self.orig_msg = tk.StringVar(value="")
        ttk.Label(self.tab_original, textvariable=self.orig_msg, foreground="#57606a").pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(self.tab_original, text=HEULE_ATTRIBUTION_TEXT, wraplength=1100).pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(self.tab_original, text=HEULE_DISCLAIMER_TEXT, wraplength=1100, foreground="#57606a").pack(
            anchor=tk.W
        )

    def refresh(self) -> None:
        self.snapshot = self._provider()
        self._resolve_display_snapshot()
        self._load_reference_image()
        self._load_original_image()
        self._update_values_panel()
        if self._animator is not None:
            self._animator._update()

    def _load_reference_image(self) -> None:
        path = get_bsf_geometry_reference_image_path()
        self._ref_panel.load_from_path(str(path) if path is not None else None)

    def _resolve_display_snapshot(self) -> None:
        base = self.snapshot
        if base is None:
            self._display_snapshot = None
            return
        if self._learning_mode is None:
            self._display_snapshot = base
            self._values_panel.set_mode_label("Aktuelle GUI-Werte")
            return
        ex = Z0_EXAMPLES[self._learning_mode % len(Z0_EXAMPLES)]
        tool = base.tool_profile.designation if base.tool_profile is not None else ""
        self._display_snapshot = build_bsf_geometry_help_snapshot(
            entry_text=str(ex["entry_edge_z"]),
            exit_text=str(ex["exit_edge_z"]),
            target_text=str(ex["target_surface_z"]),
            raw_surface_z_text="",
            x_safety_text=str(base.x_safety_clearance if base.x_safety_clearance is not None else 2.0),
            entry_clearance_text=str(base.entry_clearance if base.entry_clearance is not None else 1.0),
            overlap_text=str(base.full_cut_overlap if base.full_cut_overlap is not None else 0.25),
            tool_designation=tool,
            safe_z_text="" if base.safe_z is None else str(base.safe_z),
            end_safe_z_text="" if base.end_safe_z is None else str(base.end_safe_z),
        )
        self._values_panel.set_mode_label(f"Lernmodus: {ex['name']}")

    def _use_current_geometry(self) -> None:
        self._learning_mode = None
        self.refresh()

    def _use_z0_example(self, index: int) -> None:
        self._learning_mode = index
        self.refresh()

    def _update_values_panel(self) -> None:
        snap = self._display_snapshot
        self._values_panel.update_snapshot(snap)
        if snap is not None:
            self.geom_info.set(format_help_info(snap))

    def _load_reference_image(self) -> None:
        path = get_bsf_geometry_reference_image_path()
        self._ref_panel.load_from_path(str(path) if path is not None else None)

    def _choose_heule_image(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.win,
            title="HEULE-Original auswaehlen",
            filetypes=[
                ("Bilder", "*.png;*.jpg;*.jpeg"),
                ("PNG", "*.png"),
                ("JPEG", "*.jpg;*.jpeg"),
                ("Alle Dateien", "*.*"),
            ],
        )
        if not path:
            return
        try:
            stored = set_heule_bsf_reference_image(Path(path), copy_to_appdata=True)
        except (OSError, ValueError) as exc:
            self.orig_msg.set(f"Bild konnte nicht geladen werden: {exc}")
            return
        self.orig_msg.set(f"Lokale Abbildung: {stored}")
        self._load_original_image()

    def _clear_heule_image(self) -> None:
        clear_heule_bsf_reference_image(delete_local_copy=False)
        self._image_src = None
        self._img = None
        self.orig_msg.set(HEULE_MISSING_ASSET_TEXT)
        self.orig_canvas.delete("all")

    def _load_original_image(self) -> None:
        path = get_heule_bsf_reference_image_path()
        if path is None:
            self._image_src = None
            self._img = None
            self.orig_msg.set(HEULE_MISSING_ASSET_TEXT)
            self.orig_canvas.delete("all")
            return
        try:
            src = tk.PhotoImage(file=str(path))
        except tk.TclError:
            self._image_src = None
            self._img = None
            self.orig_msg.set(HEULE_MISSING_ASSET_TEXT)
            self.orig_canvas.delete("all")
            return
        self._image_src = src
        self.orig_msg.set(f"Originalabbildung geladen: {path.name}")
        self._fit_original_image()

    def _set_orig_zoom(self, value: float) -> None:
        self._orig_zoom = min(4.0, max(0.25, value))
        self._render_original_image()

    def _fit_original_image(self) -> None:
        if self._image_src is None:
            return
        cw = max(1, self.orig_canvas.winfo_width())
        ch = max(1, self.orig_canvas.winfo_height())
        iw = max(1, self._image_src.width())
        ih = max(1, self._image_src.height())
        scale = min(cw / iw, ch / ih)
        self._orig_zoom = min(4.0, max(0.25, scale))
        self._render_original_image()

    def _render_original_image(self) -> None:
        self.orig_canvas.delete("all")
        if self._image_src is None:
            return
        zoom = self._orig_zoom
        if zoom >= 1.0:
            best = (1, 1, abs(1.0 - zoom))
            for n in range(1, 9):
                for m in range(1, 9):
                    factor = n / m
                    err = abs(factor - zoom)
                    if err < best[2]:
                        best = (n, m, err)
            img = self._image_src.zoom(best[0], best[0])
            if best[1] > 1:
                img = img.subsample(best[1], best[1])
        else:
            best = (1, 1, abs(1.0 - zoom))
            for n in range(1, 9):
                for m in range(1, 17):
                    factor = n / m
                    err = abs(factor - zoom)
                    if err < best[2]:
                        best = (n, m, err)
            img = self._image_src.zoom(best[0], best[0]).subsample(best[1], best[1])
        self._img = img
        self.orig_canvas.create_image(0, 0, anchor="nw", image=img)
        self.orig_canvas.configure(scrollregion=(0, 0, img.width(), img.height()))

    def _draw_process_step(self, step_index: int) -> None:
        snap = self._display_snapshot
        if snap is None:
            return
        status = draw_process_frame(self.proc_canvas, snap, step_index)
        self.badge_spindle.set(f"Spindel: {status.spindle}")
        self.badge_pressure.set(f"Druck/IK: {status.pressure_ik}")
        self.badge_blade.set(f"Messer: {status.blade}")
        self.badge_pos.set(f"Position: {status.position}")
        self.badge_z.set(f"Z: {fmt_axis_z(status.tool_z)}")


def tool_detail_canvas_layout(canvas_height: float) -> tuple[float, float]:
    y_cut = 55.0
    y_meas = canvas_height - 55.0
    return y_cut, y_meas


def bsf_geometry_reference_resource_path() -> Path:
    return resource_path(BSF_GEOMETRY_REFERENCE_REL)


__all__ = [
    "BSFHelpWindow",
    "bsf_geometry_reference_resource_path",
    "help_image_scaler_mode",
    "tool_detail_canvas_layout",
]
