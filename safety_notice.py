"""Sicherheits-, Haftungs- und Markenhinweis fuer den NC-Code Generator."""

from __future__ import annotations

import json
import logging
import os
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Dict, Optional

from app_info import APP_NAME, APP_VERSION
from app_paths import apply_window_icon

logger = logging.getLogger(__name__)

SAFETY_NOTICE_TITLE = "Sicherheits- und Nutzungshinweis"

SAFETY_NOTICE_TEXT = (
    "Der NC-Code Generator ist ein Hilfsmittel zur Erstellung von NC-Programmen.\n\n"
    "Die erzeugten Programme dürfen nicht ungeprüft auf einer CNC-Maschine "
    "ausgeführt werden.\n\n"
    "Vor jedem Einsatz sind insbesondere Werkzeug, Werkzeugdaten, "
    "Werkstücknullpunkt, Spannmittel, Bearbeitungsrichtung, Drehzahlen, "
    "Vorschübe, M-Funktionen, Sicherheitsabstände sowie mögliche Kollisionen "
    "zu prüfen.\n\n"
    "Die Programme sind vor der produktiven Bearbeitung nach Möglichkeit in der "
    "Maschinen-/CNC-Simulation und anschließend unter geeigneten "
    "Sicherheitsmaßnahmen, z. B. im Einzelsatz oder Trockenlauf, zu "
    "kontrollieren.\n\n"
    "Die Verwendung der erzeugten NC-Programme erfolgt eigenverantwortlich.\n\n"
    "HEULE und CERATIZIT sind Marken bzw. eingetragene Marken ihrer jeweiligen "
    "Rechteinhaber.\n\n"
    "Die Nennung der Marken dient ausschließlich der Beschreibung kompatibler "
    "Werkzeuge und Verfahren.\n\n"
    "Dieses Programm ist kein Produkt von HEULE oder CERATIZIT und stellt keine "
    "Freigabe, Zertifizierung oder Empfehlung durch diese Unternehmen dar."
)

TRADEMARK_NOTICE_TEXT = (
    "HEULE und CERATIZIT sind Marken bzw. eingetragene Marken ihrer jeweiligen "
    "Rechteinhaber.\n\n"
    "Keine Verbindung oder Herstellerfreigabe durch HEULE oder CERATIZIT."
)

SETTINGS_FILENAME = "settings.json"
SETTINGS_KEY = "accepted_safety_notice_version"
ENV_SKIP = "NC_GENERATOR_SKIP_SAFETY_NOTICE"
ENV_SETTINGS_PATH = "NC_GENERATOR_SETTINGS_PATH"


def user_settings_path() -> Path:
    """Benutzerprofil-Pfad; nicht im Programm-/Releaseordner."""
    override = os.environ.get(ENV_SETTINGS_PATH, "").strip()
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        return Path(appdata) / APP_NAME / SETTINGS_FILENAME
    return Path.home() / ".nc-code-generator" / SETTINGS_FILENAME


def load_settings(path: Optional[Path] = None) -> Dict[str, Any]:
    settings_path = path or user_settings_path()
    if not settings_path.is_file():
        return {}
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Settings konnten nicht gelesen werden: %s", exc)
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(data: Dict[str, Any], path: Optional[Path] = None) -> bool:
    settings_path = path or user_settings_path()
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return True
    except OSError as exc:
        logger.debug("Settings konnten nicht gespeichert werden: %s", exc)
        return False


def accepted_safety_notice_version(path: Optional[Path] = None) -> Optional[str]:
    value = load_settings(path).get(SETTINGS_KEY)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def is_safety_notice_accepted(
    app_version: str = APP_VERSION,
    *,
    path: Optional[Path] = None,
) -> bool:
    return accepted_safety_notice_version(path) == app_version


def record_safety_notice_acceptance(
    app_version: str = APP_VERSION,
    *,
    path: Optional[Path] = None,
) -> bool:
    data = load_settings(path)
    data[SETTINGS_KEY] = app_version
    return save_settings(data, path)


def _should_skip_startup_notice() -> bool:
    if os.environ.get(ENV_SKIP) == "1":
        return True
    if os.environ.get("NC_GENERATOR_RUNTIME_SMOKE") == "1":
        return True
    return False


