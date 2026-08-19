"""BSF-Hilfe mit 3 Reitern: HEULE Original, Eigene Geometrie, Prozessablauf."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from app_paths import apply_window_icon
from help_views.bsf_geometry_model import BSFGeometryHelpSnapshot, format_help_info
from manufacturer_assets import (
    HEULE_ATTRIBUTION_TEXT,
    HEULE_DISCLAIMER_TEXT,
    HEULE_MISSING_ASSET_TEXT,
    get_heule_bsf_reference_image_path,
)
from ui.bsf_geometry_canvas import draw_bsf_geometry
from ui.bsf_process_animation import BSFProcessAnimator, PROCESS_STEPS


class BSFHelpWindow:
    def __init__(self, master: tk.Misc, *, snapshot_provider: Callable[[], BSFGeometryHelpSnapshot]) -> None:
        self._provider = snapshot_provider
        self.win = tk.Toplevel(master)
        self.win.title("HEULE BSF – Senkgeometrie")
        self.win.geometry("1220x820")
        self.win.minsize(1020, 680)
        apply_window_icon(self.win)
        self.snapshot: Optional[BSFGeometryHelpSnapshot] = None
        self._zoom = 1.0
        self._image_src = None
        self._img = None
        self._animator: Optional[BSFProcessAnimator] = None
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
        ttk.Button(tools, text="Zoom +", command=lambda: self._set_zoom(self._zoom * 1.1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tools, text="Zoom -", command=lambda: self._set_zoom(self._zoom / 1.1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tools, text="100 %", command=lambda: self._set_zoom(1.0)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tools, text="An Fenster anpassen", command=self._fit_image).pack(side=tk.LEFT, padx=2)

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
        ttk.Label(self.tab_original, text=HEULE_DISCLAIMER_TEXT, wraplength=1100, foreground="#57606a").pack(anchor=tk.W)

    def _build_geometry_tab(self) -> None:
        self.geom_canvas = tk.Canvas(self.tab_geom, background="#eef2f6")
        # Rueckwaertskompatibel: einige Tests greifen auf win.canvas zu.
        self.canvas = self.geom_canvas
        self.geom_canvas.pack(fill=tk.BOTH, expand=True)
        self.geom_canvas.bind("<Configure>", lambda _e: self._draw_geometry_tab())
        self.geom_info = tk.StringVar(value="")
        ttk.Label(self.tab_geom, textvariable=self.geom_info, justify=tk.LEFT).pack(anchor=tk.W, pady=(6, 0))

    def _build_process_tab(self) -> None:
        self.proc_canvas = tk.Canvas(self.tab_process, background="#eef2f6")
        self.proc_canvas.pack(fill=tk.BOTH, expand=True)
        self.step_var = tk.StringVar(value=PROCESS_STEPS[0])
        ttk.Label(self.tab_process, textvariable=self.step_var, font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(6, 2))
        ttk.Label(
            self.tab_process,
            text="Darstellung schematisch – nicht maßstaeblich. NC-Code vor Maschineneinsatz simulieren und pruefen.",
            foreground="#57606a",
        ).pack(anchor=tk.W, pady=(0, 8))

        row = ttk.Frame(self.tab_process)
        row.pack(fill=tk.X)
        ttk.Button(row, text="|< Anfang", command=lambda: self._animator.first()).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="< Zurueck", command=lambda: self._animator.prev()).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="Play/Pause", command=lambda: self._animator.toggle_play()).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="Weiter >", command=lambda: self._animator.next()).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="Ende >|", command=lambda: self._animator.last()).pack(side=tk.LEFT, padx=2)
        self._animator = BSFProcessAnimator(self.proc_canvas, self.step_var, on_redraw=self._draw_process_step)

    def refresh(self) -> None:
        self.snapshot = self._provider()
        self._load_original_image()
        self._draw_geometry_tab()
        if self.snapshot is not None:
            self.geom_info.set(format_help_info(self.snapshot))

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
        self._zoom = min(4.0, max(0.2, value))
        self._render_original_image()

    def _fit_image(self) -> None:
        if self._image_src is None:
            return
        cw = max(1, self.orig_canvas.winfo_width())
        ch = max(1, self.orig_canvas.winfo_height())
        iw = max(1, self._image_src.width())
        ih = max(1, self._image_src.height())
        scale = min(cw / iw, ch / ih)
        self._zoom = min(4.0, max(0.2, scale))
        self._render_original_image()

    def _render_original_image(self) -> None:
        self.orig_canvas.delete("all")
        if self._image_src is None:
            return
        zoom_int = max(1, int(round(self._zoom)))
        subsample_int = max(1, int(round(1 / self._zoom))) if self._zoom < 1 else 1
        if self._zoom >= 1:
            img = self._image_src.zoom(zoom_int, zoom_int)
        else:
            img = self._image_src.subsample(subsample_int, subsample_int)
        self._img = img
        self.orig_canvas.create_image(0, 0, anchor="nw", image=img)
        self.orig_canvas.configure(scrollregion=(0, 0, img.width(), img.height()))

    def _draw_geometry_tab(self) -> None:
        if self.snapshot is None:
            return
        draw_bsf_geometry(self.geom_canvas, self.snapshot)

    def _draw_process_step(self, step_index: int) -> None:
        c = self.proc_canvas
        c.delete("all")
        w = max(240, int(c.winfo_width()))
        h = max(160, int(c.winfo_height()))
        y = h // 2
        x_a = int(w * 0.82)
        x_x = int(w * 0.34)
        x_d = int(w * 0.62)
        c.create_rectangle(int(w * 0.28), y - 30, int(w * 0.72), y + 30, fill="#d0d7de", outline="#57606a")
        c.create_rectangle(int(w * 0.45), y - 20, int(w * 0.55), y + 20, fill="#f6f8fa", outline="#57606a")
        c.create_text(x_a, y - 42, text="A")
        c.create_text(x_x, y - 42, text="X")
        c.create_text(x_d, y + 42, text="D")
        # Werkzeug rechts
        x_tool = x_a
        if step_index in (1, 2, 3):
            x_tool = x_x
        elif step_index in (4, 5):
            x_tool = x_d
        elif step_index in (6, 7):
            x_tool = x_x
        c.create_polygon(
            x_tool + 26, y - 10, x_tool, y, x_tool + 26, y + 10,
            fill="#57606a", outline="#1f2328",
        )
        c.create_text(14, 14, anchor="w", text="-Z (nach links)  /  +Z (nach rechts)")


def tool_detail_canvas_layout(canvas_height: float) -> tuple[float, float]:
    # Rueckwaertskompatibel fuer vorhandene Tests.
    y_cut = 55.0
    y_meas = canvas_height - 55.0
    return y_cut, y_meas

