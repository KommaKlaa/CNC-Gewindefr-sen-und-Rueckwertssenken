"""Scrollbare Referenzgrafik mit Fit/Zoom fuer BSF-Geometriehilfe."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from help_assets import BSF_HELP_MISSING_TEXT, help_image_scaler_mode

try:
    from PIL import Image, ImageTk

    _PIL = True
except ImportError:
    _PIL = False


class BSFReferenceImagePanel:
    """Zeigt eine PNG gross, proportional, mit Zoom und Scrollbars."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_missing: Optional[Callable[[], None]] = None,
    ) -> None:
        self._on_missing = on_missing
        self._source_path: Optional[str] = None
        self._pil_source: Optional["Image.Image"] = None
        self._tk_source: Optional[tk.PhotoImage] = None
        self._display_img: Optional[tk.PhotoImage] = None
        self._zoom = 1.0
        self._native_w = 1
        self._native_h = 1
        self._fit_mode = True

        self.frame = ttk.Frame(master)
        tools = ttk.Frame(self.frame)
        tools.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(tools, text="Zoom +", command=lambda: self.set_zoom(self._zoom * 1.15)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tools, text="Zoom -", command=lambda: self.set_zoom(self._zoom / 1.15)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tools, text="100 %", command=self.set_100_percent).pack(side=tk.LEFT, padx=2)
        ttk.Button(tools, text="An Fenster", command=self.fit_to_window).pack(side=tk.LEFT, padx=2)
        self._scaler_var = tk.StringVar(value=f"Scaler: {help_image_scaler_mode()}")
        ttk.Label(tools, textvariable=self._scaler_var, foreground="#57606a").pack(side=tk.RIGHT)

        holder = ttk.Frame(self.frame)
        holder.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(holder, background="#f6f8fa", highlightthickness=0)
        sy = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=self.canvas.yview)
        sx = ttk.Scrollbar(holder, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.canvas.bind("<Configure>", self._on_configure)

        self.msg = tk.StringVar(value="")
        ttk.Label(self.frame, textvariable=self.msg, foreground="#cf222e").pack(anchor=tk.W, pady=(4, 0))

    def pack(self, **kwargs) -> None:
        self.frame.pack(**kwargs)

    def load_from_path(self, path: Optional[str]) -> bool:
        self._source_path = path
        self._pil_source = None
        self._tk_source = None
        self._display_img = None
        if not path:
            self.canvas.delete("all")
            self.msg.set(BSF_HELP_MISSING_TEXT)
            if self._on_missing:
                self._on_missing()
            return False
        try:
            if _PIL:
                self._pil_source = Image.open(path).convert("RGBA")
                self._native_w, self._native_h = self._pil_source.size
            else:
                self._tk_source = tk.PhotoImage(file=path)
                self._native_w = max(1, self._tk_source.width())
                self._native_h = max(1, self._tk_source.height())
        except (OSError, tk.TclError) as exc:
            self.canvas.delete("all")
            self.msg.set(str(exc))
            if self._on_missing:
                self._on_missing()
            return False
        self.msg.set("")
        self._fit_mode = True
        self._render()
        return True

    def fit_to_window(self) -> None:
        self._fit_mode = True
        self._render()

    def set_100_percent(self) -> None:
        self._fit_mode = False
        self._zoom = 1.0
        self._render()

    def set_zoom(self, value: float) -> None:
        self._fit_mode = False
        self._zoom = min(4.0, max(0.25, value))
        self._render()

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def aspect_ratio(self) -> float:
        if self._native_h <= 0:
            return 1.0
        return self._native_w / self._native_h

    @property
    def display_size(self) -> tuple[int, int]:
        if self._display_img is None:
            return (0, 0)
        return (self._display_img.width(), self._display_img.height())

    def _on_configure(self, _event=None) -> None:
        if self._fit_mode and (self._pil_source is not None or self._tk_source is not None):
            self._render()

    def _effective_zoom(self) -> float:
        if not self._fit_mode:
            return self._zoom
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        return min(cw / self._native_w, ch / self._native_h, 4.0)

    def _render(self) -> None:
        self.canvas.delete("all")
        if self._pil_source is None and self._tk_source is None:
            return
        zoom = self._effective_zoom()
        self._zoom = zoom
        target_w = max(1, int(round(self._native_w * zoom)))
        target_h = max(1, int(round(self._native_h * zoom)))
        if _PIL and self._pil_source is not None:
            resized = self._pil_source.resize((target_w, target_h), Image.Resampling.LANCZOS)
            master = self.canvas.winfo_toplevel()
            self._display_img = ImageTk.PhotoImage(resized, master=master)
        else:
            self._display_img = self._best_tk_scale(self._tk_source, zoom)
        self.canvas._bsf_ref_image = self._display_img
        try:
            self.canvas.create_image(0, 0, anchor="nw", image=self._display_img, tags=("reference_image",))
        except tk.TclError:
            return
        self.canvas.configure(scrollregion=(0, 0, target_w, target_h))

    @staticmethod
    def _best_tk_scale(src: tk.PhotoImage, zoom: float) -> tk.PhotoImage:
        if zoom >= 1.0:
            best = (1, 1, abs(1.0 - zoom))
            for n in range(1, 9):
                for m in range(1, 9):
                    factor = n / m
                    err = abs(factor - zoom)
                    if err < best[2]:
                        best = (n, m, err)
            img = src.zoom(best[0], best[0])
            if best[1] > 1:
                img = img.subsample(best[1], best[1])
            return img
        best = (1, 1, abs(1.0 - zoom))
        for n in range(1, 9):
            for m in range(1, 17):
                factor = n / m
                err = abs(factor - zoom)
                if err < best[2]:
                    best = (n, m, err)
        return src.zoom(best[0], best[0]).subsample(best[1], best[1])
