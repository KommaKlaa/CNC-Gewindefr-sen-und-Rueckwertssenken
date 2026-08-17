"""Scrollbarer Parameterbereich fuer dichte GUIs."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    """Canvas + Scrollbar; Kinder in ``.body`` platzieren."""

    def __init__(self, master, *, height: int = 480, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, height=height)
        self.vscroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self._wheel_bound = False

        self.canvas.configure(yscrollcommand=self.vscroll.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # bind_all nur solange Maus ueber dem Scrollbereich – vermeidet Test-/Leak-Probleme
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.body.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)
        self.bind("<Destroy>", self._on_destroy)

    def _on_body_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._win, width=event.width)

    def _bind_wheel(self, _event=None) -> None:
        if not self._wheel_bound:
            self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
            self._wheel_bound = True

    def _unbind_wheel(self, _event=None) -> None:
        if self._wheel_bound:
            try:
                self.canvas.unbind_all("<MouseWheel>")
            except tk.TclError:
                pass
            self._wheel_bound = False

    def _on_destroy(self, _event=None) -> None:
        self._unbind_wheel()

    def _on_mousewheel(self, event) -> None:
        try:
            if not self.canvas.winfo_exists():
                self._unbind_wheel()
                return
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except tk.TclError:
            self._unbind_wheel()
