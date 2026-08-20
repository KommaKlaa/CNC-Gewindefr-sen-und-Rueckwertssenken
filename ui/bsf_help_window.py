"""BSF-Hilfe: HEULE Original, Eigene Geometrie, Prozessablauf."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable, Optional

from app_paths import apply_window_icon
from bsf_workpiece_geometry import Z0_EXAMPLES
from help_views.bsf_geometry_model import (
    BSFGeometryHelpSnapshot,
    build_bsf_geometry_help_snapshot,
    fmt_axis_z,
    fmt_mm,
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
from ui.bsf_geometry_canvas import draw_bsf_geometry
from ui.bsf_process_animation import (
    PROCESS_STEPS,
    BSFProcessAnimator,
    draw_process_frame,
    machine_status_for_step,
)
from ui.bsf_safe_status import fmt_axis_z as fmt_safe_z


class BSFHelpWindow:
    def __init__(self, master: tk.Misc, *, snapshot_provider: Callable[[], BSFGeometryHelpSnapshot]) -> None:
        self._provider = snapshot_provider
        self.win = tk.Toplevel(master)
        self.win.title("HEULE BSF – Senkgeometrie")
        self.win.geometry("1280x860")
        self.win.minsize(1080, 720)
        apply_window_icon(self.win)
        self.snapshot: Optional[BSFGeometryHelpSnapshot] = None
        self._display_snapshot: Optional[BSFGeometryHelpSnapshot] = None
        self._zoom = 1.0
        self._image_src = None
        self._img = None
        self._animator: Optional[BSFProcessAnimator] = None
        self._learning_mode: Optional[int] = None  # None = aktuelle GUI-Geometrie
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

        self.tab_original = ttk.Frame(nb, padding=6)
        self.tab_geom = ttk.Frame(nb, padding=6)
        self.tab_process = ttk.Frame(nb, padding=6)
        nb.add(self.tab_original, text="HEULE Original")
        nb.add(self.tab_geom, text="Eigene Geometrie")
        nb.add(self.tab_process, text="Prozessablauf")

        self._build_original_tab()
        self._build_geometry_tab()
        self._build_process_tab()

    def _build_original_tab(self) -> None:
        tools = ttk.Frame(self.tab_original)
        tools.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(tools, text="HEULE-Original auswaehlen...", command=self._choose_heule_image).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(tools, text="Zoom +", command=lambda: self._set_zoom(self._zoom * 1.15)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tools, text="Zoom -", command=lambda: self._set_zoom(self._zoom / 1.15)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tools, text="100 %", command=lambda: self._set_zoom(1.0)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tools, text="An Fenster", command=self._fit_image).pack(side=tk.LEFT, padx=2)
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

    def _build_geometry_tab(self) -> None:
        body = ttk.Panedwindow(self.tab_geom, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(body)
        right = ttk.Frame(body, width=340)
        body.add(left, weight=3)
        body.add(right, weight=1)

        self.geom_canvas = tk.Canvas(left, background="#eef2f6")
        self.canvas = self.geom_canvas  # Rueckwaertskompatibel
        self.geom_canvas.pack(fill=tk.BOTH, expand=True)
        self.geom_canvas.bind("<Configure>", lambda _e: self._draw_geometry_tab())

        learn = ttk.LabelFrame(right, text="Z0-Beispiele / Lernmodus", padding=6)
        learn.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(learn, text="Aktuelle Geometrie", command=self._use_current_geometry).pack(fill=tk.X, pady=2)
        for idx, ex in enumerate(Z0_EXAMPLES):
            ttk.Button(
                learn,
                text=ex["name"],
                command=lambda i=idx: self._use_z0_example(i),
            ).pack(fill=tk.X, pady=2)
        self._learn_mode_var = tk.StringVar(value="Aktuelle GUI-Werte")
        ttk.Label(learn, textvariable=self._learn_mode_var, foreground="#57606a", wraplength=300).pack(anchor=tk.W)

        self._info_text = tk.Text(right, width=42, height=28, wrap=tk.WORD, font=("Consolas", 9))
        self._info_text.pack(fill=tk.BOTH, expand=True)
        self._info_text.configure(state=tk.DISABLED)
        self.geom_info = tk.StringVar(value="")  # Kompatibilitaet

    def _build_process_tab(self) -> None:
        top = ttk.Frame(self.tab_process)
        top.pack(fill=tk.X, pady=(0, 4))
        self.badge_spindle = tk.StringVar(value="Spindel: —")
        self.badge_pressure = tk.StringVar(value="Druck/IK: —")
        self.badge_blade = tk.StringVar(value="Messer: —")
        self.badge_pos = tk.StringVar(value="Position: —")
        self.badge_z = tk.StringVar(value="Z: —")
        for var in (
            self.badge_spindle,
            self.badge_pressure,
            self.badge_blade,
            self.badge_pos,
            self.badge_z,
        ):
            ttk.Label(top, textvariable=var, padding=(6, 2)).pack(side=tk.LEFT, padx=4)

        self.proc_canvas = tk.Canvas(self.tab_process, background="#eef2f6")
        self.proc_canvas.pack(fill=tk.BOTH, expand=True)
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

    def refresh(self) -> None:
        self.snapshot = self._provider()
        self._resolve_display_snapshot()
        self._load_original_image()
        self._draw_geometry_tab()
        self._update_info_panel()
        if self._animator is not None:
            self._animator._update()

    def _resolve_display_snapshot(self) -> None:
        base = self.snapshot
        if base is None:
            self._display_snapshot = None
            return
        if self._learning_mode is None:
            self._display_snapshot = base
            self._learn_mode_var.set("Aktuelle GUI-Werte")
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
        self._learn_mode_var.set(f"Lernmodus: {ex['name']}")

    def _use_current_geometry(self) -> None:
        self._learning_mode = None
        self.refresh()

    def _use_z0_example(self, index: int) -> None:
        self._learning_mode = index
        self.refresh()

    def _update_info_panel(self) -> None:
        snap = self._display_snapshot
        if snap is None:
            return
        tool = snap.tool_profile
        lines = [
            "WERKSTUECK-Z0",
            f"Z0 = {fmt_axis_z(snap.z0)}",
            "",
            "WERKSTUECKFLAECHEN",
            f"Eintritt     {fmt_axis_z(snap.entry_edge_z)}",
            f"Austritt     {fmt_axis_z(snap.exit_edge_z)}",
            f"Ziel         {fmt_axis_z(snap.target_surface_z)}",
            f"Roh          {fmt_axis_z(snap.raw_surface_z)}",
            f"Senktiefe    {fmt_mm(snap.sink_depth)}",
            f"Abtrag       {fmt_mm(snap.material_removal)}",
            "",
            "HEULE WERKZEUG",
            f"{tool.designation if tool else '—'}",
            f"Hs {fmt_mm(tool.measurement_face_to_cutting_edge_mm if tool else None)}",
            f"AL {fmt_mm(tool.deployment_length_al_mm if tool else None)}",
            "",
            "PROZESSPOSITIONEN",
            f"A {fmt_axis_z(snap.a_z)}",
            f"X {fmt_axis_z(snap.x_z)}",
            f"B {fmt_axis_z(snap.b_z)}",
            f"C {fmt_axis_z(snap.c_z)}",
            f"D {fmt_axis_z(snap.d_z)}",
            "",
            "SICHERHEITSPRUEFUNG",
            snap.safe_headline,
            f"Minimum  {fmt_safe_z(snap.required_safe_z)}",
            f"Safe-Z   {fmt_safe_z(snap.safe_z)}",
            f"End-Safe {fmt_safe_z(snap.end_safe_z)}",
        ]
        if snap.notes:
            lines.extend(["", "HINWEISE"] + [f"- {n}" for n in snap.notes])
        text = "\n".join(lines)
        self.geom_info.set(format_help_info(snap))
        self._info_text.configure(state=tk.NORMAL)
        self._info_text.delete("1.0", tk.END)
        self._info_text.insert("1.0", text)
        self._info_text.configure(state=tk.DISABLED)

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
        self._fit_image()

    def _set_zoom(self, value: float) -> None:
        self._zoom = min(4.0, max(0.25, value))
        self._render_original_image()

    def _fit_image(self) -> None:
        if self._image_src is None:
            return
        cw = max(1, self.orig_canvas.winfo_width())
        ch = max(1, self.orig_canvas.winfo_height())
        iw = max(1, self._image_src.width())
        ih = max(1, self._image_src.height())
        scale = min(cw / iw, ch / ih)
        self._zoom = min(4.0, max(0.25, scale))
        self._render_original_image()

    def _render_original_image(self) -> None:
        """TK_ONLY: ganzzahlige zoom/subsample-Schritte, kein Pillow."""
        self.orig_canvas.delete("all")
        if self._image_src is None:
            return
        # Feinere Stufung ueber kombinierte zoom/subsample
        zoom = self._zoom
        if zoom >= 1.0:
            # zoom(n)/subsample(m) ~ n/m
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

    def _draw_geometry_tab(self) -> None:
        snap = self._display_snapshot
        if snap is None:
            return
        draw_bsf_geometry(self.geom_canvas, snap)

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
    # Rueckwaertskompatibel fuer vorhandene Tests.
    y_cut = 55.0
    y_meas = canvas_height - 55.0
    return y_cut, y_meas
