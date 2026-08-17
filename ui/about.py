"""Read-only Info-/Ueber-Fenster (keine Projekt- oder NC-Aenderung)."""

from __future__ import annotations

import logging
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Optional

from app_info import (
    APP_AUTHOR,
    APP_COPYRIGHT,
    APP_DESCRIPTION,
    APP_EMAIL,
    APP_MAILTO,
    APP_NAME,
    APP_VERSION,
    APP_WEBSITE,
    APP_WEBSITE_URL,
)
from app_paths import APP_ICON_PNG_REL, apply_window_icon, resource_path

logger = logging.getLogger(__name__)

_COLOR_LINK = "#0969da"
_COLOR_MUTED = "#57606a"
_COLOR_BG = "#f0f4f8"


def _safe_open(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception as exc:
        logger.debug("Externer Link konnte nicht geoeffnet werden: %s", exc)


def open_about_window(master: tk.Misc) -> tk.Toplevel:
    win = tk.Toplevel(master)
    win.title(f"Info – {APP_NAME}")
    win.resizable(False, False)
    win.configure(bg=_COLOR_BG)
    apply_window_icon(win)

    body = tk.Frame(win, bg=_COLOR_BG, padx=24, pady=20)
    body.pack(fill=tk.BOTH, expand=True)

    png = resource_path(APP_ICON_PNG_REL)
    photo: Optional[tk.PhotoImage] = None
    if png.is_file():
        try:
            photo = tk.PhotoImage(file=str(png))
            if photo.width() > 96:
                factor = max(1, photo.width() // 96)
                photo = photo.subsample(factor, factor)
            win._about_photo = photo  # Referenz gegen Garbage Collection
            tk.Label(body, image=photo, bg=_COLOR_BG).pack(pady=(0, 10))
        except tk.TclError as exc:
            logger.debug("Info-Icon konnte nicht geladen werden: %s", exc)

    tk.Label(body, text=APP_NAME, font=("Segoe UI", 14, "bold"), bg=_COLOR_BG).pack()
    tk.Label(
        body, text=f"Version {APP_VERSION}", fg=_COLOR_MUTED, bg=_COLOR_BG, font=("Segoe UI", 10)
    ).pack(pady=(2, 10))

    desc_lines = APP_DESCRIPTION.replace(" für ", " für\n")
    tk.Label(body, text=desc_lines, justify=tk.CENTER, bg=_COLOR_BG, font=("Segoe UI", 10)).pack(
        pady=(0, 12)
    )

    tk.Label(body, text="Entwicklung", font=("Segoe UI", 9, "bold"), bg=_COLOR_BG).pack()
    tk.Label(body, text=APP_AUTHOR, bg=_COLOR_BG, font=("Segoe UI", 10)).pack(pady=(0, 10))

    web = tk.Label(
        body,
        text=APP_WEBSITE,
        fg=_COLOR_LINK,
        cursor="hand2",
        font=("Segoe UI", 10, "underline"),
        bg=_COLOR_BG,
    )
    web.pack()
    web.bind("<Button-1>", lambda _e: _safe_open(APP_WEBSITE_URL))

    mail = tk.Label(
        body,
        text=APP_EMAIL,
        fg=_COLOR_LINK,
        cursor="hand2",
        font=("Segoe UI", 10, "underline"),
        bg=_COLOR_BG,
    )
    mail.pack(pady=(2, 12))
    mail.bind("<Button-1>", lambda _e: _safe_open(APP_MAILTO))

    tk.Label(body, text=APP_COPYRIGHT, fg=_COLOR_MUTED, bg=_COLOR_BG, font=("Segoe UI", 9)).pack(
        pady=(0, 14)
    )
    ttk.Button(body, text="Schließen", command=win.destroy).pack()
    win.focus_force()
    return win