def ensure_startup_safety_notice(
    master: tk.Misc,
    *,
    app_version: str = APP_VERSION,
    settings_path: Optional[Path] = None,
) -> bool:
    """True = App darf starten; False = Benutzer hat beendet."""
    if _should_skip_startup_notice():
        return True
    if is_safety_notice_accepted(app_version, path=settings_path):
        return True
    return show_startup_safety_notice(
        master,
        app_version=app_version,
        settings_path=settings_path,
    )


def show_startup_safety_notice(
    master: tk.Misc,
    *,
    app_version: str = APP_VERSION,
    settings_path: Optional[Path] = None,
) -> bool:
    return _SafetyNoticeDialog(
        master,
        mode="startup",
        app_version=app_version,
        settings_path=settings_path,
    ).show()


def show_safety_notice(master: tk.Misc) -> None:
    _SafetyNoticeDialog(master, mode="help").show()


class _SafetyNoticeDialog:
    def __init__(
        self,
        master: tk.Misc,
        *,
        mode: str,
        app_version: str = APP_VERSION,
        settings_path: Optional[Path] = None,
    ) -> None:
        self.master = master
        self.mode = mode
        self.app_version = app_version
        self.settings_path = settings_path
        self.accepted = False
        self.win: Optional[tk.Toplevel] = None

    def show(self) -> bool:
        self._build()
        assert self.win is not None
        if self.mode == "startup":
            self.win.grab_set()
            self.master.wait_window(self.win)
        return self.accepted

    def _build(self) -> None:
        win = tk.Toplevel(self.master)
        self.win = win
        win.title(SAFETY_NOTICE_TITLE)
        win.transient(self.master)
        win.resizable(True, True)
        win.minsize(520, 420)
        apply_window_icon(win)

        if self.mode == "startup":
            win.protocol("WM_DELETE_WINDOW", self._on_exit)
            win.bind("<Escape>", lambda _event: self._on_exit())
        else:
            win.protocol("WM_DELETE_WINDOW", win.destroy)
            win.bind("<Escape>", lambda _event: win.destroy())

        outer = ttk.Frame(win, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        ttk.Label(
            outer,
            text=SAFETY_NOTICE_TITLE,
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 8))

        text_frame = ttk.Frame(outer)
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL)
        text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=("Segoe UI", 10),
            relief=tk.FLAT,
            padx=8,
            pady=8,
            height=16,
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=text.yview)
        text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        text.insert("1.0", SAFETY_NOTICE_TEXT)
        text.config(state=tk.DISABLED)

        button_row = ttk.Frame(outer)
        button_row.grid(row=2, column=0, sticky=tk.E, pady=(12, 0))

        if self.mode == "startup":
            exit_btn = ttk.Button(button_row, text="Programm beenden", command=self._on_exit)
            exit_btn.pack(side=tk.RIGHT, padx=(8, 0))
            accept_btn = ttk.Button(
                button_row,
                text="Verstanden und akzeptiert",
                command=self._on_accept,
            )
            accept_btn.pack(side=tk.RIGHT)
            accept_btn.focus_set()
            win.bind("<Return>", lambda _event: self._on_accept())
        else:
            close_btn = ttk.Button(button_row, text="Schließen", command=win.destroy)
            close_btn.pack(side=tk.RIGHT)
            close_btn.focus_set()
            win.bind("<Return>", lambda _event: win.destroy())

        win.update_idletasks()
        self._center_over_master(win)

    def _center_over_master(self, win: tk.Toplevel) -> None:
        win.update_idletasks()
        width = max(win.winfo_width(), 520)
        height = max(win.winfo_height(), 420)
        master = self.master.winfo_toplevel()
        master.update_idletasks()
        mx = master.winfo_rootx()
        my = master.winfo_rooty()
        mw = max(master.winfo_width(), 1)
        mh = max(master.winfo_height(), 1)
        x = mx + max(0, (mw - width) // 2)
        y = my + max(0, (mh - height) // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")

    def _on_accept(self) -> None:
        record_safety_notice_acceptance(self.app_version, path=self.settings_path)
        self.accepted = True
        if self.win is not None:
            self.win.destroy()

    def _on_exit(self) -> None:
        self.accepted = False
        if self.win is not None:
            self.win.destroy()


def startup_exit_if_declined(master: tk.Misc) -> None:
    """Hilfsfunktion fuer den App-Start: bei Abbruch sauber beenden."""
    if not ensure_startup_safety_notice(master):
        try:
            master.destroy()
        finally:
            raise SystemExit(0)
