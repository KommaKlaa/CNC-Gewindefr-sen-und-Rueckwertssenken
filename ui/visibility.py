"""Sichtbarkeit von LabelFrames ohne Layout-Restflaeche."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional


def show_pack(frame: tk.Misc, **kwargs) -> None:
    if frame.winfo_manager():
        frame.pack_forget()
    frame.pack(**kwargs)


def hide_pack(frame: tk.Misc) -> None:
    if frame.winfo_manager():
        frame.pack_forget()


def show_grid(frame: tk.Misc, **kwargs) -> None:
    if frame.winfo_manager():
        frame.grid_forget()
    frame.grid(**kwargs)


def hide_grid(frame: tk.Misc) -> None:
    if frame.winfo_manager():
        frame.grid_forget()


def is_mapped(widget: tk.Misc) -> bool:
    return bool(widget.winfo_manager())
