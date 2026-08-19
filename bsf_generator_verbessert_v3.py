#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Heidenhain iTNC 530 Klartext-Code Generator
- HEULE BSF Rueckwaertssenken
- CERATIZIT Bohrgewindefraeser BGF nach Hersteller-Beispielprogramm

Programmierer: Jens Behm
Ueberarbeitet: BGF-Herstellerbahnen, sichere Teilkreis-Schleife mit Zaehler,
Teilkreis-Pol CC, Einzelbohrung/Teilkreis sauber getrennt.
Version v3: CP-Einfahrbogen mit explizitem Vorschub statt modalem/leeren F.

Wichtiger Hinweis:
Das erzeugte NC-Programm ist eine Vorlage. Nullpunkt, Werkzeugdaten,
Drehrichtung, Kuehlung, M-Funktionen, Kollisionsfreiheit und Simulation muessen
vor Maschineneinsatz geprueft werden.
"""

import math
import os
import re
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Dict, List, Optional

from coordinates import (
    PositionMode,
    CoordinateParseError,
    BGFCoordinatePosition,
    BSFCoordinatePosition,
    parse_bgf_coordinate_text,
    parse_coordinate_text,
    validate_bgf_coordinate_list,
    validate_bsf_coordinate_list,
    bsf_position_status_label,
    status_label_for,
    emit_bgf_coordinate_program_body,
    emit_bsf_coordinate_program_body,
    BGFDocumentError,
    build_document,
    load_document_json,
    resolve_tool_in_catalog,
    save_document_json,
    export_bgf_csv,
    import_bgf_csv_text,
    write_bgf_csv_file,
    BSFDocumentError,
    build_bsf_document,
    load_bsf_document_json,
    save_bsf_document_json,
    import_bsf_csv_text,
    write_bsf_csv_file,
)

from bgf_surface import (
    DEFAULT_APPROACH_CLEARANCE,
    absolute_from_surface,
    above_surface,
    at_surface,
    validate_approach_clearance,
)
from bgf_variable_depth import axial_increment_from_passes
from bgf_depth import (
    BGFDepthRequest,
    DepthGateStatus,
    evaluate_bgf_depth,
    policy_from_tool,
    thread_end_z,
)
from bgf_depth_reference import references_for_size
from bgf_depth_approvals import approved_max_thread_depth
from bsf_blade import (
    apply_workpiece_reference_z,
    calculate_workpiece_bsf_z,
    parse_reference_z,
    spindle_on_z,
    validate_bsf_safe_z_against_reference,
)
from heule_bsf_tools import (
    MEASUREMENT_LABEL,
    MEASUREMENT_MODEL,
    MEASUREMENT_NC_COMMENT,
    MEASUREMENT_OFFSET_DIRECTION,
    TOOL_SELECTION_REQUIRED,
    apply_measurement_face_offset,
    ordered_tool_profiles,
    profile_by_designation,
    profile_by_key,
    profile_options,
)
from coordinates.bsf_list_document import (
    APPROACH_FEED_FACTOR_FULL,
    APPROACH_FEED_FACTOR_REDUCED,
    z_reference_from_label,
)

from app_paths import apply_window_icon
from app_info import APP_NAME
from runtime_smoke import schedule_runtime_smoke_if_requested
from safety_notice import ensure_startup_safety_notice, show_safety_notice
from nc_programmer import ProgrammerError, normalize_programmer, programmer_comment_line
from nc_state import (
    NcOutputGuard,
    STATUS_CURRENT_TEXT,
    STATUS_STALE_TEXT,
    STALE_ACTION_MESSAGE,
)
from stock_z import (
    SURFACE_OUTSIDE_STOCK_MESSAGE,
    all_surfaces_inside_stock,
    blk_form_z_extents,
)
from ui.about import open_about_window as show_about_dialog
from ui import MODE_BGF, MODE_BSF, POSITION_LABELS_BGF, POSITION_LABELS_BSF, ScrollableFrame
from ui.visibility import hide_grid, hide_pack, is_mapped, show_grid, show_pack


# ---------------------------------------------------------------------------
# BGF-Herstellerdaten nach CERATIZIT Beispielprogramm
# Bezug: Aussenbahn, inkremental, Fraesmethode Gegenlauf.
# M5 bis M10: 2-fach radial.
# M16 und M16x1,5: keine Schnittaufteilung.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BGFPass:
    y_start: float
    feed_start: int
    cc_entry_y: float
    iz_entry: float
    cc_thread_y: float
    iz_thread: float
    feed_thread: int
    cc_exit_y: float
    iz_exit: float
    feed_exit: int


@dataclass(frozen=True)
class BGFToolData:
    size: str
    article_no: str
    radius: float
    thread_length: float
    drill_depth: float
    mill_start_depth: float
    pitch: float
    spindle_speed: int
    feed_drill: int
    passes: List[BGFPass]
    predrill_depth: Optional[float] = None
    feed_predrill: Optional[int] = None
    note: str = ""


BGF_DATA: Dict[str, BGFToolData] = {
    "M5": BGFToolData(
        size="M5",
        article_no="5089805000",
        radius=2.0060,
        thread_length=12.58,
        drill_depth=14.0460,
        mill_start_depth=12.5120,
        pitch=0.8,
        spindle_speed=15000,
        feed_drill=1200,
        passes=[
            BGFPass(2.0060, 125, -2.1880, -0.1200, 2.3700, -0.8000, 230, 2.1880, -0.1200, 312),
            BGFPass(2.0060, 164, -2.2530, -0.1200, 2.5000, -0.8000, 296, 2.2530, -0.1200, 411),
        ],
    ),
    "M6": BGFToolData(
        size="M6",
        article_no="5089806000",
        radius=2.3770,
        thread_length=14.69,
        drill_depth=16.4860,
        mill_start_depth=14.5630,
        pitch=1.0,
        spindle_speed=15000,
        feed_drill=1350,
        passes=[
            BGFPass(2.3770, 157, -2.6035, -0.1500, 2.8300, -1.0000, 288, 2.6035, -0.1500, 391),
            BGFPass(2.3770, 209, -2.6885, -0.1500, 3.0000, -1.0000, 374, 2.6885, -0.1500, 521),
        ],
    ),
    "M8": BGFToolData(
        size="M8",
        article_no="5089808000",
        radius=3.1720,
        thread_length=20.88,
        drill_depth=23.1720,
        mill_start_depth=20.7190,
        pitch=1.25,
        spindle_speed=14147,
        feed_drill=1415,
        passes=[
            BGFPass(3.1720, 176, -3.4810, -0.1875, 3.7900, -1.2500, 323, 3.4810, -0.1875, 440),
            BGFPass(3.1720, 229, -3.5860, -0.1875, 4.0000, -1.2500, 410, 3.5860, -0.1875, 572),
        ],
    ),
    "M10": BGFToolData(
        size="M10",
        article_no="5089810000",
        radius=3.9790,
        thread_length=25.06,
        drill_depth=27.8700,
        mill_start_depth=24.8990,
        pitch=1.5,
        spindle_speed=11234,
        feed_drill=1348,
        passes=[
            BGFPass(3.9790, 159, -4.3645, -0.2250, 4.7500, -1.5000, 292, 4.3645, -0.2250, 397),
            BGFPass(3.9790, 204, -4.4895, -0.2250, 5.0000, -1.5000, 367, 4.4895, -0.2250, 511),
        ],
    ),
    "M16": BGFToolData(
        size="M16",
        article_no="5086916000",
        radius=6.5590,
        thread_length=32.96,
        drill_depth=37.1160,
        mill_start_depth=33.0750,
        pitch=2.0,
        spindle_speed=6821,
        feed_drill=2046,
        predrill_depth=2.1000,
        feed_predrill=682,
        passes=[
            BGFPass(6.5590, 135, -7.2795, -0.3000, 8.0000, -2.0000, 246, 7.2795, -0.3000, 338),
        ],
    ),
    "M16x1.5": BGFToolData(
        size="M16x1.5",
        article_no="Sonderwerkzeug",
        radius=6.9300,
        thread_length=32.60,
        drill_depth=36.3350,
        mill_start_depth=33.3150,
        pitch=1.5,
        spindle_speed=6586,
        feed_drill=1976,
        predrill_depth=2.2000,
        feed_predrill=659,
        passes=[
            BGFPass(6.9300, 94, -7.4650, -0.2250, 8.0000, -1.5000, 176, 7.4650, -0.2250, 236),
        ],
        note="Sonderwerkzeug / Daten aus Beispielprogramm M16x1,5",
    ),
}


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def fmt_axis(axis: str, value: float, decimals: int = 4) -> str:
    sign = "+" if value >= 0 else ""
    return f"{axis}{sign}{value:.{decimals}f}"


def fmt_q(value: float, decimals: int = 3) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.{decimals}f}"


def clean_program_name(value: str, default: str) -> str:
    name = (value or default).strip().upper()
    name = name.replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE").replace("ß", "SS")
    name = re.sub(r"[^A-Z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or default


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------


class BSFGeneratorGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1080x900")
        self.root.minsize(1000, 780)
        apply_window_icon(self.root)
        if not ensure_startup_safety_notice(self.root):
            self.root.destroy()
            raise SystemExit(0)

        self.bg_color = "#f0f4f8"
        self.accent_color = "#3498db"
        self.accent_hover = "#2980b9"
        self._last_coord_dir: Optional[str] = None
        self.text_color = "#2c3e50"
        self.root.configure(bg=self.bg_color)

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TFrame", background=self.bg_color, padding=8)
        self.style.configure(
            "TLabelframe",
            background=self.bg_color,
            foreground=self.text_color,
            font=("Segoe UI", 10, "bold"),
        )
        self.style.configure(
            "TLabelframe.Label",
            background=self.bg_color,
            foreground=self.accent_color,
            font=("Segoe UI", 11, "bold"),
        )
        self.style.configure("TLabel", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 9))
        self.style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=8)
        self.style.map("TButton", background=[("active", self.accent_hover)])

        self.entries: Dict[str, ttk.Entry] = {}
        self.bgf_info_labels: Dict[str, ttk.Label] = {}
        self._tool_num_var = tk.StringVar(value="8")
        self.programmer_var = tk.StringVar(value="")

        self.main_frame = ttk.Frame(root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        self.coord_rows: List[BGFCoordinatePosition] = []
        self.bsf_coord_rows: List[BSFCoordinatePosition] = []
        self._circle_entry_keys = ("diameter", "count", "start_angle", "center_x", "center_y")
        self._bgf_preview_window = None
        self._bsf_help_window = None
        self._bgf_help_window = None
        self.nc_guard = NcOutputGuard()
        self._nc_status_label = None

        self.create_header()
        self._create_menubar()

        # Split: Parameter (scrollbar) oben, NC-Ausgabe unten
        self.paned = ttk.Panedwindow(self.main_frame, orient=tk.VERTICAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        self.top_pane = ttk.Frame(self.paned)
        self.bottom_pane = ttk.Frame(self.paned)
        self.paned.add(self.top_pane, weight=3)
        self.paned.add(self.bottom_pane, weight=2)

        self.params_scroll = ScrollableFrame(self.top_pane, height=520)
        self.params_scroll.pack(fill=tk.BOTH, expand=True)
        self.params_host = self.params_scroll.body

        self.create_processing_selector()
        self.create_bgf_tool_panel()
        self.create_bgf_processing_panel()
        self.create_bsf_tool_panel()
        self.create_bsf_processing_panel()
        self.create_bsf_machine_panel()
        self.create_positioning_panel()
        self.create_common_parameters()
        self.create_buttons()
        self.create_output_field()
        self._install_nc_state_watchers()
        self.on_mode_change(None)
        self.on_position_mode_change(None)
        self.refresh_nc_output_status()
        schedule_runtime_smoke_if_requested(self)

    # ------------------------------------------------------------------
    # GUI-Aufbau (UI.1 – Bearbeitung / Positionierung entkoppelt)
    # ------------------------------------------------------------------

    def _create_menubar(self) -> None:
        menubar = tk.Menu(self.root)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(
            label="Sicherheits- und Nutzungshinweis",
            command=lambda: show_safety_notice(self.root),
        )
        help_menu.add_command(label="Info", command=self.open_about_window)
        menubar.add_cascade(label="Hilfe", menu=help_menu)
        self.root.config(menu=menubar)

    def open_about_window(self) -> None:
        show_about_dialog(self.root)

    def create_header(self) -> None:
        header_frame = tk.Frame(self.main_frame, bg=self.bg_color)
        header_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Button(header_frame, text="Info", command=self.open_about_window, width=8).pack(
            side=tk.RIGHT, padx=(4, 0)
        )

        tk.Label(
            header_frame,
            text="HEULE BSF & CERATIZIT BGF - iTNC 530 Generator",
            font=("Segoe UI", 15, "bold"),
            bg=self.bg_color,
            fg=self.accent_color,
        ).pack()

    def create_processing_selector(self) -> None:
        mode_frame = ttk.LabelFrame(self.params_host, text="Bearbeitung", padding=8)
        mode_frame.pack(fill=tk.X, pady=4)
        self.processing_frame = mode_frame

        ttk.Label(mode_frame, text="Bearbeitung:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=5)

        self.mode_var = tk.StringVar(value=MODE_BGF)
        self.mode_combo = ttk.Combobox(
            mode_frame,
            textvariable=self.mode_var,
            values=[MODE_BSF, MODE_BGF],
            state="readonly",
            width=28,
        )
        self.mode_combo.pack(side=tk.LEFT, padx=5)
        self.mode_combo.bind("<<ComboboxSelected>>", self.on_mode_change)

        # Alias fuer bestehende Tests / Logik (frueher ein grosses BGF-Panel)
        self.bgf_frame = None  # wird in create_bgf_* gesetzt

    def create_bgf_tool_panel(self) -> None:
        frame = ttk.LabelFrame(self.params_host, text="CERATIZIT BGF Werkzeug", padding=8)
        frame.pack(fill=tk.X, pady=4)
        self.bgf_tool_frame = frame
        self.bgf_frame = frame  # Kompatibilitaet: pack/forget ueber on_mode_change

        ttk.Label(frame, text="Gewinde:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.bgf_size_var = tk.StringVar(value="M10")
        bgf_size_combo = ttk.Combobox(
            frame,
            textvariable=self.bgf_size_var,
            values=list(BGF_DATA.keys()),
            state="readonly",
            width=12,
        )
        bgf_size_combo.grid(row=0, column=1, sticky=tk.W, pady=2)
        bgf_size_combo.bind("<<ComboboxSelected>>", self.on_bgf_size_change)

        ttk.Label(frame, text="Werkzeugnummer T:").grid(row=0, column=2, sticky=tk.W, padx=(16, 4))
        ttk.Label(frame, textvariable=self._tool_num_var).grid(row=0, column=3, sticky=tk.W, pady=2)

        info_fields = [
            ("Artikel", "article_no"),
            ("Werkzeugradius", "radius"),
            ("Template Gewindetiefe", "thread_length"),
            ("Template Bohrtiefe", "drill_depth"),
            ("Template Fraesstart", "mill_start_depth"),
            ("Steigung", "pitch"),
            ("Drehzahl", "spindle_speed"),
            ("Vorschub Bohren", "feed_drill"),
            ("Radial-Durchgaenge", "passes"),
        ]
        self.bgf_info_labels.clear()
        for idx, (caption, key) in enumerate(info_fields):
            row = 1 + idx // 3
            col = (idx % 3) * 2
            ttk.Label(frame, text=f"{caption}:").grid(row=row, column=col, sticky=tk.W, padx=(0, 4), pady=1)
            label = ttk.Label(frame, text="-")
            label.grid(row=row, column=col + 1, sticky=tk.W, padx=(0, 12), pady=1)
            self.bgf_info_labels[key] = label

        self.output_tool_def_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="TOOL DEF aktivieren (Radius ausgeben, Laenge/Tooldaten pruefen)",
            variable=self.output_tool_def_var,
        ).grid(row=5, column=0, columnspan=6, sticky=tk.W, pady=(6, 2))

        # load_bgf_values nach create_bgf_processing_panel

    def create_bgf_processing_panel(self) -> None:
        frame = ttk.LabelFrame(self.params_host, text="CERATIZIT BGF Bearbeitungsparameter", padding=8)
        frame.pack(fill=tk.X, pady=4)
        self.bgf_processing_frame = frame

        ttk.Label(frame, text="Gewindetiefe [mm]:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.entries["bgf_thread_depth"] = ttk.Entry(frame, width=12)
        self.entries["bgf_thread_depth"].grid(row=0, column=1, sticky=tk.W, padx=(4, 16), pady=2)
        self.entries["bgf_thread_depth"].bind("<KeyRelease>", self.on_bgf_depth_input_change)
        self.entries["bgf_thread_depth"].bind("<FocusOut>", self.on_bgf_depth_input_change)

        ttk.Label(frame, text="Kernlochtiefe Soll [mm]:").grid(row=0, column=2, sticky=tk.W, pady=2)
        self.entries["bgf_core_hole_depth"] = ttk.Entry(frame, width=12)
        self.entries["bgf_core_hole_depth"].grid(row=0, column=3, sticky=tk.W, padx=(4, 8), pady=2)
        self.entries["bgf_core_hole_depth"].bind("<KeyRelease>", self.on_bgf_depth_input_change)
        self.entries["bgf_core_hole_depth"].bind("<FocusOut>", self.on_bgf_depth_input_change)
        ttk.Label(frame, text="(leer = keine Angabe)").grid(row=0, column=4, sticky=tk.W)

        ttk.Label(frame, text="Sicherheitsabstand ueber Oberflaeche [mm]:").grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        self.entries["approach_clearance"] = ttk.Entry(frame, width=12)
        self.entries["approach_clearance"].insert(0, f"{DEFAULT_APPROACH_CLEARANCE:.3f}")
        self.entries["approach_clearance"].grid(row=1, column=1, sticky=tk.W, padx=(4, 12), pady=2)
        ttk.Label(
            frame,
            text="Anfahr-Z = Bohrungsanfang Z + Sicherheitsabstand",
            font=("Segoe UI", 8),
        ).grid(row=1, column=2, columnspan=3, sticky=tk.W)

        self.bgf_depth_info_labels = {}
        info_rows = [
            (2, "Gewindeende:", "thread_end"),
            (3, "Aktuell freigegebene max. Gewindetiefe:", "max_depth"),
            (4, "NC-Bohrposition:", "nc_drill"),
            (5, "Berechneter Fraesstart:", "nc_mill"),
            (6, "Tiefenmodus:", "depth_mode"),
            (7, "Tiefenstatus:", "status"),
        ]
        for row, caption, key in info_rows:
            ttk.Label(frame, text=caption).grid(row=row, column=0, sticky=tk.W, pady=1)
            lab = ttk.Label(frame, text="-")
            lab.grid(row=row, column=1, columnspan=4, sticky=tk.W, pady=1)
            self.bgf_depth_info_labels[key] = lab

        ttk.Label(
            frame,
            text="Tiefenmodell: AXIAL_TEMPLATE_SHIFT – inkrementelle CERATIZIT-Bahn unveraendert.",
            font=("Segoe UI", 8),
        ).grid(row=8, column=0, columnspan=4, sticky=tk.W, pady=(4, 0))
        ttk.Button(
            frame,
            text="Hilfsgrafik Gewinde",
            command=self.open_bgf_geometry_help,
        ).grid(row=8, column=4, sticky=tk.E, pady=(4, 0))

        self.load_bgf_values()

    def create_bsf_tool_panel(self) -> None:
        frame = ttk.LabelFrame(self.params_host, text="HEULE BSF Werkzeug", padding=8)
        # nicht packen – on_mode_change steuert Sichtbarkeit
        self.bsf_tool_frame = frame

        ttk.Label(frame, text="Werkzeugnummer T:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Label(frame, textvariable=self._tool_num_var, width=8).grid(
            row=0, column=1, sticky=tk.W, padx=(4, 16), pady=2
        )

        ttk.Label(frame, text="Spindeldrehzahl S:").grid(row=0, column=2, sticky=tk.W, pady=2)
        self.entries["spindle_speed"] = ttk.Entry(frame, width=10)
        self.entries["spindle_speed"].insert(0, "800")
        self.entries["spindle_speed"].grid(row=0, column=3, sticky=tk.W, padx=(4, 16), pady=2)

        ttk.Label(frame, text="Vorschub F:").grid(row=0, column=4, sticky=tk.W, pady=2)
        self.entries["feed_rate"] = ttk.Entry(frame, width=10)
        self.entries["feed_rate"].insert(0, "60")
        self.entries["feed_rate"].grid(row=0, column=5, sticky=tk.W, padx=4, pady=2)

        ttk.Label(frame, text="HEULE Werkzeug:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.bsf_tool_profile_var = tk.StringVar(value=TOOL_SELECTION_REQUIRED)
        self.bsf_tool_profile_combo = ttk.Combobox(
            frame,
            textvariable=self.bsf_tool_profile_var,
            values=profile_options(),
            state="readonly",
            width=34,
        )
        self.bsf_tool_profile_combo.grid(row=1, column=1, columnspan=3, sticky=tk.W, padx=(4, 16), pady=2)
        self.bsf_tool_profile_combo.bind("<<ComboboxSelected>>", self.on_bsf_tool_profile_change)
        self.blade_measurement_var = tk.StringVar(value=MEASUREMENT_LABEL)
        self.blade_measurement_combo = ttk.Combobox(frame, textvariable=self.blade_measurement_var, values=(MEASUREMENT_LABEL,), state="readonly")
        self.entries["blade_thickness"] = ttk.Entry(frame, width=10)

        ttk.Label(frame, text="Vermessung:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.bsf_measurement_value = tk.StringVar(value=MEASUREMENT_LABEL)
        ttk.Label(frame, textvariable=self.bsf_measurement_value).grid(
            row=2, column=1, sticky=tk.W, padx=(4, 16), pady=2
        )

        ttk.Label(frame, text="Abstand Vermessfläche -> Schneide:").grid(row=2, column=2, sticky=tk.W, pady=2)
        self.bsf_measurement_face_to_edge_value = tk.StringVar(value="—")
        ttk.Label(frame, textvariable=self.bsf_measurement_face_to_edge_value).grid(
            row=2, column=3, sticky=tk.W, padx=(4, 16), pady=2
        )

        ttk.Label(frame, text="HEULE Aktivierungsdrehzahl:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.bsf_activation_speed_value = tk.StringVar(value="—")
        ttk.Label(frame, textvariable=self.bsf_activation_speed_value).grid(
            row=3, column=1, sticky=tk.W, padx=(4, 16), pady=2
        )

        ttk.Label(
            frame,
            text="Werkzeuglaenge an der unteren Werkzeug-Stirnflaeche vermessen; Offset kommt aus dem HEULE-Profil.",
            font=("Segoe UI", 8),
        ).grid(row=4, column=0, columnspan=6, sticky=tk.W, pady=(4, 0))
        self.on_bsf_tool_profile_change()

    def create_bsf_processing_panel(self) -> None:
        """HEULE BSF Bearbeitungsparameter (Werkstueck: Bund, Senkmass, Z0, Freifahrt).

        Schwertgeometrie (blade_thickness, measurement_reference) steht im
        Werkzeug-Panel; Domain: bsf_blade.py.
        """
        frame = ttk.LabelFrame(self.params_host, text="HEULE BSF Bearbeitungsparameter", padding=8)
        self.bsf_processing_frame = frame

        fields = [
            (0, 0, "Bund-Dicke (mm):", "bund_thickness", "18"),
            (0, 2, "Senk-Fertigmaß (mm):", "sink_depth", "38"),
            (0, 4, "Freifahr-Tiefe unten (mm):", "clearance", "23"),
            (1, 0, "Wartezeit Druckaufbau (s):", "dwell_time", "1.5"),
        ]
        for row, col, label, key, default in fields:
            ttk.Label(frame, text=label).grid(row=row, column=col, sticky=tk.W, pady=2, padx=(0, 4))
            entry = ttk.Entry(frame, width=12)
            entry.insert(0, default)
            entry.grid(row=row, column=col + 1, sticky=tk.W, pady=2, padx=(0, 12))
            self.entries[key] = entry

        ttk.Label(frame, text="Bezugsebene:").grid(row=1, column=2, sticky=tk.W, pady=2)
        self.z0_var = tk.StringVar(value="Z0 ist Unterkante Bund")
        ttk.Combobox(
            frame,
            textvariable=self.z0_var,
            values=["Z0 ist Unterkante Bund", "Z0 ist Oberkante Bund"],
            state="readonly",
            width=24,
        ).grid(row=1, column=3, columnspan=2, sticky=tk.W, pady=2)

        ttk.Label(frame, text="Z-Lage Bezugsebene [mm]:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.entries["bsf_reference_z"] = ttk.Entry(frame, width=12)
        self.entries["bsf_reference_z"].insert(0, "0")
        self.entries["bsf_reference_z"].grid(row=2, column=1, sticky=tk.W, pady=2, padx=(0, 12))
        ttk.Label(
            frame,
            text="Absolute Z-Koordinate der Werkstueckflaeche, an der die Bohrung beginnt.",
            font=("Segoe UI", 8),
        ).grid(row=2, column=2, columnspan=4, sticky=tk.W, pady=2)

        self.reduce_approach_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame,
            text="Anschnitt-Vorschub reduzieren (50%)",
            variable=self.reduce_approach_var,
        ).grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(6, 0))
        ttk.Button(
            frame,
            text="Hilfsgrafik Senken",
            command=self.open_bsf_geometry_help,
        ).grid(row=3, column=4, columnspan=2, sticky=tk.E, pady=(6, 0))

    def create_bsf_machine_panel(self) -> None:
        frame = ttk.LabelFrame(self.params_host, text="HEULE BSF Maschinenoptionen", padding=8)
        self.bsf_machine_frame = frame
        self.machine_frame = frame  # Alias

        ttk.Label(frame, text="Aktivierung BSF-Messer:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.m_activate_var = tk.StringVar(value="IKZ Ein (M7)")
        self.m_activate_combo = ttk.Combobox(
            frame,
            textvariable=self.m_activate_var,
            values=["IKZ Ein (M7)", "IKZ Ein (M8)", "Innenluft Ein (M89)", "Freitext / Eigener M-Befehl"],
            state="readonly",
            width=28,
        )
        self.m_activate_combo.grid(row=0, column=1, sticky=tk.W, pady=2)
        self.m_activate_combo.bind("<<ComboboxSelected>>", self.on_m_activate_change)

        self.m_activate_custom = ttk.Entry(frame, width=12, state="disabled")
        self.m_activate_custom.insert(0, "M107")
        self.m_activate_custom.grid(row=0, column=2, sticky=tk.W, pady=2, padx=5)

        ttk.Label(frame, text="Deaktivierung BSF-Messer:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.m_deactivate_var = tk.StringVar(value="Alles AUS (M9)")
        self.m_deactivate_combo = ttk.Combobox(
            frame,
            textvariable=self.m_deactivate_var,
            values=["Alles AUS (M9)", "Eigener M-Befehl"],
            state="readonly",
            width=28,
        )
        self.m_deactivate_combo.grid(row=1, column=1, sticky=tk.W, pady=2)
        self.m_deactivate_combo.bind("<<ComboboxSelected>>", self.on_m_deactivate_change)

        self.m_deactivate_custom = ttk.Entry(frame, width=12, state="disabled")
        self.m_deactivate_custom.insert(0, "M9")
        self.m_deactivate_custom.grid(row=1, column=2, sticky=tk.W, pady=2, padx=5)

    def create_positioning_panel(self) -> None:
        pos_frame = ttk.LabelFrame(self.params_host, text="Positionierung", padding=8)
        pos_frame.pack(fill=tk.X, pady=4)
        self.position_frame = pos_frame

        ttk.Label(pos_frame, text="Positionierungsart:").grid(row=0, column=0, sticky=tk.W, pady=2)

        self._position_mode_labels = {
            "Teilkreis": PositionMode.CIRCLE,
            "Einzelposition": PositionMode.SINGLE,
            "Koordinatenliste": PositionMode.COORDINATES,
        }
        self._position_combo_values = POSITION_LABELS_BGF
        self.position_mode_var = tk.StringVar(value="Teilkreis")
        self._position_mode_by_enum = {v: k for k, v in self._position_mode_labels.items()}

        self.position_mode_combo = ttk.Combobox(
            pos_frame,
            textvariable=self.position_mode_var,
            values=self._position_combo_values,
            state="readonly",
            width=24,
            height=5,
        )
        self.position_mode_combo.grid(row=0, column=1, sticky=tk.W, pady=2, padx=5)
        self.position_mode_combo.bind("<<ComboboxSelected>>", self.on_position_mode_change)

        # --- Teilkreis ---
        self.circle_frame = ttk.LabelFrame(pos_frame, text="Teilkreis", padding=6)
        circle_fields = [
            (0, 0, "Teilkreis-Durchmesser (mm):", "diameter", "715"),
            (0, 2, "Anzahl Positionen:", "count", "24"),
            (0, 4, "Startwinkel (Grad):", "start_angle", "15"),
            (1, 0, "Mitte X:", "center_x", "0"),
            (1, 2, "Mitte Y:", "center_y", "0"),
        ]
        for row, col, label, key, default in circle_fields:
            ttk.Label(self.circle_frame, text=label).grid(row=row, column=col, sticky=tk.W, pady=2, padx=(0, 4))
            entry = ttk.Entry(self.circle_frame, width=12)
            entry.insert(0, default)
            entry.grid(row=row, column=col + 1, sticky=tk.W, pady=2, padx=(0, 12))
            self.entries[key] = entry

        self._circle_surface_z_label = ttk.Label(self.circle_frame, text="Bohrungsanfang Z [mm]:")
        self._circle_surface_z_label.grid(row=1, column=4, sticky=tk.W, pady=2, padx=(0, 4))
        self.entries["circle_surface_z"] = ttk.Entry(self.circle_frame, width=12)
        self.entries["circle_surface_z"].insert(0, "0")
        self.entries["circle_surface_z"].grid(row=1, column=5, sticky=tk.W, pady=2, padx=(0, 12))
        self.entries["circle_surface_z"].bind("<KeyRelease>", self.on_bgf_depth_input_change)
        self.entries["circle_surface_z"].bind("<FocusOut>", self.on_bgf_depth_input_change)

        # --- Einzelposition ---
        self.single_pos_frame = ttk.LabelFrame(pos_frame, text="Einzelposition", padding=6)
        ttk.Label(self.single_pos_frame, text="X:").grid(row=0, column=0, sticky=tk.W)
        self.entries["single_x"] = ttk.Entry(self.single_pos_frame, width=12)
        self.entries["single_x"].insert(0, "0")
        self.entries["single_x"].grid(row=0, column=1, sticky=tk.W, padx=(4, 12))
        ttk.Label(self.single_pos_frame, text="Y:").grid(row=0, column=2, sticky=tk.W)
        self.entries["single_y"] = ttk.Entry(self.single_pos_frame, width=12)
        self.entries["single_y"].insert(0, "0")
        self.entries["single_y"].grid(row=0, column=3, sticky=tk.W, padx=(4, 12))

        self._single_surface_z_label = ttk.Label(self.single_pos_frame, text="Bohrungsanfang Z [mm]:")
        self._single_surface_z_label.grid(row=0, column=4, sticky=tk.W)
        self.entries["single_surface_z"] = ttk.Entry(self.single_pos_frame, width=12)
        self.entries["single_surface_z"].insert(0, "0")
        self.entries["single_surface_z"].grid(row=0, column=5, sticky=tk.W, padx=4)
        self.entries["single_surface_z"].bind("<KeyRelease>", self.on_bgf_depth_input_change)
        self.entries["single_surface_z"].bind("<FocusOut>", self.on_bgf_depth_input_change)

        self.bgf_nutzlaenge_label = ttk.Label(self.single_pos_frame, text="")
        self.bgf_nutzlaenge_label.grid(row=1, column=0, columnspan=6, sticky=tk.W, pady=(4, 0))

        # --- Koordinatenliste (BGF / BSF, getrennte Daten und schlankeres BSF-UI) ---
        self.coord_list_frame = ttk.LabelFrame(pos_frame, text="Koordinatenliste (BGF)", padding=6)

        self.bgf_coord_inner = ttk.Frame(self.coord_list_frame)
        tree_wrap = ttk.Frame(self.bgf_coord_inner)
        tree_wrap.pack(fill=tk.X, pady=(4, 2))

        columns = ("nr", "x", "y", "sz", "td", "ch", "status")
        self.coord_tree = ttk.Treeview(
            tree_wrap,
            columns=columns,
            show="headings",
            height=6,
            selectmode="browse",
        )
        headings = {
            "nr": ("Nr.", 36),
            "x": ("X", 70),
            "y": ("Y", 70),
            "sz": ("Bohrungsanfang Z", 110),
            "td": ("Gewindetiefe", 90),
            "ch": ("Kernloch Soll", 90),
            "status": ("Status", 160),
        }
        for key, (title, width) in headings.items():
            self.coord_tree.heading(key, text=title)
            self.coord_tree.column(
                key, width=width, anchor=tk.CENTER if key == "nr" else tk.E, stretch=(key == "status")
            )

        scroll = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=self.coord_tree.yview)
        self.coord_tree.configure(yscrollcommand=scroll.set)
        self.coord_tree.pack(side=tk.LEFT, fill=tk.X, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        btn_row = ttk.Frame(self.bgf_coord_inner)
        btn_row.pack(fill=tk.X, pady=2)
        ttk.Button(btn_row, text="+ Position", command=self.coord_add_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Bearbeiten", command=self.coord_edit_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Loeschen", command=self.coord_delete_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Koordinaten einfuegen", command=self.coord_paste_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row, text="Liste leeren", command=self.coord_clear_rows).pack(side=tk.LEFT, padx=2)

        file_row = ttk.Frame(self.bgf_coord_inner)
        file_row.pack(fill=tk.X, pady=(2, 0))
        ttk.Button(file_row, text="Liste speichern", command=self.coord_save_list).pack(side=tk.LEFT, padx=2)
        ttk.Button(file_row, text="Liste laden", command=self.coord_load_list).pack(side=tk.LEFT, padx=2)
        ttk.Button(file_row, text="CSV importieren", command=self.coord_import_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(file_row, text="CSV exportieren", command=self.coord_export_csv).pack(side=tk.LEFT, padx=2)

        self.bsf_coord_inner = ttk.Frame(self.coord_list_frame)
        bsf_tree_wrap = ttk.Frame(self.bsf_coord_inner)
        bsf_tree_wrap.pack(fill=tk.X, pady=(4, 2))
        bsf_columns = ("nr", "x", "y", "status")
        self.bsf_coord_tree = ttk.Treeview(
            bsf_tree_wrap,
            columns=bsf_columns,
            show="headings",
            height=6,
            selectmode="browse",
        )
        bsf_headings = {
            "nr": ("Nr.", 36),
            "x": ("X", 90),
            "y": ("Y", 90),
            "status": ("Status", 180),
        }
        for key, (title, width) in bsf_headings.items():
            self.bsf_coord_tree.heading(key, text=title)
            self.bsf_coord_tree.column(
                key, width=width, anchor=tk.CENTER if key == "nr" else tk.E, stretch=(key == "status")
            )
        bsf_scroll = ttk.Scrollbar(bsf_tree_wrap, orient=tk.VERTICAL, command=self.bsf_coord_tree.yview)
        self.bsf_coord_tree.configure(yscrollcommand=bsf_scroll.set)
        self.bsf_coord_tree.pack(side=tk.LEFT, fill=tk.X, expand=True)
        bsf_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        bsf_btn_row = ttk.Frame(self.bsf_coord_inner)
        bsf_btn_row.pack(fill=tk.X, pady=2)
        ttk.Label(bsf_btn_row, text="Positionen:").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bsf_btn_row, text="+ Position", command=self.bsf_coord_add_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(bsf_btn_row, text="Bearbeiten", command=self.bsf_coord_edit_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(bsf_btn_row, text="Loeschen", command=self.bsf_coord_delete_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(bsf_btn_row, text="Koordinaten einfuegen", command=self.bsf_coord_paste_dialog).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(bsf_btn_row, text="Liste leeren", command=self.bsf_coord_clear_rows).pack(side=tk.LEFT, padx=2)

        bsf_file_row = ttk.Frame(self.bsf_coord_inner)
        bsf_file_row.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(bsf_file_row, text="Datei:").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bsf_file_row, text="Liste speichern", command=self.bsf_coord_save_list).pack(side=tk.LEFT, padx=2)
        ttk.Button(bsf_file_row, text="Liste laden", command=self.bsf_coord_load_list).pack(side=tk.LEFT, padx=2)
        ttk.Button(bsf_file_row, text="CSV importieren", command=self.bsf_coord_import_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(bsf_file_row, text="CSV exportieren", command=self.bsf_coord_export_csv).pack(side=tk.LEFT, padx=2)

    def create_common_parameters(self) -> None:
        frame = ttk.LabelFrame(self.params_host, text="Werkstueck / Sicherheit / Programm", padding=8)
        frame.pack(fill=tk.X, pady=4)
        self.common_frame = frame

        fields = [
            (0, 0, "Werkzeugnummer T:", "tool_num", "8"),
            (0, 2, "Rohteil-Kantenlaenge (mm):", "blank_size", "1000"),
            (0, 4, "Rohteil-Hoehe Z (mm):", "blank_height", "60"),
            (1, 0, "Rohteil-Oberkante Z [mm]:", "raw_stock_top_z", "0.000"),
            (1, 2, "Sicherheits-Z zwischen Positionen:", "safe_z", "100"),
            (1, 4, "End-Sicherheits-Z:", "end_safe_z", "200"),
            (2, 0, "Programmname:", "program_name", "BGF_TK"),
            (2, 2, "Programmierer:", "programmer", ""),
        ]
        for row, col, label, key, default in fields:
            ttk.Label(frame, text=label).grid(row=row, column=col, sticky=tk.W, pady=2, padx=(0, 4))
            if key == "tool_num":
                entry = ttk.Entry(frame, width=12, textvariable=self._tool_num_var)
            elif key == "programmer":
                entry = ttk.Entry(frame, width=18, textvariable=self.programmer_var)
            else:
                entry = ttk.Entry(frame, width=18 if key == "program_name" else 12)
                entry.insert(0, default)
            entry.grid(row=row, column=col + 1, sticky=tk.W, pady=2, padx=(0, 16))
            self.entries[key] = entry

        # Alias: frueheres practice_frame / input_frame
        self.practice_frame = frame
        self.input_frame = frame

    def create_buttons(self) -> None:
        button_frame = ttk.Frame(self.top_pane)
        button_frame.pack(fill=tk.X, pady=6)

        ttk.Button(button_frame, text="NC-Code generieren", command=self.generate_code).pack(side=tk.LEFT, padx=3)
        ttk.Button(button_frame, text="In Zwischenablage kopieren", command=self.copy_to_clipboard).pack(side=tk.LEFT, padx=3)
        ttk.Button(button_frame, text="Als *.H exportieren", command=self.export_to_h).pack(side=tk.LEFT, padx=3)
        ttk.Button(button_frame, text="NC-Code drucken", command=self.print_code).pack(side=tk.LEFT, padx=3)
        ttk.Button(button_frame, text="Positionsvorschau", command=self.open_bgf_positions_preview).pack(
            side=tk.LEFT, padx=3
        )

    def create_output_field(self) -> None:
        output_frame = ttk.LabelFrame(self.bottom_pane, text="Generierter iTNC 530 Klartext-Code", padding=10)
        output_frame.pack(fill=tk.BOTH, expand=True, pady=2)

        self._nc_status_label = tk.Label(
            output_frame,
            text="Kein NC-Code erzeugt",
            anchor=tk.W,
            bg=self.bg_color,
            fg="#7f8c8d",
            font=("Segoe UI", 9, "bold"),
        )
        self._nc_status_label.pack(fill=tk.X, pady=(0, 6))

        scrollbar_y = ttk.Scrollbar(output_frame, orient=tk.VERTICAL)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        scrollbar_x = ttk.Scrollbar(output_frame, orient=tk.HORIZONTAL)
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.output_text = tk.Text(
            output_frame,
            wrap=tk.NONE,
            font=("Consolas", 10),
            yscrollcommand=scrollbar_y.set,
            xscrollcommand=scrollbar_x.set,
            bg="#2c3e50",
            fg="#ecf0f1",
            insertbackground="white",
            selectbackground="#3498db",
            selectforeground="white",
        )
        self.output_text.pack(fill=tk.BOTH, expand=True)
        scrollbar_y.config(command=self.output_text.yview)
        scrollbar_x.config(command=self.output_text.xview)

    def _install_nc_state_watchers(self) -> None:
        def _on_change(event=None):
            self.refresh_nc_output_status()

        for widget in list(self.entries.values()):
            widget.bind("<KeyRelease>", _on_change, add="+")
            widget.bind("<FocusOut>", _on_change, add="+")
        for extra in (self.m_activate_custom, self.m_deactivate_custom):
            extra.bind("<KeyRelease>", _on_change, add="+")
            extra.bind("<FocusOut>", _on_change, add="+")
        for var in (
            self.mode_var,
            self.position_mode_var,
            self.programmer_var,
            self._tool_num_var,
            self.bgf_size_var,
            self.output_tool_def_var,
            self.bsf_tool_profile_var,
            self.z0_var,
            self.reduce_approach_var,
            self.m_activate_var,
            self.m_deactivate_var,
        ):
            var.trace_add("write", lambda *_args: self.refresh_nc_output_status())

    def refresh_nc_output_status(self, event=None) -> None:
        label = getattr(self, "_nc_status_label", None)
        if label is None:
            return
        output = ""
        if getattr(self, "output_text", None) is not None:
            output = self.output_text.get("1.0", tk.END)
        text = self.nc_guard.status_text(self, output_text=output)
        label.config(text=text)
        if text == STATUS_CURRENT_TEXT:
            label.config(fg="#1e8449")
        elif text == STATUS_STALE_TEXT:
            label.config(fg="#c0392b")
        else:
            label.config(fg="#7f8c8d")

    def _require_current_nc_for_output(self) -> Optional[str]:
        code = self.output_text.get("1.0", tk.END).strip()
        if not code:
            messagebox.showwarning("Warnung", "Kein NC-Code vorhanden.")
            return None
        if not self.nc_guard.is_current(self, output_text=code):
            messagebox.showerror("NC-Code veraltet", STALE_ACTION_MESSAGE)
            return None
        return code

    def open_bgf_positions_preview(self) -> None:
        """Oeffnet read-only XY-Positionsvorschau (BGF und BSF)."""
        from preview.bgf_preview_window import open_bgf_preview

        existing = getattr(self, "_bgf_preview_window", None)
        if existing is not None:
            try:
                if existing.win.winfo_exists():
                    existing.refresh()
                    existing.win.lift()
                    existing.win.focus_force()
                    return
            except tk.TclError:
                pass

        self._bgf_preview_window = open_bgf_preview(
            self.root,
            snapshot_provider=self.build_preview_snapshot,
        )

    def open_bsf_geometry_help(self) -> None:
        """Oeffnet read-only HEULE-BSF-Senkgeometrie in einem Toplevel."""
        from help_views.bsf_geometry_help import open_bsf_geometry_help_window

        existing = getattr(self, "_bsf_help_window", None)
        if existing is not None:
            try:
                if existing.win.winfo_exists():
                    existing.refresh()
                    existing.win.lift()
                    existing.win.focus_force()
                    return
            except tk.TclError:
                pass

        self._bsf_help_window = open_bsf_geometry_help_window(
            self.root,
            snapshot_provider=self.build_bsf_geometry_help_snapshot,
        )

    def open_bgf_geometry_help(self) -> None:
        """Oeffnet read-only CERATIZIT-BGF-Gewindegeometrie in einem Toplevel."""
        from help_views.bgf_geometry_help import open_bgf_geometry_help_window

        existing = getattr(self, "_bgf_help_window", None)
        if existing is not None:
            try:
                if existing.win.winfo_exists():
                    existing.refresh()
                    existing.win.lift()
                    existing.win.focus_force()
                    return
            except tk.TclError:
                pass

        self._bgf_help_window = open_bgf_geometry_help_window(
            self.root,
            source_provider=self.collect_bgf_help_source,
        )

    def collect_bgf_help_source(self):
        """Read-only Quelle fuer die BGF-Hilfsgrafik. Keine Dialoge, keine NC-Aenderung."""
        from help_views.bgf_geometry_model import (
            BGFHelpPositionView,
            BGFHelpSource,
            BGFHelpToolView,
            parse_help_mm,
        )

        data = BGF_DATA[self.bgf_size_var.get()]
        policy = self.get_bgf_depth_policy()
        tool = BGFHelpToolView(
            size=data.size,
            article_no=data.article_no,
            radius=data.radius,
            pitch=data.pitch,
            predrill_depth=data.predrill_depth,
        )
        clearance = parse_help_mm(self.entries["approach_clearance"].get()) if "approach_clearance" in self.entries else None

        def _silent_float(key: str) -> Optional[float]:
            if key not in self.entries:
                return None
            return parse_help_mm(self.entries[key].get())

        def _silent_int(key: str) -> Optional[int]:
            value = _silent_float(key)
            if value is None:
                return None
            return int(value)

        mode = self.get_position_mode()
        circle_diameter = None
        circle_count = None
        positions: List[BGFHelpPositionView] = []
        initial_index = 0
        mode_label = self.position_mode_var.get() if hasattr(self, "position_mode_var") else "Teilkreis"

        if mode == PositionMode.COORDINATES:
            mode_label = "Koordinatenliste"
            positions = [
                BGFHelpPositionView(
                    x=pos.x,
                    y=pos.y,
                    surface_z=pos.surface_z,
                    thread_depth=pos.thread_depth,
                    core_hole_depth=pos.core_hole_depth,
                )
                for pos in self.coord_rows
            ]
            selected = ()
            if hasattr(self, "coord_tree"):
                try:
                    selected = self.coord_tree.selection()
                except tk.TclError:
                    selected = ()
            if selected:
                try:
                    initial_index = int(selected[0])
                except (TypeError, ValueError):
                    initial_index = 0
                if initial_index < 0 or initial_index >= len(positions):
                    initial_index = 0
        elif mode == PositionMode.SINGLE:
            mode_label = "Einzelposition"
            ok_td, thread_depth = self.parse_thread_depth_input()
            ok_ch, core_hole = self.parse_optional_core_hole_depth()
            positions = [
                BGFHelpPositionView(
                    x=_silent_float("single_x"),
                    y=_silent_float("single_y"),
                    surface_z=_silent_float("single_surface_z"),
                    thread_depth=thread_depth if ok_td else None,
                    core_hole_depth=core_hole if ok_ch else None,
                )
            ]
        else:
            mode_label = "Teilkreis"
            ok_td, thread_depth = self.parse_thread_depth_input()
            ok_ch, core_hole = self.parse_optional_core_hole_depth()
            circle_diameter = _silent_float("diameter")
            circle_count = _silent_int("count")
            positions = [
                BGFHelpPositionView(
                    x=_silent_float("center_x"),
                    y=_silent_float("center_y"),
                    surface_z=_silent_float("circle_surface_z"),
                    thread_depth=thread_depth if ok_td else None,
                    core_hole_depth=core_hole if ok_ch else None,
                )
            ]

        return BGFHelpSource(
            tool=tool,
            policy=policy,
            approach_clearance=clearance,
            mode=mode_label,
            positions=tuple(positions),
            initial_index=initial_index,
            circle_diameter=circle_diameter,
            circle_count=circle_count,
        )

    def build_bsf_geometry_help_snapshot(self):
        from help_views.bsf_geometry_model import build_bsf_geometry_help_snapshot

        return build_bsf_geometry_help_snapshot(
            bund_text=self.entries["bund_thickness"].get() if "bund_thickness" in self.entries else "",
            sink_text=self.entries["sink_depth"].get() if "sink_depth" in self.entries else "",
            clearance_text=self.entries["clearance"].get() if "clearance" in self.entries else "",
            z0_label=self.z0_var.get(),
            reference_z_text=self.entries["bsf_reference_z"].get() if "bsf_reference_z" in self.entries else "0",
            tool_designation=self.bsf_tool_profile_var.get() if hasattr(self, "bsf_tool_profile_var") else "",
        )

    def build_preview_snapshot(self):
        if self.is_bgf_mode():
            return self.build_bgf_preview_snapshot()
        return self.build_bsf_preview_snapshot()

    def build_bsf_preview_snapshot(self):
        """Snapshot fuer HEULE BSF – aendert keine Projekt-/NC-Daten."""
        from preview.bgf_preview_model import PreviewSnapshot, build_bsf_preview_from_xy
        from coordinates.circle_positions import compute_circle_xy_positions

        def _silent_float(key: str) -> Optional[float]:
            try:
                return float(self.entries[key].get().replace(",", "."))
            except (KeyError, ValueError):
                return None

        def _silent_int(key: str) -> Optional[int]:
            try:
                return int(float(self.entries[key].get().replace(",", ".")))
            except (KeyError, ValueError):
                return None

        program_name = clean_program_name(self.entries["program_name"].get(), "BSF_RUECKWAERTS")
        tool_num = _silent_int("tool_num") or 0
        safe_z = _silent_float("safe_z")
        end_safe_z = _silent_float("end_safe_z")
        if safe_z is None or end_safe_z is None:
            safe_z = 0.0
            end_safe_z = 0.0

        bund = _silent_float("bund_thickness")
        sink = _silent_float("sink_depth")
        clearance = _silent_float("clearance")
        reference_z = _silent_float("bsf_reference_z")
        tool_profile = self.get_selected_bsf_tool_profile(show_error=False)
        tool_ok = tool_profile is not None

        mode = self.get_position_mode()
        mode_label = self.position_mode_var.get()
        positions: List[BSFCoordinatePosition] = []
        circle_info = None

        if mode == PositionMode.COORDINATES:
            positions = list(self.bsf_coord_rows)
            mode_label = "Koordinatenliste"
        elif mode == PositionMode.SINGLE:
            mode_label = "Einzelposition"
            sx = _silent_float("single_x")
            sy = _silent_float("single_y")
            if None not in (sx, sy):
                positions = [BSFCoordinatePosition(x=sx, y=sy)]
        else:
            mode_label = "Teilkreis"
            diameter = _silent_float("diameter")
            count = _silent_int("count")
            start_angle = _silent_float("start_angle")
            center_x = _silent_float("center_x")
            center_y = _silent_float("center_y")
            if (
                None not in (diameter, count, start_angle, center_x, center_y)
                and diameter > 0
                and count > 0
            ):
                xy = compute_circle_xy_positions(
                    center_x=center_x,
                    center_y=center_y,
                    diameter=diameter,
                    count=count,
                    start_angle_deg=start_angle,
                )
                positions = [BSFCoordinatePosition(x=x, y=y) for x, y in xy]
                circle_info = (
                    f"Ø{diameter:g}  {count} Positionen  Start {start_angle:g}°  "
                    f"Mitte X{center_x:g}/Y{center_y:g}"
                )

        list_ok = True
        if mode == PositionMode.COORDINATES and not positions:
            list_ok = False
        nc_allowed = bool(tool_ok and list_ok and positions)

        if not positions:
            return PreviewSnapshot(
                mode_label=mode_label,
                thread_size="BSF",
                article_no="",
                tool_radius=0.0,
                tool_number=tool_num,
                program_name=program_name,
                approach_clearance=0.0,
                safe_z=safe_z,
                end_safe_z=end_safe_z,
                process_kind="BSF",
                bsf_bund_thickness=bund,
                bsf_sink_depth=sink,
                bsf_clearance=clearance,
                bsf_tool_designation=tool_profile.designation if tool_profile is not None else "",
                bsf_measurement_face_to_edge_mm=tool_profile.measurement_face_to_cutting_edge_mm if tool_profile is not None else None,
                bsf_reference_z=reference_z,
                circle_info=circle_info,
                nc_allowed=False,
            )

        return build_bsf_preview_from_xy(
            positions,
            nc_allowed=nc_allowed,
            mode_label=mode_label,
            tool_number=tool_num,
            program_name=program_name,
            safe_z=safe_z,
            end_safe_z=end_safe_z,
            bund_thickness=bund,
            sink_depth=sink,
            clearance=clearance,
            tool_designation=tool_profile.designation if tool_profile is not None else "",
            measurement_face_to_edge_mm=tool_profile.measurement_face_to_cutting_edge_mm if tool_profile is not None else None,
            circle_info=circle_info,
            reference_z=reference_z,
        )

    def build_bgf_preview_snapshot(self):
        """Snapshot aus aktuellem GUI-Stand – aendert keine Projekt-/NC-Daten."""
        from preview.bgf_preview_model import (
            PreviewSnapshot,
            build_circle_positions_for_preview,
            build_preview_from_positions,
        )

        def _silent_float(key: str) -> Optional[float]:
            try:
                return float(self.entries[key].get().replace(",", "."))
            except (KeyError, ValueError):
                return None

        def _silent_int(key: str) -> Optional[int]:
            try:
                return int(float(self.entries[key].get().replace(",", ".")))
            except (KeyError, ValueError):
                return None

        data = BGF_DATA[self.bgf_size_var.get()]
        policy = self.get_bgf_depth_policy()
        mode = self.get_position_mode()
        program_name = clean_program_name(self.entries["program_name"].get(), "BGF_TK")
        tool_num = _silent_int("tool_num") or 0

        clearance = self.get_approach_clearance()
        if clearance is None:
            clearance = DEFAULT_APPROACH_CLEARANCE

        safe_z = _silent_float("safe_z")
        end_safe_z = _silent_float("end_safe_z")
        if safe_z is None or end_safe_z is None:
            return PreviewSnapshot(
                mode_label=self.position_mode_var.get(),
                thread_size=data.size,
                article_no=data.article_no,
                tool_radius=data.radius,
                tool_number=tool_num,
                program_name=program_name,
                approach_clearance=clearance,
                safe_z=0.0,
                end_safe_z=0.0,
            )

        circle_info = None
        positions: List[BGFCoordinatePosition] = []
        mode_label = self.position_mode_var.get()

        if mode == PositionMode.COORDINATES:
            positions = list(self.coord_rows)
            mode_label = "Koordinatenliste"
        elif mode == PositionMode.SINGLE:
            mode_label = "Einzelposition"
            ok_td, thread_depth = self.parse_thread_depth_input()
            ok_ch, core_hole = self.parse_optional_core_hole_depth()
            sx = _silent_float("single_x")
            sy = _silent_float("single_y")
            sz = _silent_float("single_surface_z")
            if ok_td and None not in (sx, sy, sz):
                positions = [
                    BGFCoordinatePosition(
                        x=sx,
                        y=sy,
                        surface_z=sz,
                        thread_depth=thread_depth,
                        core_hole_depth=core_hole if ok_ch else None,
                    )
                ]
        else:
            mode_label = "Teilkreis"
            diameter = _silent_float("diameter")
            count = _silent_int("count")
            start_angle = _silent_float("start_angle")
            center_x = _silent_float("center_x")
            center_y = _silent_float("center_y")
            ok_td, thread_depth = self.parse_thread_depth_input()
            ok_ch, core_hole = self.parse_optional_core_hole_depth()
            if (
                ok_td
                and None not in (diameter, count, start_angle, center_x, center_y)
                and diameter > 0
                and count > 0
            ):
                circle_sz = _silent_float("circle_surface_z")
                if circle_sz is None:
                    circle_sz = 0.0
                positions = build_circle_positions_for_preview(
                    center_x=center_x,
                    center_y=center_y,
                    diameter=diameter,
                    count=count,
                    start_angle_deg=start_angle,
                    thread_depth=thread_depth,
                    core_hole_depth=core_hole if ok_ch else None,
                    surface_z=circle_sz,
                )
                circle_info = (
                    f"Ø{diameter:g}  {count} Positionen  Start {start_angle:g}°  "
                    f"Mitte X{center_x:g}/Y{center_y:g}"
                )

        if not positions:
            return PreviewSnapshot(
                mode_label=mode_label,
                thread_size=data.size,
                article_no=data.article_no,
                tool_radius=data.radius,
                tool_number=tool_num,
                program_name=program_name,
                approach_clearance=clearance,
                safe_z=safe_z,
                end_safe_z=end_safe_z,
                circle_info=circle_info,
            )

        return build_preview_from_positions(
            positions,
            policy=policy,
            safe_z=safe_z,
            end_safe_z=end_safe_z,
            approach_clearance=clearance,
            mode_label=mode_label,
            thread_size=data.size,
            article_no=data.article_no,
            tool_radius=data.radius,
            tool_number=tool_num,
            program_name=program_name,
            circle_info=circle_info,
        )

    # ------------------------------------------------------------------
    # GUI Events
    # ------------------------------------------------------------------

    def is_bgf_mode(self) -> bool:
        return self.mode_var.get() == MODE_BGF

    def on_mode_change(self, event) -> None:
        is_bgf = self.is_bgf_mode()

        # Alle wechselnden Panels aus dem Layout nehmen, dann in fester Reihenfolge einpacken
        for frame in (
            self.bgf_tool_frame,
            self.bgf_processing_frame,
            self.bsf_tool_frame,
            self.bsf_processing_frame,
            self.bsf_machine_frame,
            self.position_frame,
            self.common_frame,
        ):
            hide_pack(frame)

        if is_bgf:
            show_pack(self.bgf_tool_frame, fill=tk.X, pady=4)
            show_pack(self.position_frame, fill=tk.X, pady=4)
            show_pack(self.bgf_processing_frame, fill=tk.X, pady=4)
            self._set_position_combo_values(POSITION_LABELS_BGF)
            if self.entries.get("program_name"):
                current = self.entries["program_name"].get().strip()
                if current in ("", "BSF_RUECKWAERTS"):
                    self.entries["program_name"].delete(0, tk.END)
                    self.entries["program_name"].insert(0, "BGF_TK")
        else:
            show_pack(self.bsf_tool_frame, fill=tk.X, pady=4)
            show_pack(self.position_frame, fill=tk.X, pady=4)
            show_pack(self.bsf_processing_frame, fill=tk.X, pady=4)
            show_pack(self.bsf_machine_frame, fill=tk.X, pady=4)
            self._set_position_combo_values(POSITION_LABELS_BSF)
            if self.entries.get("program_name"):
                current = self.entries["program_name"].get().strip()
                if current in ("", "BGF_TK"):
                    self.entries["program_name"].delete(0, tk.END)
                    self.entries["program_name"].insert(0, "BSF_RUECKWAERTS")

        show_pack(self.common_frame, fill=tk.X, pady=4)

        self.update_bgf_nutzlaenge_info()
        self.on_position_mode_change(None)
        self.refresh_nc_output_status()

    def _set_position_combo_values(self, values: tuple) -> None:
        self._position_combo_values = values
        self.position_mode_combo["values"] = values
        current = self.position_mode_var.get()
        if current not in values:
            self.position_mode_var.set(values[0])

    def get_position_mode(self) -> PositionMode:
        label = self.position_mode_var.get()
        return self._position_mode_labels.get(label, PositionMode.CIRCLE)

    def on_position_mode_change(self, event) -> None:
        mode = self.get_position_mode()
        hide_grid(self.circle_frame)
        hide_grid(self.single_pos_frame)
        hide_grid(self.coord_list_frame)

        # Kreis-Entries immer beschreibbar halten (Werte erhalten); Panel steuert Sichtbarkeit
        for key in self._circle_entry_keys:
            if key in self.entries:
                self.entries[key].configure(state="normal")

        if mode == PositionMode.CIRCLE:
            show_grid(self.circle_frame, row=1, column=0, columnspan=6, sticky=tk.EW, pady=(8, 0))
            if self.is_bgf_mode():
                self._circle_surface_z_label.grid(row=1, column=4, sticky=tk.W, pady=2, padx=(0, 4))
                self.entries["circle_surface_z"].grid(row=1, column=5, sticky=tk.W, pady=2, padx=(0, 12))
            else:
                self._circle_surface_z_label.grid_forget()
                self.entries["circle_surface_z"].grid_forget()
        elif mode == PositionMode.SINGLE:
            show_grid(self.single_pos_frame, row=1, column=0, columnspan=6, sticky=tk.EW, pady=(8, 0))
            for key in ("single_x", "single_y", "single_surface_z"):
                self.entries[key].configure(state="normal")
            if self.is_bgf_mode():
                self._single_surface_z_label.grid(row=0, column=4, sticky=tk.W)
                self.entries["single_surface_z"].grid(row=0, column=5, sticky=tk.W, padx=4)
                self.bgf_nutzlaenge_label.grid(row=1, column=0, columnspan=6, sticky=tk.W, pady=(4, 0))
            else:
                self._single_surface_z_label.grid_forget()
                self.entries["single_surface_z"].grid_forget()
                self.bgf_nutzlaenge_label.grid_forget()
            self.update_bgf_nutzlaenge_info()
        elif mode == PositionMode.COORDINATES:
            show_grid(self.coord_list_frame, row=1, column=0, columnspan=6, sticky=tk.EW, pady=(8, 0))
            self.position_frame.columnconfigure(0, weight=1)
            self._show_coord_list_for_mode()
        self.refresh_nc_output_status()

    def _show_coord_list_for_mode(self) -> None:
        hide_pack(self.bgf_coord_inner)
        hide_pack(self.bsf_coord_inner)
        if self.is_bgf_mode():
            self.coord_list_frame.configure(text="Koordinatenliste (BGF)")
            show_pack(self.bgf_coord_inner, fill=tk.X)
            self._refresh_coord_tree()
        else:
            self.coord_list_frame.configure(text="Koordinatenliste (BSF)")
            show_pack(self.bsf_coord_inner, fill=tk.X)
            self._refresh_bsf_coord_tree()

    def _default_template_thread_depth(self) -> float:
        return float(BGF_DATA[self.bgf_size_var.get()].thread_length)

    def _position_status_label(self, pos: BGFCoordinatePosition) -> str:
        policy = self.get_bgf_depth_policy()
        ev = evaluate_bgf_depth(
            BGFDepthRequest(pos.thread_depth, pos.core_hole_depth),
            policy,
            surface_z=pos.surface_z,
        )
        return status_label_for(ev.status)

    def _refresh_coord_tree(self) -> None:
        for item in self.coord_tree.get_children():
            self.coord_tree.delete(item)
        for idx, pos in enumerate(self.coord_rows, start=1):
            core_txt = "" if pos.core_hole_depth is None else f"{pos.core_hole_depth:g}"
            self.coord_tree.insert(
                "",
                tk.END,
                iid=str(idx - 1),
                values=(
                    idx,
                    f"{pos.x:g}",
                    f"{pos.y:g}",
                    f"{pos.surface_z:g}",
                    f"{pos.thread_depth:g}",
                    core_txt,
                    self._position_status_label(pos),
                ),
            )
        self.refresh_nc_output_status()

    def coord_add_row(self) -> None:
        if self.mode_var.get() != "Bohrgewindefraesen (BGF)":
            messagebox.showwarning("Hinweis", "Koordinatenliste ist derzeit nur fuer BGF verfuegbar.")
            return
        dialog = _BGFPositionDialog(
            self.root,
            title="Position hinzufuegen",
            default_thread_depth=self._default_template_thread_depth(),
        )
        if dialog.result is None:
            return
        self.coord_rows.append(dialog.result)
        self._refresh_coord_tree()

    def coord_edit_row(self) -> None:
        selected = self.coord_tree.selection()
        if not selected:
            messagebox.showwarning("Hinweis", "Bitte eine Zeile auswaehlen.")
            return
        index = int(selected[0])
        current = self.coord_rows[index]
        dialog = _BGFPositionDialog(
            self.root,
            title="Position bearbeiten",
            initial=current,
            default_thread_depth=self._default_template_thread_depth(),
        )
        if dialog.result is None:
            return
        self.coord_rows[index] = dialog.result
        self._refresh_coord_tree()

    def coord_delete_row(self) -> None:
        selected = self.coord_tree.selection()
        if not selected:
            messagebox.showwarning("Hinweis", "Bitte eine Zeile auswaehlen.")
            return
        index = int(selected[0])
        del self.coord_rows[index]
        self._refresh_coord_tree()

    def coord_clear_rows(self) -> None:
        if not self.coord_rows:
            return
        if messagebox.askyesno("Liste leeren", "Alle Koordinaten wirklich loeschen?"):
            self.coord_rows.clear()
            self._refresh_coord_tree()

    def coord_paste_dialog(self) -> None:
        if self.mode_var.get() != "Bohrgewindefraesen (BGF)":
            messagebox.showwarning("Hinweis", "Koordinatenliste ist derzeit nur fuer BGF verfuegbar.")
            return
        dialog = _CoordinatePasteDialog(self.root)
        if dialog.result_text is None:
            return
        try:
            parsed = parse_bgf_coordinate_text(
                dialog.result_text,
                default_thread_depth=self._default_template_thread_depth(),
            )
        except CoordinateParseError as exc:
            messagebox.showerror(
                "Importfehler",
                "Koordinatenimport abgebrochen.\n\n" + "\n".join(exc.messages),
            )
            return
        self.coord_rows.extend(parsed)
        self._refresh_coord_tree()
        messagebox.showinfo("Import", f"{len(parsed)} Position(en) hinzugefuegt.")

    def _refresh_bsf_coord_tree(self) -> None:
        for item in self.bsf_coord_tree.get_children():
            self.bsf_coord_tree.delete(item)
        for idx, pos in enumerate(self.bsf_coord_rows, start=1):
            self.bsf_coord_tree.insert(
                "",
                tk.END,
                iid=str(idx - 1),
                values=(
                    idx,
                    f"{pos.x:.3f}",
                    f"{pos.y:.3f}",
                    bsf_position_status_label(pos, self.bsf_coord_rows),
                ),
            )
        self.refresh_nc_output_status()

    def bsf_coord_add_row(self) -> None:
        dialog = _XYPositionDialog(self.root, title="Position hinzufuegen")
        if dialog.result is None:
            return
        self.bsf_coord_rows.append(dialog.result)
        self._refresh_bsf_coord_tree()

    def bsf_coord_edit_row(self) -> None:
        selected = self.bsf_coord_tree.selection()
        if not selected:
            messagebox.showwarning("Hinweis", "Bitte eine Zeile auswaehlen.")
            return
        index = int(selected[0])
        current = self.bsf_coord_rows[index]
        dialog = _XYPositionDialog(self.root, title="Position bearbeiten", initial=current)
        if dialog.result is None:
            return
        self.bsf_coord_rows[index] = dialog.result
        self._refresh_bsf_coord_tree()

    def bsf_coord_delete_row(self) -> None:
        selected = self.bsf_coord_tree.selection()
        if not selected:
            messagebox.showwarning("Hinweis", "Bitte eine Zeile auswaehlen.")
            return
        index = int(selected[0])
        del self.bsf_coord_rows[index]
        self._refresh_bsf_coord_tree()

    def bsf_coord_clear_rows(self) -> None:
        if not self.bsf_coord_rows:
            return
        if messagebox.askyesno("Liste leeren", "Alle Koordinaten wirklich loeschen?"):
            self.bsf_coord_rows.clear()
            self._refresh_bsf_coord_tree()

    def import_bsf_coordinate_text(self, text: str) -> int:
        """Atomarer XY-Import. Bei Fehler bleibt die vorhandene Liste unveraendert."""
        previous = list(self.bsf_coord_rows)
        try:
            parsed = parse_coordinate_text(text)
        except CoordinateParseError:
            self.bsf_coord_rows = previous
            raise
        self.bsf_coord_rows.extend(BSFCoordinatePosition(x=c.x, y=c.y) for c in parsed)
        self._refresh_bsf_coord_tree()
        return len(parsed)

    def bsf_coord_paste_dialog(self) -> None:
        dialog = _CoordinatePasteDialog(
            self.root,
            hint=(
                "Eine Position pro Zeile (Semikolon oder Tab):\n"
                "X;Y\n"
                "Beispiel: 100;50\n"
                "Dezimalkomma erlaubt: 100,5;50,25\n"
                "Optionaler Header: X;Y"
            ),
        )
        if dialog.result_text is None:
            return
        previous = list(self.bsf_coord_rows)
        try:
            n = self.import_bsf_coordinate_text(dialog.result_text)
        except CoordinateParseError as exc:
            self.bsf_coord_rows = previous
            messagebox.showerror(
                "Importfehler",
                "Koordinatenimport abgebrochen. Die vorhandene Liste bleibt unveraendert.\n\n"
                + "\n".join(exc.messages),
            )
            return
        messagebox.showinfo("Import", f"{n} Position(en) hinzugefuegt.")

    def _validated_bsf_coord_positions(self) -> Optional[List[BSFCoordinatePosition]]:
        if not self.bsf_coord_rows:
            messagebox.showerror(
                "Koordinatenliste",
                "Keine Positionen in der Koordinatenliste.\nNC-Code kann nicht erzeugt werden.",
            )
            return None
        result = validate_bsf_coordinate_list(self.bsf_coord_rows)
        self._refresh_bsf_coord_tree()
        if not result.ok:
            messagebox.showerror(
                "Koordinatenliste",
                "NC-Code kann nicht erzeugt werden.\n\n" + "\n".join(result.errors),
            )
            return None
        if result.warnings:
            if not messagebox.askyesno(
                "Warnung",
                "\n".join(result.warnings) + "\n\nTrotzdem fortfahren?",
            ):
                return None
        return list(self.bsf_coord_rows)

    def _bsf_coord_default_filename(self, ext: str) -> str:
        name = clean_program_name(self.entries["program_name"].get(), "BSF_LISTE")
        return f"{name}{ext}"

    def _set_entry_value(self, key: str, value: str) -> None:
        entry = self.entries[key]
        entry.delete(0, tk.END)
        entry.insert(0, value)

    def _collect_bsf_position_list_document(self):
        if not self.bsf_coord_rows:
            raise BSFDocumentError("Keine Bearbeitungspositionen vorhanden.")

        def _entry_float(key: str, caption: str) -> float:
            raw = self.entries[key].get().strip()
            try:
                value = float(raw.replace(",", "."))
            except ValueError as exc:
                raise BSFDocumentError(f"{caption} ist keine gueltige Zahl.") from exc
            if not math.isfinite(value):
                raise BSFDocumentError(f"{caption} darf nicht NaN/Infinity sein.")
            return value

        def _entry_int(key: str, caption: str) -> int:
            if key == "tool_num":
                raw = self._tool_num_var.get().strip()
            else:
                raw = self.entries[key].get().strip()
            try:
                value = float(raw.replace(",", "."))
            except ValueError as exc:
                raise BSFDocumentError(f"{caption} ist keine ganze Zahl.") from exc
            if not math.isfinite(value) or value != int(value):
                raise BSFDocumentError(f"{caption} muss eine ganze Zahl sein.")
            return int(value)

        tool_profile = self.get_selected_bsf_tool_profile(show_error=False)
        if tool_profile is None:
            raise BSFDocumentError("HEULE_TOOL_SELECTION_REQUIRED")

        reduce_approach = bool(self.reduce_approach_var.get())
        try:
            programmer = normalize_programmer(self.programmer_var.get())
        except ProgrammerError as exc:
            raise BSFDocumentError(f"Programmierer: {exc.message}") from exc
        return build_bsf_document(
            program_name=clean_program_name(self.entries["program_name"].get(), "BSF_LISTE"),
            tool_number=_entry_int("tool_num", "Werkzeug-Nummer T"),
            blank_size=_entry_float("blank_size", "Rohteil-Kantenlaenge"),
            blank_height=_entry_float("blank_height", "Rohteil-Hoehe"),
            raw_stock_top_z=_entry_float("raw_stock_top_z", "Rohteil-Oberkante Z"),
            z_reference=z_reference_from_label(self.z0_var.get()),
            reference_z=_entry_float("bsf_reference_z", "Z-Lage Bezugsebene"),
            tool_profile_key=tool_profile.key,
            bund_thickness=_entry_float("bund_thickness", "Bund-Dicke"),
            sink_finish=_entry_float("sink_depth", "Senk-Fertigmaß"),
            clearance=_entry_float("clearance", "Freifahr-Tiefe"),
            spindle_speed=_entry_int("spindle_speed", "Spindeldrehzahl"),
            feed=_entry_float("feed_rate", "Vorschub"),
            dwell_time=_entry_float("dwell_time", "Wartezeit"),
            reduce_approach=reduce_approach,
            approach_feed_factor=(
                APPROACH_FEED_FACTOR_REDUCED if reduce_approach else APPROACH_FEED_FACTOR_FULL
            ),
            activate_preset=self.m_activate_var.get(),
            activate_custom=self.m_activate_custom.get(),
            deactivate_preset=self.m_deactivate_var.get(),
            deactivate_custom=self.m_deactivate_custom.get(),
            safe_z=_entry_float("safe_z", "Sicherheits-Z"),
            end_safe_z=_entry_float("end_safe_z", "End-Sicherheits-Z"),
            positions=self.bsf_coord_rows,
            programmer=programmer,
        )

    def _snapshot_bsf_project(self) -> dict:
        return {
            "rows": list(self.bsf_coord_rows),
            "mode": self.mode_var.get(),
            "position_mode": self.position_mode_var.get(),
            "program": self.entries["program_name"].get(),
            "programmer": self.programmer_var.get(),
            "tool": self.entries["tool_num"].get(),
            "blank_size": self.entries["blank_size"].get(),
            "blank_height": self.entries["blank_height"].get(),
            "raw_stock_top_z": self.entries["raw_stock_top_z"].get(),
            "safe_z": self.entries["safe_z"].get(),
            "end_safe_z": self.entries["end_safe_z"].get(),
            "bund": self.entries["bund_thickness"].get(),
            "sink": self.entries["sink_depth"].get(),
            "clearance": self.entries["clearance"].get(),
            "dwell": self.entries["dwell_time"].get(),
            "z0": self.z0_var.get(),
            "reference_z": self.entries["bsf_reference_z"].get() if "bsf_reference_z" in self.entries else "0",
            "tool_profile": self.bsf_tool_profile_var.get() if hasattr(self, "bsf_tool_profile_var") else "",
            "spindle": self.entries["spindle_speed"].get(),
            "feed": self.entries["feed_rate"].get(),
            "reduce": bool(self.reduce_approach_var.get()),
            "m_act": self.m_activate_var.get(),
            "m_act_custom": self.m_activate_custom.get(),
            "m_deact": self.m_deactivate_var.get(),
            "m_deact_custom": self.m_deactivate_custom.get(),
        }

    def _restore_bsf_project(self, snapshot: dict) -> None:
        self.mode_var.set(snapshot["mode"])
        self.on_mode_change(None)
        self._set_entry_value("program_name", snapshot["program"])
        self.programmer_var.set(snapshot.get("programmer", ""))
        self._set_entry_value("tool_num", snapshot["tool"])
        self._set_entry_value("blank_size", snapshot["blank_size"])
        self._set_entry_value("blank_height", snapshot["blank_height"])
        self._set_entry_value("raw_stock_top_z", snapshot.get("raw_stock_top_z", "0.000"))
        self._set_entry_value("safe_z", snapshot["safe_z"])
        self._set_entry_value("end_safe_z", snapshot["end_safe_z"])
        self._set_entry_value("bund_thickness", snapshot["bund"])
        self._set_entry_value("sink_depth", snapshot["sink"])
        self._set_entry_value("clearance", snapshot["clearance"])
        self._set_entry_value("dwell_time", snapshot["dwell"])
        self.z0_var.set(snapshot["z0"])
        self._set_entry_value("bsf_reference_z", snapshot.get("reference_z", "0"))
        self.bsf_tool_profile_var.set(snapshot.get("tool_profile", TOOL_SELECTION_REQUIRED))
        self.on_bsf_tool_profile_change()
        self._set_entry_value("spindle_speed", snapshot["spindle"])
        self._set_entry_value("feed_rate", snapshot["feed"])
        self.reduce_approach_var.set(snapshot["reduce"])
        self.m_activate_var.set(snapshot["m_act"])
        self.m_activate_custom.config(state="normal")
        self.m_activate_custom.delete(0, tk.END)
        self.m_activate_custom.insert(0, snapshot["m_act_custom"])
        self.on_m_activate_change(None)
        self.m_deactivate_var.set(snapshot["m_deact"])
        self.m_deactivate_custom.config(state="normal")
        self.m_deactivate_custom.delete(0, tk.END)
        self.m_deactivate_custom.insert(0, snapshot["m_deact_custom"])
        self.on_m_deactivate_change(None)
        self.bsf_coord_rows = list(snapshot["rows"])
        self.position_mode_var.set(snapshot["position_mode"])
        self.on_position_mode_change(None)
        self._refresh_bsf_coord_tree()

    def _apply_bsf_position_list_document(self, doc) -> None:
        """Atomar: Document ist bereits vollstaendig geparst; erst danach GUI ersetzen."""
        self.mode_var.set(MODE_BSF)
        self.on_mode_change(None)
        self._set_entry_value("program_name", doc.program_name)
        self.programmer_var.set(doc.programmer)
        self._set_entry_value("tool_num", str(doc.tool_number))
        self._set_entry_value("blank_size", f"{doc.blank_size:g}")
        self._set_entry_value("blank_height", f"{doc.blank_height:g}")
        self._set_entry_value("raw_stock_top_z", f"{doc.raw_stock_top_z:g}")
        self._set_entry_value("safe_z", f"{doc.safe_z:g}")
        self._set_entry_value("end_safe_z", f"{doc.end_safe_z:g}")
        self._set_entry_value("bund_thickness", f"{doc.bund_thickness:g}")
        self._set_entry_value("sink_depth", f"{doc.sink_finish:g}")
        self._set_entry_value("clearance", f"{doc.clearance:g}")
        self._set_entry_value("dwell_time", f"{doc.dwell_time:g}")
        self.z0_var.set(doc.z0_label)
        self._set_entry_value("bsf_reference_z", f"{doc.reference_z:g}")
        if doc.tool_profile_key:
            profile = profile_by_key(doc.tool_profile_key)
            self.bsf_tool_profile_var.set(profile.designation if profile is not None else TOOL_SELECTION_REQUIRED)
        else:
            self.bsf_tool_profile_var.set(TOOL_SELECTION_REQUIRED)
        self.on_bsf_tool_profile_change()
        self._set_entry_value("spindle_speed", str(doc.spindle_speed))
        self._set_entry_value("feed_rate", f"{doc.feed:g}")
        self.reduce_approach_var.set(bool(doc.reduce_approach))
        self.m_activate_var.set(doc.activate_preset)
        self.m_activate_custom.config(state="normal")
        self.m_activate_custom.delete(0, tk.END)
        self.m_activate_custom.insert(0, doc.activate_custom)
        self.on_m_activate_change(None)
        self.m_deactivate_var.set(doc.deactivate_preset)
        self.m_deactivate_custom.config(state="normal")
        self.m_deactivate_custom.delete(0, tk.END)
        self.m_deactivate_custom.insert(0, doc.deactivate_custom)
        self.on_m_deactivate_change(None)
        self.bsf_coord_rows = list(doc.positions)
        self.position_mode_var.set("Koordinatenliste")
        self.on_position_mode_change(None)
        self._refresh_bsf_coord_tree()

    def bsf_coord_save_list(self) -> None:
        if self.mode_var.get() != MODE_BSF:
            messagebox.showwarning("Hinweis", "HEULE-BSF-Projektdatei ist nur im BSF-Modus verfuegbar.")
            return
        try:
            doc = self._collect_bsf_position_list_document()
        except BSFDocumentError as exc:
            messagebox.showerror("Speichern", exc.message)
            return
        path = filedialog.asksaveasfilename(
            title="HEULE-BSF-Projekt speichern",
            defaultextension=".bsf.json",
            initialfile=self._bsf_coord_default_filename(".bsf.json"),
            initialdir=self._last_coord_dir,
            filetypes=[("HEULE BSF Projekt", "*.bsf.json"), ("JSON", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        try:
            save_bsf_document_json(path, doc)
        except OSError as exc:
            messagebox.showerror("Speichern", f"Datei konnte nicht geschrieben werden:\n{exc}")
            return
        self._last_coord_dir = os.path.dirname(path)
        messagebox.showinfo("Speichern", "HEULE-BSF-Projekt gespeichert.")

    def bsf_coord_load_list(self) -> None:
        if self.mode_var.get() != MODE_BSF:
            messagebox.showwarning("Hinweis", "HEULE-BSF-Projektdatei ist nur im BSF-Modus verfuegbar.")
            return
        path = filedialog.askopenfilename(
            title="HEULE-BSF-Projekt laden",
            initialdir=self._last_coord_dir,
            filetypes=[("HEULE BSF Projekt", "*.bsf.json"), ("JSON", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        try:
            doc = load_bsf_document_json(path)
        except BSFDocumentError as exc:
            messagebox.showerror("Laden", exc.message)
            return
        except OSError as exc:
            messagebox.showerror("Laden", f"Datei konnte nicht gelesen werden:\n{exc}")
            return

        if self.bsf_coord_rows:
            if not messagebox.askyesno(
                "Liste laden",
                f"Die aktuelle HEULE-BSF-Koordinatenliste enthaelt {len(self.bsf_coord_rows)} Positionen.\n\n"
                "Beim Laden wird das gesamte BSF-Projekt ersetzt\n"
                "(Prozesswerte, Schwertgeometrie, Safety, Programmname, Positionen).\n\n"
                "Fortfahren?",
            ):
                return

        snapshot = self._snapshot_bsf_project()
        try:
            self._apply_bsf_position_list_document(doc)
        except Exception as exc:
            self._restore_bsf_project(snapshot)
            messagebox.showerror("Laden", f"Projekt konnte nicht geladen werden. Stand unveraendert.\n{exc}")
            return

        self._last_coord_dir = os.path.dirname(path)
        self._refresh_bsf_coord_tree()
        preview = getattr(self, "_bgf_preview_window", None)
        if preview is not None:
            try:
                if preview.win.winfo_exists():
                    preview.refresh()
            except tk.TclError:
                pass
        help_win = getattr(self, "_bsf_help_window", None)
        if help_win is not None:
            try:
                if help_win.win.winfo_exists():
                    help_win.refresh()
            except tk.TclError:
                pass
        messagebox.showinfo(
            "Laden",
            f"{len(doc.positions)} Position(en) geladen.\nHEULE BSF Projekt: {doc.program_name}",
        )

    def bsf_coord_export_csv(self) -> None:
        if self.mode_var.get() != MODE_BSF:
            messagebox.showwarning("Hinweis", "BSF-CSV ist nur im BSF-Modus verfuegbar.")
            return
        if not self.bsf_coord_rows:
            messagebox.showwarning("CSV exportieren", "Keine Bearbeitungspositionen vorhanden.")
            return
        path = filedialog.asksaveasfilename(
            title="CSV exportieren",
            defaultextension=".csv",
            initialfile=self._bsf_coord_default_filename(".csv"),
            initialdir=self._last_coord_dir,
            filetypes=[("CSV", "*.csv"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        try:
            write_bsf_csv_file(path, self.bsf_coord_rows)
        except OSError as exc:
            messagebox.showerror("CSV exportieren", f"Datei konnte nicht geschrieben werden:\n{exc}")
            return
        self._last_coord_dir = os.path.dirname(path)
        messagebox.showinfo("CSV exportieren", f"{len(self.bsf_coord_rows)} Position(en) exportiert.")

    def bsf_coord_import_csv(self) -> None:
        if self.mode_var.get() != MODE_BSF:
            messagebox.showwarning("Hinweis", "BSF-CSV ist nur im BSF-Modus verfuegbar.")
            return
        path = filedialog.askopenfilename(
            title="CSV importieren",
            initialdir=self._last_coord_dir,
            filetypes=[("CSV", "*.csv"), ("Textdateien", "*.txt"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return

        replace: Optional[bool] = True
        if self.bsf_coord_rows:
            choice = messagebox.askyesnocancel(
                "CSV importieren",
                "Ja = aktuelle Liste ersetzen\n"
                "Nein = an aktuelle Liste anhaengen\n"
                "Abbrechen = kein Import",
            )
            if choice is None:
                return
            replace = bool(choice)

        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                text = handle.read()
            parsed = import_bsf_csv_text(text)
        except CoordinateParseError as exc:
            messagebox.showerror(
                "CSV-Import",
                "CSV-Import abgebrochen. Bestehende Liste unveraendert.\n\n"
                + "\n".join(exc.messages),
            )
            return
        except OSError as exc:
            messagebox.showerror("CSV-Import", f"Datei konnte nicht gelesen werden:\n{exc}")
            return

        if replace:
            self.bsf_coord_rows = list(parsed)
        else:
            self.bsf_coord_rows.extend(parsed)
        self._refresh_bsf_coord_tree()
        self._last_coord_dir = os.path.dirname(path)

        from coordinates.validation import find_duplicate_xy
        from coordinates.bsf_list_validation import as_xy

        dups = find_duplicate_xy(as_xy(self.bsf_coord_rows))
        msg = f"{len(parsed)} Position(en) importiert."
        if dups:
            sample = ", ".join(f"({x:g}|{y:g})" for x, y in dups[:5])
            msg += f"\n\nWarnung: Die Koordinatenliste enthaelt doppelte Positionen: {sample}"
        messagebox.showinfo("CSV-Import", msg)

    def _coord_default_filename(self, ext: str) -> str:
        name = clean_program_name(self.entries["program_name"].get(), "BGF_LISTE")
        return f"{name}{ext}"

    def _collect_position_list_document(self):
        if not self.coord_rows:
            raise BGFDocumentError("Keine Bearbeitungspositionen vorhanden.")
        data = BGF_DATA[self.bgf_size_var.get()]

        def _entry_float(key: str, caption: str) -> float:
            raw = self.entries[key].get().strip()
            try:
                value = float(raw.replace(",", "."))
            except ValueError as exc:
                raise BGFDocumentError(f"{caption} ist keine gueltige Zahl.") from exc
            if not math.isfinite(value):
                raise BGFDocumentError(f"{caption} darf nicht NaN/Infinity sein.")
            return value

        def _entry_int(key: str, caption: str) -> int:
            value = _entry_float(key, caption)
            if value != int(value):
                raise BGFDocumentError(f"{caption} muss eine ganze Zahl sein.")
            return int(value)

        tool_num = _entry_int("tool_num", "Werkzeug-Nummer T")
        if tool_num <= 0:
            raise BGFDocumentError("Werkzeug-Nummer T muss groesser 0 sein.")
        clearance = _entry_float("approach_clearance", "Sicherheitsabstand ueber Oberflaeche")
        from bgf_surface import validate_approach_clearance

        err = validate_approach_clearance(clearance)
        if err:
            raise BGFDocumentError(err)
        safe_z = _entry_float("safe_z", "Sicherheits-Z")
        end_safe_z = _entry_float("end_safe_z", "End-Sicherheits-Z")
        program_name = clean_program_name(self.entries["program_name"].get(), "BGF_LISTE")
        try:
            programmer = normalize_programmer(self.programmer_var.get())
        except ProgrammerError as exc:
            raise BGFDocumentError(f"Programmierer: {exc.message}") from exc
        return build_document(
            thread_size=data.size,
            article_no=data.article_no,
            tool_number=tool_num,
            program_name=program_name,
            approach_clearance=clearance,
            safe_z=safe_z,
            end_safe_z=end_safe_z,
            positions=self.coord_rows,
            programmer=programmer,
        )

    def _apply_position_list_document(self, doc) -> None:
        """Atomar: erst alles vorbereiten, dann GUI ersetzen."""
        tool_key = resolve_tool_in_catalog(doc.thread_size, doc.article_no, BGF_DATA)
        # Alle Werte vor Mutation pruefen
        from bgf_surface import validate_approach_clearance

        err = validate_approach_clearance(doc.approach_clearance)
        if err:
            raise BGFDocumentError(err)

        # Mutation
        self.mode_var.set("Bohrgewindefraesen (BGF)")
        self.on_mode_change(None)
        self.bgf_size_var.set(tool_key)
        self.load_bgf_values()
        self.entries["tool_num"].delete(0, tk.END)
        self.entries["tool_num"].insert(0, str(doc.tool_number))
        self.entries["program_name"].delete(0, tk.END)
        self.entries["program_name"].insert(0, doc.program_name)
        self.programmer_var.set(doc.programmer)
        self.entries["approach_clearance"].delete(0, tk.END)
        self.entries["approach_clearance"].insert(0, f"{doc.approach_clearance:g}")
        self.entries["safe_z"].delete(0, tk.END)
        self.entries["safe_z"].insert(0, f"{doc.safe_z:g}")
        self.entries["end_safe_z"].delete(0, tk.END)
        self.entries["end_safe_z"].insert(0, f"{doc.end_safe_z:g}")
        self.coord_rows = list(doc.positions)
        self.position_mode_var.set("Koordinatenliste")
        self.on_position_mode_change(None)
        self._refresh_coord_tree()
        self.update_bgf_depth_status()

    def coord_save_list(self) -> None:
        if self.mode_var.get() != "Bohrgewindefraesen (BGF)":
            messagebox.showwarning("Hinweis", "Koordinatenliste ist derzeit nur fuer BGF verfuegbar.")
            return
        try:
            doc = self._collect_position_list_document()
        except BGFDocumentError as exc:
            messagebox.showerror("Speichern", exc.message)
            return
        path = filedialog.asksaveasfilename(
            title="Positionsliste speichern",
            defaultextension=".bgf.json",
            initialfile=self._coord_default_filename(".bgf.json"),
            initialdir=self._last_coord_dir,
            filetypes=[("BGF Positionsliste", "*.bgf.json"), ("JSON", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        try:
            save_document_json(path, doc)
        except OSError as exc:
            messagebox.showerror("Speichern", f"Datei konnte nicht geschrieben werden:\n{exc}")
            return
        self._last_coord_dir = os.path.dirname(path)
        messagebox.showinfo("Speichern", "Positionsliste gespeichert.")

    def coord_load_list(self) -> None:
        if self.mode_var.get() != "Bohrgewindefraesen (BGF)":
            messagebox.showwarning("Hinweis", "Koordinatenliste ist derzeit nur fuer BGF verfuegbar.")
            return
        path = filedialog.askopenfilename(
            title="Positionsliste laden",
            initialdir=self._last_coord_dir,
            filetypes=[("BGF Positionsliste", "*.bgf.json"), ("JSON", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        try:
            doc = load_document_json(path)
            resolve_tool_in_catalog(doc.thread_size, doc.article_no, BGF_DATA)
        except BGFDocumentError as exc:
            messagebox.showerror("Laden", exc.message)
            return
        except OSError as exc:
            messagebox.showerror("Laden", f"Datei konnte nicht gelesen werden:\n{exc}")
            return

        if self.coord_rows:
            if not messagebox.askyesno(
                "Liste laden",
                f"Die aktuelle Koordinatenliste enthaelt {len(self.coord_rows)} Positionen.\n\n"
                "Beim Laden wird diese Liste ersetzt.\n\nFortfahren?",
            ):
                return

        # Snapshot fuer Rollback bei spaetem Fehler
        snapshot = {
            "rows": list(self.coord_rows),
            "size": self.bgf_size_var.get(),
            "tool": self.entries["tool_num"].get(),
            "program": self.entries["program_name"].get(),
            "programmer": self.programmer_var.get(),
            "clearance": self.entries["approach_clearance"].get(),
            "safe_z": self.entries["safe_z"].get(),
            "end_safe_z": self.entries["end_safe_z"].get(),
            "mode": self.position_mode_var.get(),
        }
        try:
            self._apply_position_list_document(doc)
        except BGFDocumentError as exc:
            self.coord_rows = snapshot["rows"]
            self.bgf_size_var.set(snapshot["size"])
            self.load_bgf_values()
            self.entries["tool_num"].delete(0, tk.END)
            self.entries["tool_num"].insert(0, snapshot["tool"])
            self.entries["program_name"].delete(0, tk.END)
            self.entries["program_name"].insert(0, snapshot["program"])
            self.programmer_var.set(snapshot["programmer"])
            self.entries["approach_clearance"].delete(0, tk.END)
            self.entries["approach_clearance"].insert(0, snapshot["clearance"])
            self.entries["safe_z"].delete(0, tk.END)
            self.entries["safe_z"].insert(0, snapshot["safe_z"])
            self.entries["end_safe_z"].delete(0, tk.END)
            self.entries["end_safe_z"].insert(0, snapshot["end_safe_z"])
            self.position_mode_var.set(snapshot["mode"])
            self.on_position_mode_change(None)
            self._refresh_coord_tree()
            messagebox.showerror("Laden", exc.message)
            return

        self._last_coord_dir = os.path.dirname(path)
        # Safety/Depth neu berechnen – ungültige Listen bleiben sichtbar, NC bleibt blockiert
        self._refresh_coord_tree()
        messagebox.showinfo(
            "Laden",
            f"{len(doc.positions)} Position(en) geladen.\n"
            f"Werkzeug: {doc.thread_size} / Artikel {doc.article_no}",
        )

    def coord_export_csv(self) -> None:
        if self.mode_var.get() != "Bohrgewindefraesen (BGF)":
            messagebox.showwarning("Hinweis", "Koordinatenliste ist derzeit nur fuer BGF verfuegbar.")
            return
        if not self.coord_rows:
            messagebox.showwarning("CSV exportieren", "Keine Bearbeitungspositionen vorhanden.")
            return
        path = filedialog.asksaveasfilename(
            title="CSV exportieren",
            defaultextension=".csv",
            initialfile=self._coord_default_filename(".csv"),
            initialdir=self._last_coord_dir,
            filetypes=[("CSV", "*.csv"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        try:
            write_bgf_csv_file(path, self.coord_rows)
        except OSError as exc:
            messagebox.showerror("CSV exportieren", f"Datei konnte nicht geschrieben werden:\n{exc}")
            return
        self._last_coord_dir = os.path.dirname(path)
        messagebox.showinfo("CSV exportieren", f"{len(self.coord_rows)} Position(en) exportiert.")

    def coord_import_csv(self) -> None:
        if self.mode_var.get() != "Bohrgewindefraesen (BGF)":
            messagebox.showwarning("Hinweis", "Koordinatenliste ist derzeit nur fuer BGF verfuegbar.")
            return
        path = filedialog.askopenfilename(
            title="CSV importieren",
            initialdir=self._last_coord_dir,
            filetypes=[("CSV", "*.csv"), ("Textdateien", "*.txt"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return

        replace: Optional[bool] = True
        if self.coord_rows:
            choice = messagebox.askyesnocancel(
                "CSV importieren",
                "Ja = aktuelle Liste ersetzen\n"
                "Nein = an aktuelle Liste anhaengen\n"
                "Abbrechen = kein Import",
            )
            if choice is None:
                return
            replace = bool(choice)

        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                text = handle.read()
            parsed = import_bgf_csv_text(
                text,
                default_thread_depth=self._default_template_thread_depth(),
            )
        except CoordinateParseError as exc:
            messagebox.showerror(
                "CSV-Import",
                "CSV-Import abgebrochen. Bestehende Liste unveraendert.\n\n"
                + "\n".join(exc.messages),
            )
            return
        except OSError as exc:
            messagebox.showerror("CSV-Import", f"Datei konnte nicht gelesen werden:\n{exc}")
            return

        previous = list(self.coord_rows)
        if replace:
            self.coord_rows = list(parsed)
        else:
            self.coord_rows.extend(parsed)
        self._refresh_coord_tree()
        self._last_coord_dir = os.path.dirname(path)

        # Duplicate-Warnung (ohne Auto-Loeschen)
        from coordinates.bgf_list_validation import find_duplicate_xyz

        dups = find_duplicate_xyz(self.coord_rows)
        msg = f"{len(parsed)} Position(en) importiert."
        if dups:
            sample = ", ".join(f"({x:g}|{y:g}|Z{z:g})" for x, y, z in dups[:5])
            msg += f"\n\nWarnung: Die Koordinatenliste enthaelt doppelte Positionen: {sample}"
        messagebox.showinfo("CSV-Import", msg)
        # previous ungenutzt – atomar: parsed war vollstaendig bevor Mutation
        _ = previous

    def prepare_bgf_coordinate_list(self):
        common_safe = self.get_float_value("safe_z", "Sicherheits-Z")
        common_end = self.get_float_value("end_safe_z", "End-Sicherheits-Z")
        clearance = self.get_approach_clearance()
        if common_safe is None or common_end is None or clearance is None:
            return None
        result = validate_bgf_coordinate_list(
            self.coord_rows,
            self.get_bgf_depth_policy(),
            safe_z=common_safe,
            end_safe_z=common_end,
            approach_clearance=clearance,
        )
        self._refresh_coord_tree()
        if result.warnings:
            if not messagebox.askyesno(
                "Warnung",
                "\n".join(result.warnings) + "\n\nTrotzdem fortfahren?",
            ):
                return None
        if not result.ok_for_nc:
            messagebox.showerror(
                "Koordinatenliste",
                "NC-Code kann nicht erzeugt werden.\n\n" + "\n".join(result.errors),
            )
            return None
        return [row.position for row in result.positions]

    def get_approach_clearance(self) -> Optional[float]:
        """Globaler Sicherheitsabstand ueber Oberflaeche; Default 1.000 mm."""
        raw = self.entries.get("approach_clearance")
        if raw is None:
            return DEFAULT_APPROACH_CLEARANCE
        text = raw.get().strip()
        if text == "":
            messagebox.showerror(
                "Fehler",
                "Sicherheitsabstand ueber Oberflaeche fehlt.",
            )
            return None
        try:
            value = float(text.replace(",", "."))
        except ValueError:
            messagebox.showerror(
                "Fehler",
                "Sicherheitsabstand ueber Oberflaeche muss numerisch sein.",
            )
            return None
        err = validate_approach_clearance(value)
        if err:
            messagebox.showerror("Fehler", err)
            return None
        return value

    def get_single_xy(self) -> Optional[tuple]:
        x = self.get_float_value("single_x", "Einzelposition X")
        y = self.get_float_value("single_y", "Einzelposition Y")
        if x is None or y is None:
            return None
        return x, y

    def get_single_position(self) -> Optional[tuple]:
        """X, Y, surface_z fuer BGF/BSF-Einzelposition."""
        xy = self.get_single_xy()
        if xy is None:
            return None
        surface_z = self.get_float_value("single_surface_z", "Bohrungsanfang Z")
        if surface_z is None:
            return None
        if not math.isfinite(surface_z) or not math.isfinite(xy[0]) or not math.isfinite(xy[1]):
            messagebox.showerror("Fehler", "X/Y/Bohrungsanfang Z duerfen nicht NaN/Infinity sein.")
            return None
        return xy[0], xy[1], surface_z

    def update_bgf_nutzlaenge_info(self) -> None:
        if not hasattr(self, "bgf_nutzlaenge_label"):
            return
        if self.mode_var.get() != "Bohrgewindefraesen (BGF)":
            self.bgf_nutzlaenge_label.config(text="")
            return
        data = BGF_DATA[self.bgf_size_var.get()]
        self.bgf_nutzlaenge_label.config(
            text=f"BGF Hersteller-Nutzlaenge {data.size}: {data.thread_length:.2f} mm (nicht editierbar)"
        )

    def on_bgf_size_change(self, event) -> None:
        self.load_bgf_values()
        # Gewindetiefen der Liste bleiben unveraendert; Status neu gegen neues Werkzeug pruefen.
        if self.coord_rows:
            self._refresh_coord_tree()

    def on_bgf_depth_input_change(self, event=None) -> None:
        self.update_bgf_depth_status()

    def get_bgf_depth_policy(self):
        data = BGF_DATA[self.bgf_size_var.get()]
        approved = approved_max_thread_depth(data.size, data.article_no)
        return policy_from_tool(
            data.size,
            data.thread_length,
            data.drill_depth,
            data.mill_start_depth,
            article_no=data.article_no,
            approved_max_thread_depth=approved,
            axial_increment=axial_increment_from_passes(data.passes),
            variable_depth_rule_validated=True,
        )

    def parse_optional_core_hole_depth(self) -> tuple:
        """Returns (ok, value_or_None). ok=False bei Parsefehler."""
        raw = self.entries.get("bgf_core_hole_depth")
        if raw is None:
            return True, None
        text = raw.get().strip()
        if text == "":
            return True, None
        try:
            value = float(text.replace(",", "."))
        except ValueError:
            return False, None
        return True, value

    def parse_thread_depth_input(self) -> tuple:
        """Returns (ok, value). ok=False bei Parsefehler."""
        raw = self.entries.get("bgf_thread_depth")
        if raw is None:
            return False, None
        text = raw.get().strip()
        if text == "":
            return False, None
        try:
            value = float(text.replace(",", "."))
        except ValueError:
            return False, None
        return True, value

    def current_surface_z_for_depth_info(self) -> float:
        if not hasattr(self, "position_mode_var"):
            return 0.0
        mode = self.get_position_mode()
        key = None
        if mode == PositionMode.SINGLE:
            key = "single_surface_z"
        elif mode == PositionMode.CIRCLE:
            key = "circle_surface_z"
        if key and key in self.entries:
            try:
                value = float(self.entries[key].get().replace(",", "."))
            except ValueError:
                return 0.0
            if math.isfinite(value):
                return value
        return 0.0

    def get_circle_surface_z(self) -> Optional[float]:
        value = self.get_float_value("circle_surface_z", "Bohrungsanfang Z")
        if value is None:
            return None
        if not math.isfinite(value):
            messagebox.showerror("Fehler", "Bohrungsanfang Z darf nicht NaN/Infinity sein.")
            return None
        return value

    def get_bsf_reference_z(self) -> Optional[float]:
        ok, value, err = parse_reference_z(
            self.entries["bsf_reference_z"].get() if "bsf_reference_z" in self.entries else ""
        )
        if not ok:
            messagebox.showerror("Z-Lage Bezugsebene", err)
            return None
        return value

    def get_selected_bsf_tool_profile(self, *, show_error: bool = True):
        profile = profile_by_designation(
            self.bsf_tool_profile_var.get() if hasattr(self, "bsf_tool_profile_var") else ""
        )
        if profile is None and show_error:
            messagebox.showerror("HEULE Werkzeug", "HEULE_TOOL_SELECTION_REQUIRED")
        return profile

    def evaluate_current_bgf_depth(self):
        policy = self.get_bgf_depth_policy()
        ok_td, thread_depth = self.parse_thread_depth_input()
        ok_ch, core_hole = self.parse_optional_core_hole_depth()
        surface_z = self.current_surface_z_for_depth_info()

        if not ok_td:
            from bgf_depth import BGFDepthEvaluation

            return BGFDepthEvaluation(
                ok_for_nc=False,
                status=DepthGateStatus.INVALID,
                messages=["Gewindetiefe ist keine gueltige Zahl."],
                status_text="Ungueltige Tiefenkombination",
                status_level="red",
                max_thread_depth=policy.approved_max_thread_depth,
            )
        if not ok_ch:
            from bgf_depth import BGFDepthEvaluation

            return BGFDepthEvaluation(
                ok_for_nc=False,
                status=DepthGateStatus.INVALID,
                messages=["Kernlochtiefe Soll ist keine gueltige Zahl."],
                status_text="Ungueltige Tiefenkombination",
                status_level="red",
                max_thread_depth=policy.approved_max_thread_depth,
            )

        return evaluate_bgf_depth(
            BGFDepthRequest(thread_depth=thread_depth, core_hole_depth=core_hole),
            policy,
            surface_z=surface_z,
        )

    def update_bgf_depth_status(self) -> None:
        if not hasattr(self, "bgf_depth_info_labels"):
            return
        if self.mode_var.get() != "Bohrgewindefraesen (BGF)":
            return

        evaluation = self.evaluate_current_bgf_depth()
        policy = self.get_bgf_depth_policy()
        surface_z = self.current_surface_z_for_depth_info()

        if evaluation.thread_end_z is not None:
            end_txt = f"Z{evaluation.thread_end_z:+.4f}"
        else:
            end_txt = "-"

        if policy.approved_max_thread_depth is None:
            max_txt = "noch nicht hinterlegt / nicht validiert"
        else:
            max_txt = (
                f"{policy.approved_max_thread_depth:.3f} mm "
                "(Freigabe basiert auf vorhandener CERATIZIT-Referenz)"
            )

        if evaluation.nc_drill_depth is not None and evaluation.nc_drill_z is not None:
            nc_txt = (
                f"{evaluation.nc_drill_depth:.3f} mm  "
                f"(Z{evaluation.nc_drill_z:+.4f})"
            )
            if evaluation.is_template:
                nc_txt += " – Hersteller-Template"
            else:
                nc_txt += " – Axial-Shift"
        elif evaluation.template_nc_drill_z is not None:
            nc_txt = f"Template waere Z{evaluation.template_nc_drill_z:+.4f}"
        else:
            nc_txt = "-"

        if evaluation.nc_mill_start_depth is not None and evaluation.nc_mill_start_z is not None:
            mill_txt = (
                f"{evaluation.nc_mill_start_depth:.3f} mm  "
                f"(Z{evaluation.nc_mill_start_z:+.4f})"
            )
        else:
            mill_txt = "-"

        mode_txt = evaluation.depth_mode_label or "-"

        colors = {"green": "#1e8449", "yellow": "#b7950b", "red": "#c0392b"}
        status_color = colors.get(evaluation.status_level, "#2c3e50")

        self.bgf_depth_info_labels["thread_end"].config(text=end_txt)
        self.bgf_depth_info_labels["max_depth"].config(text=max_txt)
        self.bgf_depth_info_labels["nc_drill"].config(text=nc_txt)
        self.bgf_depth_info_labels["nc_mill"].config(text=mill_txt)
        self.bgf_depth_info_labels["depth_mode"].config(text=mode_txt)
        self.bgf_depth_info_labels["status"].config(
            text=evaluation.status_text,
            foreground=status_color,
        )

        # Referenzhinweis (keine Berechnung)
        refs = references_for_size(policy.thread_size)
        if refs and evaluation.status_level == "yellow":
            ref_bits = []
            for r in refs[:3]:
                if r.core_hole_depth is not None:
                    ref_bits.append(f"{r.thread_depth:g}→Kernloch {r.core_hole_depth:g}")
                else:
                    ref_bits.append(f"{r.thread_depth:g}→Dulo")
            _ = surface_z

    def ensure_bgf_depth_allows_nc(self) -> bool:
        evaluation = self.evaluate_current_bgf_depth()
        self.update_bgf_depth_status()
        if evaluation.ok_for_nc:
            return True
        messagebox.showerror(
            "BGF-Tiefe",
            "\n".join(evaluation.messages) if evaluation.messages else evaluation.status_text,
        )
        return False

    def _ensure_bgf_safe_above_approach(self, surface_z: float, clearance: float, common: dict) -> bool:
        approach = above_surface(surface_z, clearance)
        if common["safe_z"] < approach or common["end_safe_z"] < approach:
            messagebox.showerror(
                "Sicherheits-Z",
                "Sicherheits-Z muss oberhalb der Anfahrhoehe liegen "
                f"(Anfahr-Z {fmt_axis('Z', approach)}).",
            )
            return False
        return True

    def load_bgf_values(self) -> None:
        data = BGF_DATA[self.bgf_size_var.get()]
        values = {
            "article_no": data.article_no,
            "radius": f"R+{data.radius:.4f} mm",
            "thread_length": f"{data.thread_length:.2f} mm (Template)",
            "drill_depth": f"Z-{data.drill_depth:.4f}",
            "mill_start_depth": f"Z-{data.mill_start_depth:.4f}",
            "pitch": f"{data.pitch:.3f} mm",
            "spindle_speed": f"S{data.spindle_speed}",
            "feed_drill": f"F{data.feed_drill}",
            "passes": str(len(data.passes)),
        }
        for key, value in values.items():
            if key in self.bgf_info_labels:
                self.bgf_info_labels[key].config(text=value)

        if "bgf_thread_depth" in self.entries:
            self.entries["bgf_thread_depth"].delete(0, tk.END)
            self.entries["bgf_thread_depth"].insert(0, f"{data.thread_length:.3f}")
        if "bgf_core_hole_depth" in self.entries:
            self.entries["bgf_core_hole_depth"].delete(0, tk.END)

        self.update_bgf_nutzlaenge_info()
        self.update_bgf_depth_status()
        self.refresh_nc_output_status()

    def on_m_activate_change(self, event) -> None:
        state = "normal" if self.m_activate_var.get() == "Freitext / Eigener M-Befehl" else "disabled"
        self.m_activate_custom.config(state=state)

    def on_m_deactivate_change(self, event) -> None:
        state = "normal" if self.m_deactivate_var.get() == "Eigener M-Befehl" else "disabled"
        self.m_deactivate_custom.config(state=state)

    def on_bsf_tool_profile_change(self, event=None) -> None:
        profile = self.get_selected_bsf_tool_profile(show_error=False)
        self.bsf_measurement_value.set(MEASUREMENT_LABEL)
        if profile is None:
            self.bsf_measurement_face_to_edge_value.set("—")
            self.bsf_activation_speed_value.set("—")
            if "blade_thickness" in self.entries:
                self.entries["blade_thickness"].delete(0, tk.END)
            self.blade_measurement_var.set(MEASUREMENT_LABEL)
            self.refresh_nc_output_status()
            return
        self.bsf_measurement_face_to_edge_value.set(f"{profile.measurement_face_to_cutting_edge_mm:.3f} mm")
        if "blade_thickness" in self.entries:
            self.entries["blade_thickness"].delete(0, tk.END)
            self.entries["blade_thickness"].insert(0, f"{profile.measurement_face_to_cutting_edge_mm:.3f}")
        self.blade_measurement_var.set(MEASUREMENT_LABEL)
        if profile.activation_speed_rpm is None:
            self.bsf_activation_speed_value.set("—")
        else:
            self.bsf_activation_speed_value.set(f"{profile.activation_speed_rpm:d} U/min")
        self.refresh_nc_output_status()

    # ------------------------------------------------------------------
    # Eingabe / Validierung
    # ------------------------------------------------------------------

    def get_float_value(self, key: str, caption: Optional[str] = None) -> Optional[float]:
        try:
            return float(self.entries[key].get().replace(",", "."))
        except (KeyError, ValueError):
            messagebox.showerror("Fehler", f"Ungueltiger Wert fuer {caption or key}")
            return None

    def get_int_value(self, key: str, caption: Optional[str] = None) -> Optional[int]:
        try:
            if key == "tool_num":
                raw = self._tool_num_var.get()
            else:
                raw = self.entries[key].get()
            return int(float(raw.replace(",", ".")))
        except (KeyError, ValueError):
            messagebox.showerror("Fehler", f"Ungueltiger Wert fuer {caption or key}")
            return None

    def validate_common(self):
        diameter = self.get_float_value("diameter", "Teilkreis-Durchmesser")
        count = self.get_int_value("count", "Anzahl Bohrungen")
        start_angle = self.get_float_value("start_angle", "Startwinkel")
        center_x = self.get_float_value("center_x", "TK-Mitte X")
        center_y = self.get_float_value("center_y", "TK-Mitte Y")
        tool_num = self.get_int_value("tool_num", "Werkzeug-Nummer")
        blank_size = self.get_float_value("blank_size", "Rohteil-Kantenlaenge")
        blank_height = self.get_float_value("blank_height", "Rohteil-Hoehe")
        raw_stock_top_z = self.get_float_value("raw_stock_top_z", "Rohteil-Oberkante Z")
        safe_z = self.get_float_value("safe_z", "Sicherheits-Z")
        end_safe_z = self.get_float_value("end_safe_z", "End-Sicherheits-Z")

        values = [
            diameter,
            count,
            start_angle,
            center_x,
            center_y,
            tool_num,
            blank_size,
            blank_height,
            raw_stock_top_z,
            safe_z,
            end_safe_z,
        ]
        if any(v is None for v in values):
            return None
        if diameter <= 0:
            messagebox.showerror("Fehler", "Teilkreis-Durchmesser muss groesser 0 sein.")
            return None
        if count <= 0:
            messagebox.showerror("Fehler", "Anzahl Bohrungen muss groesser 0 sein.")
            return None
        if tool_num <= 0:
            messagebox.showerror("Fehler", "Werkzeug-Nummer muss groesser 0 sein.")
            return None
        if not math.isfinite(blank_size) or blank_size <= 0:
            messagebox.showerror("Fehler", "Rohteil-Kantenlaenge muss eine endliche Zahl groesser 0 sein.")
            return None
        if not math.isfinite(blank_height) or blank_height <= 0:
            messagebox.showerror("Fehler", "Rohteil-Hoehe Z muss eine endliche Zahl groesser 0 sein.")
            return None
        if not math.isfinite(raw_stock_top_z):
            messagebox.showerror("Fehler", "Rohteil-Oberkante Z muss eine endliche Zahl sein.")
            return None
        if safe_z <= 0 or end_safe_z <= 0:
            messagebox.showwarning("Warnung", "Sicherheits-Z ist nicht positiv. Bitte Kollisionsfreiheit pruefen.")

        try:
            programmer = normalize_programmer(self.programmer_var.get())
        except ProgrammerError as exc:
            messagebox.showerror("Programmierer", exc.message)
            return None

        return {
            "diameter": diameter,
            "count": count,
            "start_angle": start_angle,
            "center_x": center_x,
            "center_y": center_y,
            "tool_num": tool_num,
            "blank_size": blank_size,
            "blank_height": blank_height,
            "raw_stock_top_z": raw_stock_top_z,
            "safe_z": safe_z,
            "end_safe_z": end_safe_z,
            "program_name": clean_program_name(self.entries["program_name"].get(), "NC_PROGRAMM"),
            "programmer": programmer,
        }

    def get_m_commands(self):
        act = self.m_activate_var.get()
        deact = self.m_deactivate_var.get()

        if "M7" in act:
            m_act = "M7"
        elif "M8" in act:
            m_act = "M8"
        elif "M89" in act:
            m_act = "M89"
        else:
            m_act = self.m_activate_custom.get().strip().upper() or "M7"

        m_deact = "M9" if "M9" in deact else (self.m_deactivate_custom.get().strip().upper() or "M9")
        return m_act, m_deact

    def set_output(self, code: List[str]) -> None:
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, "\n".join(code))
        self.nc_guard.mark_generated(self)
        self.refresh_nc_output_status()

    # ------------------------------------------------------------------
    # Code-Erzeugung allgemein
    # ------------------------------------------------------------------

    def generate_code(self) -> None:
        if self.mode_var.get() == "Bohrgewindefraesen (BGF)":
            self.generate_bgf_code()
        else:
            self.generate_bsf_code()

    def add_block_form(self, code: List[str], common: dict, bgf_mode: bool = True, z_origin: float = 0.0) -> None:
        """BLK FORM aus Rohteil-Oberkante und Rohteil-Hoehe.

        surface_z / BSF reference_z fliessen nicht ein. z_origin bleibt ungenutzt
        (Signatur kompatibel). bgf_mode ebenfalls ohne Z-Einfluss.
        """
        half = common["blank_size"] / 2.0
        z_min, z_max = blk_form_z_extents(common["raw_stock_top_z"], common["blank_height"])
        _ = (bgf_mode, z_origin)

        code.append(
            f"BLK FORM 0.1 Z {fmt_axis('X', -half)} {fmt_axis('Y', -half)} {fmt_axis('Z', z_min)}"
        )
        code.append(
            f"BLK FORM 0.2 {fmt_axis('X', half)} {fmt_axis('Y', half)} {fmt_axis('Z', z_max)}"
        )

    def _ensure_bgf_surfaces_inside_stock(self, surfaces: List[float], common: dict) -> bool:
        top = common["raw_stock_top_z"]
        height = common["blank_height"]
        if all_surfaces_inside_stock(surfaces, top, height):
            return True
        messagebox.showerror("Rohteil", SURFACE_OUTSIDE_STOCK_MESSAGE)
        return False

    def add_counted_circle_loop(
        self,
        code: List[str],
        common: dict,
        sub_label: int,
        *,
        restore_pole_each_iteration: bool = False,
    ) -> None:
        """Teilkreis-Schleife mit Q2-Zaehler.

        restore_pole_each_iteration=True: absolutes CC unmittelbar vor jedem LP.
        Noetig, wenn das Unterprogramm den Heidenhain-Pol (CC) veraendert.
        """
        step = 360.0 / common["count"]
        radius = common["diameter"] / 2.0
        pole = (
            f"CC {fmt_axis('X', common['center_x'])} {fmt_axis('Y', common['center_y'])} "
            "; Teilkreis-Mitte / Pol"
        )
        if not restore_pole_each_iteration:
            code.append(pole)
        code.append(f"Q1 = {fmt_q(common['start_angle'])} ; Startwinkel")
        code.append("Q2 = +0 ; Bohrungszaehler")
        code.append("LBL 1 ; Schleifenanfang Teilkreis")
        if restore_pole_each_iteration:
            code.append(pole)
        code.append(f"LP PR+{radius:.4f} PA+Q1 R0 FMAX ; Teilkreisposition")
        code.append(f"CALL LBL {sub_label} ; Bearbeitung aufrufen")
        code.append(f"Q1 = Q1 + {step:.4f} ; Naechster Winkel")
        code.append("Q2 = Q2 + 1 ; Zaehler erhoehen")
        code.append(f"FN 12: IF +Q2 LT +{common['count']} GOTO LBL 1 ; exakt {common['count']} Bohrungen")

    # ------------------------------------------------------------------
    # BGF-Code nach Herstellerbahnen
    # ------------------------------------------------------------------

    def generate_bgf_code(self) -> None:
        common = self.validate_common()
        if not common:
            return

        position_mode = self.get_position_mode()
        # Koordinatenliste: Tiefen gate pro Position (programmweit), nicht ueber Einzel-Eingabefelder.
        if position_mode != PositionMode.COORDINATES:
            if not self.ensure_bgf_depth_allows_nc():
                return

        data = BGF_DATA[self.bgf_size_var.get()]
        program_name = clean_program_name(common["program_name"], "BGF_TK")
        clearance = self.get_approach_clearance()
        if clearance is None:
            return

        code: List[str] = []
        code.append(f"BEGIN PGM {program_name} MM")
        programmer_line = programmer_comment_line(common["programmer"])
        if programmer_line:
            code.append(programmer_line)
        code.append(f"; CERATIZIT BGF {data.size}")
        code.append(f"; ARTIKEL: {data.article_no}")
        code.append(f"; WERKZEUGRADIUS: R+{data.radius:.4f} MM")
        if self.output_tool_def_var.get():
            code.append("; TOOL DEF: AKTIV")
        else:
            code.append("; TOOL DEF: AUS - RADIUS IN WERKZEUGTABELLE PRUEFEN")
        code.append("; Bezug: Aussenbahn, inkremental, Fraesmethode Gegenlauf")
        code.append(
            f"; Hersteller-Template Gewindetiefe: {data.thread_length:.4f} mm"
        )
        code.append(f"; Sicherheitsabstand ueber Oberflaeche: {clearance:.4f} mm")
        if position_mode != PositionMode.COORDINATES:
            depth_info = self.evaluate_current_bgf_depth()
            if depth_info.depth_mode_label:
                code.append(f"; TIEFENMODUS: {depth_info.depth_mode_label.upper()}")
        code.append("; ACHTUNG: Nullpunkt, Werkzeugdaten, M-Funktionen und Simulation pruefen")
        z_origin = 0.0
        circle_surface_z = None
        single_pos = None
        stock_surfaces: List[float] = []
        if position_mode == PositionMode.SINGLE:
            single_pos = self.get_single_position()
            if single_pos is None:
                return
            z_origin = single_pos[2]
            stock_surfaces = [z_origin]
            if not self._ensure_bgf_safe_above_approach(z_origin, clearance, common):
                return
        elif position_mode == PositionMode.CIRCLE:
            circle_surface_z = self.get_circle_surface_z()
            if circle_surface_z is None:
                return
            z_origin = circle_surface_z
            stock_surfaces = [z_origin]
            if not self._ensure_bgf_safe_above_approach(z_origin, clearance, common):
                return
        elif position_mode == PositionMode.COORDINATES:
            stock_surfaces = [pos.surface_z for pos in self.coord_rows]
        if stock_surfaces and not self._ensure_bgf_surfaces_inside_stock(stock_surfaces, common):
            return
        self.add_block_form(code, common)

        if self.output_tool_def_var.get():
            code.append(f"TOOL DEF {common['tool_num']} L+0.0000 R+{data.radius:.4f} ; Laenge pruefen/anpassen")

        code.append(f"TOOL CALL {common['tool_num']} Z S{data.spindle_speed}")
        code.append(f"L {fmt_axis('Z', common['end_safe_z'])} R0 FMAX")
        code.append("")

        if position_mode == PositionMode.SINGLE:
            if single_pos is None:
                return
            x, y, surface_z = single_pos
            depth_ev = self.evaluate_current_bgf_depth()
            if not depth_ev.ok_for_nc or depth_ev.nc_drill_depth is None or depth_ev.nc_mill_start_depth is None:
                self.ensure_bgf_depth_allows_nc()
                return
            z_approach = above_surface(surface_z, clearance)
            code.append("; --- EINZELPOSITION ---")
            if depth_ev.depth_mode_label:
                code.append(f"; Tiefenmodus: {depth_ev.depth_mode_label}")
            if depth_ev.depth_delta:
                code.append(
                    f"; Axial-Shift delta={depth_ev.depth_delta:.4f} mm "
                    f"drill={depth_ev.nc_drill_depth:.4f} mill_start={depth_ev.nc_mill_start_depth:.4f}"
                )
            code.append(
                f"L {fmt_axis('X', x)} {fmt_axis('Y', y)} {fmt_axis('Z', z_approach)} R0 FMAX M13"
            )
            code.extend(
                self.get_bgf_sequence(
                    data,
                    common["tool_num"],
                    surface_z=surface_z,
                    approach_clearance=clearance,
                    drill_depth=depth_ev.nc_drill_depth,
                    mill_start_depth=depth_ev.nc_mill_start_depth,
                )
            )
            code.append(f"L {fmt_axis('Z', common['end_safe_z'])} R0 FMAX M30")
            code.append(f"END PGM {program_name} MM")
        elif position_mode == PositionMode.COORDINATES:
            positions = self.prepare_bgf_coordinate_list()
            if positions is None:
                return
            tool_num = common["tool_num"]
            safe_z = common["safe_z"]
            end_safe_z = common["end_safe_z"]
            policy = self.get_bgf_depth_policy()

            def sequence_for_position(pos: BGFCoordinatePosition) -> List[str]:
                ev = evaluate_bgf_depth(
                    BGFDepthRequest(pos.thread_depth, pos.core_hole_depth),
                    policy,
                    surface_z=pos.surface_z,
                )
                return self.get_bgf_sequence(
                    data,
                    tool_num,
                    surface_z=pos.surface_z,
                    approach_clearance=clearance,
                    drill_depth=ev.nc_drill_depth if ev.nc_drill_depth is not None else data.drill_depth,
                    mill_start_depth=(
                        ev.nc_mill_start_depth
                        if ev.nc_mill_start_depth is not None
                        else data.mill_start_depth
                    ),
                )

            # Sequenz: safe_z -> XY FMAX -> approach_z -> Herstellerbahn -> safe_z -> naechste Pos.
            code.extend(
                emit_bgf_coordinate_program_body(
                    positions,
                    safe_z=safe_z,
                    end_safe_z=end_safe_z,
                    sequence_for_position=sequence_for_position,
                    approach_clearance=clearance,
                )
            )
            code.append(f"END PGM {program_name} MM")
        else:
            if circle_surface_z is None:
                return
            depth_ev = self.evaluate_current_bgf_depth()
            if not depth_ev.ok_for_nc or depth_ev.nc_drill_depth is None or depth_ev.nc_mill_start_depth is None:
                self.ensure_bgf_depth_allows_nc()
                return
            code.append("; --- TEILKREIS ---")
            if depth_ev.depth_mode_label:
                code.append(f"; Tiefenmodus: {depth_ev.depth_mode_label}")
            code.append(f"L {fmt_axis('Z', common['safe_z'])} R0 FMAX")
            self.add_counted_circle_loop(
                code, common, sub_label=100, restore_pole_each_iteration=True
            )
            code.append(f"L {fmt_axis('Z', common['end_safe_z'])} R0 FMAX M30")
            code.append("")
            code.append("LBL 100 ; Unterprogramm BGF auf aktueller XY-Position")
            code.append(
                f"L {fmt_axis('Z', above_surface(circle_surface_z, clearance))} R0 FMAX M13 ; "
                "XY bleibt auf aktueller Teilkreisposition"
            )
            code.extend(
                self.get_bgf_sequence(
                    data,
                    common["tool_num"],
                    surface_z=circle_surface_z,
                    approach_clearance=clearance,
                    drill_depth=depth_ev.nc_drill_depth,
                    mill_start_depth=depth_ev.nc_mill_start_depth,
                )
            )
            code.append(f"L {fmt_axis('Z', common['safe_z'])} R0 FMAX")
            code.append("LBL 0")
            code.append(f"END PGM {program_name} MM")

        self.set_output(code)

    def get_bgf_sequence(
        self,
        data: BGFToolData,
        tool_num: int,
        surface_z: float = 0.0,
        approach_clearance: float = DEFAULT_APPROACH_CLEARANCE,
        drill_depth: Optional[float] = None,
        mill_start_depth: Optional[float] = None,
    ) -> List[str]:
        """CERATIZIT-Herstellerbahn; absolute Z relativ zu surface_z, Inkremente unveraendert.

        drill_depth / mill_start_depth: Template oder Axial-Shift-Werte.
        predrill_depth bleibt immer herstellerbezogen zur Oberflaeche (nicht geshiftet).
        """
        use_drill = data.drill_depth if drill_depth is None else drill_depth
        use_mill = data.mill_start_depth if mill_start_depth is None else mill_start_depth
        lines: List[str] = []

        if data.predrill_depth is not None and data.feed_predrill is not None:
            lines.append("; ( ANBOHREN )")
            lines.append(
                f"L {fmt_axis('Z', absolute_from_surface(surface_z, data.predrill_depth))} "
                f"F{data.feed_predrill} M"
            )

        lines.append("; ( BOHREN )")
        lines.append(
            f"L {fmt_axis('Z', absolute_from_surface(surface_z, use_drill))} "
            f"F{data.feed_drill} M"
        )

        # Bei M5 bis M10 wird im Herstellerprogramm nach dem Bohren auf die Oberflaeche zurueckgezogen.
        if len(data.passes) > 1:
            lines.append(f"L {fmt_axis('Z', at_surface(surface_z))} FMAX M")

        lines.append("; ( FRAESEN IM GEGENLAUF )")
        lines.append(f"TOOL CALL {tool_num} Z DR0")

        for idx, p in enumerate(data.passes, start=1):
            if idx > 1:
                lines.append("; ( FRAESEN IM GEGENLAUF )")
            lines.append(
                f"L {fmt_axis('Z', absolute_from_surface(surface_z, use_mill))} "
                f"R0 FMAX M"
            )
            lines.append(f"L IX+0.0000 IY+{p.y_start:.4f} RR F{p.feed_start} M")
            lines.append(f"CC IX+0.0000 IY{p.cc_entry_y:+.4f}")
            lines.append(f"CP IPA-180 IZ{p.iz_entry:+.4f} DR- RR F{p.feed_start} M")
            lines.append(f"CC IX+0.0000 IY+{p.cc_thread_y:.4f}")
            lines.append(f"CP IPA-360 IZ{p.iz_thread:+.4f} DR- RR F{p.feed_thread} M")
            lines.append(f"CC IX+0.0000 IY+{p.cc_exit_y:.4f}")
            lines.append(f"CP IPA-180 IZ{p.iz_exit:+.4f} DR- RR F{p.feed_exit} M")
            lines.append(f"L IX+0.0000 IY-{p.y_start:.4f} R0 FMAX M")

        lines.append(f"L {fmt_axis('Z', above_surface(surface_z, approach_clearance))} R0 FMAX M")
        return lines

    # ------------------------------------------------------------------
    # HEULE BSF-Code
    # ------------------------------------------------------------------

    def calculate_bsf_z_values(self):
        bund_thickness = self.get_float_value("bund_thickness", "Bund-Dicke")
        sink_depth = self.get_float_value("sink_depth", "Senk-Fertigmaß")
        clearance = self.get_float_value("clearance", "Freifahr-Tiefe")
        if any(v is None for v in [bund_thickness, sink_depth, clearance]):
            return None

        tool_profile = self.get_selected_bsf_tool_profile()
        if tool_profile is None:
            return None

        reference_z = self.get_bsf_reference_z()
        if reference_z is None:
            return None

        z0_is_flange_bottom = self.z0_var.get() == "Z0 ist Unterkante Bund"
        # Relativgeometrie unveraendert; danach absolute Schneiden-Ziele, dann Vermesspunkt-Z programmieren.
        workpiece_relative = calculate_workpiece_bsf_z(
            bund_thickness,
            sink_depth,
            clearance,
            z0_is_flange_bottom=z0_is_flange_bottom,
        )
        target_cutting_edge_z = apply_workpiece_reference_z(workpiece_relative, reference_z)
        programmed = apply_measurement_face_offset(target_cutting_edge_z, tool_profile)
        programmed["tool_profile"] = tool_profile
        programmed["target_cutting_edge_z"] = target_cutting_edge_z
        programmed["reference_z"] = reference_z
        programmed["spindle_on_z"] = spindle_on_z(reference_z)
        programmed["bund_thickness"] = bund_thickness
        programmed["z0_is_flange_bottom"] = z0_is_flange_bottom
        return programmed

    def generate_bsf_code(self) -> None:
        common = self.validate_common()
        if not common:
            return

        tool_num = common["tool_num"]
        spindle_speed = self.get_int_value("spindle_speed", "Spindeldrehzahl")
        feed_rate = self.get_float_value("feed_rate", "Vorschub")
        dwell_time = self.get_float_value("dwell_time", "Wartezeit")
        if any(v is None for v in [spindle_speed, feed_rate, dwell_time]):
            return

        z_values = self.calculate_bsf_z_values()
        if not z_values:
            return

        safe_err = validate_bsf_safe_z_against_reference(
            common["safe_z"],
            common["end_safe_z"],
            z_values,
            reference_z=z_values["reference_z"],
            bund_thickness=z_values["bund_thickness"],
            z0_is_flange_bottom=z_values["z0_is_flange_bottom"],
            reduce_approach=bool(self.reduce_approach_var.get()),
        )
        if safe_err:
            messagebox.showerror("Sicherheits-Z", safe_err)
            return

        program_name = clean_program_name(common["program_name"], "BSF_RUECKWAERTS")
        m_act, m_deact = self.get_m_commands()
        position_mode = self.get_position_mode()
        blade = z_values["tool_profile"]

        code: List[str] = []
        code.append(f"BEGIN PGM {program_name} MM")
        programmer_line = programmer_comment_line(common["programmer"])
        if programmer_line:
            code.append(programmer_line)
        code.append("; HEULE BSF Rueckwaertssenken - Nullpunkt/Z-Werte vor Einsatz pruefen")
        code.append(f"; WERKZEUG: {blade.designation}")
        code.append(f"; VERMESSUNG: {MEASUREMENT_NC_COMMENT}")
        code.append(f"; VERMESSFLAECHE -> SCHNEIDE: +{blade.measurement_face_to_cutting_edge_mm:.3f} MM")
        code.append(f"; OFFSET-RICHTUNG: {MEASUREMENT_OFFSET_DIRECTION.upper()} ZUR SPINDEL")
        if blade.activation_speed_rpm is not None:
            code.append(f"; HEULE AKTIVIERUNGSDREHZAHL: {blade.activation_speed_rpm:d} U/MIN")
        # BLK FORM nur aus raw_stock_top_z. BSF Domain-Safety (reference_z /
        # TOP_EDGE vs. BOTTOM_EDGE innerhalb der Rohteil-Z-Ausdehnung) wird
        # hier bewusst nicht automatisch geprueft: Bund- und Bezugssemantik
        # sind nicht generisch auf Stock-Z abbildbar. PHASE BLKFORM.ZREF.1 #20.
        self.add_block_form(code, common)
        code.append(f"TOOL CALL {tool_num} Z S{spindle_speed}")
        code.append(f"L {fmt_axis('Z', common['end_safe_z'])} R0 FMAX")
        code.append("")

        if position_mode == PositionMode.SINGLE:
            xy = self.get_single_xy()
            if xy is None:
                return
            x, y = xy
            code.append("; --- EINZELPOSITION ---")
            code.append(f"L {fmt_axis('X', x)} {fmt_axis('Y', y)} {fmt_axis('Z', common['safe_z'])} R0 FMAX")
            code.extend(
                self.get_bsf_sequence(
                    z_values,
                    feed_rate,
                    dwell_time,
                    m_act,
                    m_deact,
                    common,
                    activation_speed_rpm=blade.activation_speed_rpm,
                )
            )
            code.append(f"L {fmt_axis('Z', common['end_safe_z'])} R0 FMAX M30")
            code.append(f"END PGM {program_name} MM")
        elif position_mode == PositionMode.COORDINATES:
            positions = self._validated_bsf_coord_positions()
            if positions is None:
                return
            sequence = self.get_bsf_sequence(
                z_values,
                feed_rate,
                dwell_time,
                m_act,
                m_deact,
                common,
                activation_speed_rpm=blade.activation_speed_rpm,
            )
            code.extend(
                emit_bsf_coordinate_program_body(
                    positions,
                    sequence_lines=sequence,
                    safe_z=common["safe_z"],
                    fmt_axis=fmt_axis,
                )
            )
            code.append(f"L {fmt_axis('Z', common['end_safe_z'])} R0 FMAX M30")
            code.append(f"END PGM {program_name} MM")
        else:
            code.append("; --- TEILKREIS ---")
            code.append(f"L {fmt_axis('Z', common['safe_z'])} R0 FMAX")
            self.add_counted_circle_loop(code, common, sub_label=100)
            code.append(f"L {fmt_axis('Z', common['end_safe_z'])} R0 FMAX M30")
            code.append("")
            code.append("LBL 100 ; Unterprogramm BSF auf aktueller XY-Position")
            code.extend(
                self.get_bsf_sequence(
                    z_values,
                    feed_rate,
                    dwell_time,
                    m_act,
                    m_deact,
                    common,
                    activation_speed_rpm=blade.activation_speed_rpm,
                )
            )
            code.append("LBL 0")
            code.append(f"END PGM {program_name} MM")

        self.set_output(code)

    def get_bsf_sequence(
        self,
        z_values,
        feed_rate: float,
        dwell_time: float,
        m_act: str,
        m_deact: str,
        common: dict,
        *,
        activation_speed_rpm: Optional[int] = None,
    ) -> List[str]:
        lines: List[str] = []
        lines.append("M5 ; Spindel aus")
        lines.append(f"{m_deact} ; Druck/Kuehlung aus, Messer geschlossen")
        lines.append(f"L {fmt_axis('Z', z_values['z_clearance'])} R0 FMAX ; Durch den Bund tauchen")
        reference_z = float(z_values.get("reference_z", 0.0))
        spin_z = z_values.get("spindle_on_z", spindle_on_z(reference_z))
        if activation_speed_rpm is not None:
            lines.append(
                f"L {fmt_axis('Z', spin_z)} R0 FMAX S{int(activation_speed_rpm)} M3 ; Spindel einschalten"
            )
        else:
            lines.append(f"L {fmt_axis('Z', spin_z)} R0 FMAX M3 ; Spindel einschalten")
        lines.append(f"L {fmt_axis('Z', z_values['z_clearance'])} R0 FMAX {m_act} ; Messer unten aktivieren")
        lines.append("CYCL DEF 9.0 VERWEILZEIT")
        lines.append(f"CYCL DEF 9.1 V.ZEIT {dwell_time:.1f}")

        if self.reduce_approach_var.get():
            if self.z0_var.get() == "Z0 ist Unterkante Bund":
                z_app = z_values["z_sink_finish"] - 2.0
            else:
                z_app = z_values["z_sink_finish"] + 2.0
            lines.append(f"L {fmt_axis('Z', z_app)} R0 F{feed_rate:.0f} ; Vorposition vor Kontakt")
            lines.append(f"L {fmt_axis('Z', z_values['z_sink_finish'])} R0 F{feed_rate * 0.5:.0f} ; Senken mit 50 Prozent Vorschub")
        else:
            lines.append(f"L {fmt_axis('Z', z_values['z_sink_finish'])} R0 F{feed_rate:.0f} ; Senken auf Fertigmass")

        lines.append(f"L {fmt_axis('Z', z_values['z_clearance'])} R0 FMAX ; Unten freifahren")
        lines.append("M5 ; Spindel aus")
        lines.append(f"{m_deact} ; Messer schliessen")
        lines.append(f"L {fmt_axis('Z', common['safe_z'])} R0 FMAX ; Aus der Bohrung")
        return lines

    # ------------------------------------------------------------------
    # Zwischenablage / Export / Druck
    # ------------------------------------------------------------------

    def copy_to_clipboard(self) -> None:
        code = self._require_current_nc_for_output()
        if not code:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        messagebox.showinfo("Info", "Code erfolgreich kopiert.")

    def export_to_h(self) -> None:
        code = self._require_current_nc_for_output()
        if not code:
            return

        default_name = clean_program_name(self.entries["program_name"].get(), "NC_PROGRAMM") + ".H"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".H",
            initialfile=default_name,
            filetypes=[("Heidenhain Klartext", "*.H"), ("Alle Dateien", "*.*")],
            title="Speichern unter",
        )

        if not file_path:
            return

        try:
            # Kommentare sind bewusst ASCII gehalten. cp1252 ist fuer viele Windows/TNC-Workflows praktisch.
            with open(file_path, "w", encoding="cp1252", errors="replace") as f:
                f.write(code + "\n")
            messagebox.showinfo("Erfolg", "Datei als *.H exportiert.")
        except Exception as exc:
            messagebox.showerror("Fehler", str(exc))

    def print_code(self) -> None:
        code = self.output_text.get("1.0", tk.END).strip()
        if not code:
            messagebox.showwarning("Warnung", "Kein NC-Code vorhanden.")
            return

        try:
            temp_dir = os.environ.get("TEMP", os.getcwd())
            temp_file = os.path.join(temp_dir, "nc_code_print.txt")
            with open(temp_file, "w", encoding="cp1252", errors="replace") as f:
                f.write(f"PROGRAMM: {clean_program_name(self.entries['program_name'].get(), 'NC_PROGRAMM')}\n")
                f.write(f"DATUM: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                f.write(code)

            if os.name == "nt":
                os.startfile(temp_file, "print")  # type: ignore[attr-defined]
                messagebox.showinfo("Drucker", "An Windows-Standarddrucker gesendet.")
            else:
                messagebox.showinfo("Drucker", f"Druckdatei erstellt: {temp_file}")
        except Exception as exc:
            messagebox.showerror("Druckfehler", str(exc))


class _BGFPositionDialog(simpledialog.Dialog):
    def __init__(
        self,
        parent,
        title: str,
        *,
        default_thread_depth: float,
        initial: Optional[BGFCoordinatePosition] = None,
    ):
        self.default_thread_depth = default_thread_depth
        self.initial = initial
        self.result: Optional[BGFCoordinatePosition] = None
        super().__init__(parent, title=title)

    def body(self, master):
        fields = [
            ("X [mm]", "x", "0"),
            ("Y [mm]", "y", "0"),
            ("Z Bohrungsanfang [mm]", "sz", "0"),
            ("Gewindetiefe [mm]", "td", f"{self.default_thread_depth:g}"),
            ("Kernlochtiefe Soll [mm] (optional)", "ch", ""),
        ]
        if self.initial is not None:
            fields = [
                ("X [mm]", "x", f"{self.initial.x:g}"),
                ("Y [mm]", "y", f"{self.initial.y:g}"),
                ("Z Bohrungsanfang [mm]", "sz", f"{self.initial.surface_z:g}"),
                ("Gewindetiefe [mm]", "td", f"{self.initial.thread_depth:g}"),
                (
                    "Kernlochtiefe Soll [mm] (optional)",
                    "ch",
                    "" if self.initial.core_hole_depth is None else f"{self.initial.core_hole_depth:g}",
                ),
            ]

        self._entries: Dict[str, ttk.Entry] = {}
        for row, (label, key, value) in enumerate(fields):
            ttk.Label(master, text=label).grid(row=row, column=0, sticky=tk.W, pady=2, padx=(0, 8))
            entry = ttk.Entry(master, width=16)
            entry.insert(0, value)
            entry.grid(row=row, column=1, sticky=tk.W, pady=2)
            self._entries[key] = entry
        return self._entries["x"]

    def validate(self):
        def parse_required(key: str, caption: str) -> Optional[float]:
            raw = self._entries[key].get().strip()
            try:
                value = float(raw.replace(",", "."))
            except ValueError:
                messagebox.showerror("Fehler", f"{caption} muss numerisch sein.", parent=self)
                return None
            if not math.isfinite(value):
                messagebox.showerror("Fehler", f"{caption} darf nicht NaN/Infinity sein.", parent=self)
                return None
            return value

        x = parse_required("x", "X")
        y = parse_required("y", "Y")
        sz = parse_required("sz", "Bohrungsanfang Z")
        td = parse_required("td", "Gewindetiefe")
        if None in (x, y, sz, td):
            return False

        ch_raw = self._entries["ch"].get().strip()
        core: Optional[float] = None
        if ch_raw != "":
            try:
                core = float(ch_raw.replace(",", "."))
            except ValueError:
                messagebox.showerror("Fehler", "Kernlochtiefe Soll muss numerisch sein.", parent=self)
                return False
            if not math.isfinite(core):
                messagebox.showerror("Fehler", "Kernlochtiefe Soll darf nicht NaN/Infinity sein.", parent=self)
                return False

        self._parsed = BGFCoordinatePosition(
            x=x, y=y, surface_z=sz, thread_depth=td, core_hole_depth=core
        )
        return True

    def apply(self):
        self.result = self._parsed


class _XYPositionDialog(simpledialog.Dialog):
    def __init__(
        self,
        parent,
        title: str,
        *,
        initial: Optional[BSFCoordinatePosition] = None,
    ):
        self.initial = initial
        self.result: Optional[BSFCoordinatePosition] = None
        super().__init__(parent, title=title)

    def body(self, master):
        x_val = "0" if self.initial is None else f"{self.initial.x:g}"
        y_val = "0" if self.initial is None else f"{self.initial.y:g}"
        self._entries: Dict[str, ttk.Entry] = {}
        for row, (label, key, value) in enumerate(
            (("X [mm]", "x", x_val), ("Y [mm]", "y", y_val))
        ):
            ttk.Label(master, text=label).grid(row=row, column=0, sticky=tk.W, pady=2, padx=(0, 8))
            entry = ttk.Entry(master, width=16)
            entry.insert(0, value)
            entry.grid(row=row, column=1, sticky=tk.W, pady=2)
            self._entries[key] = entry
        return self._entries["x"]

    def validate(self):
        def parse_required(key: str, caption: str) -> Optional[float]:
            raw = self._entries[key].get().strip()
            try:
                value = float(raw.replace(",", "."))
            except ValueError:
                messagebox.showerror("Fehler", f"{caption} muss numerisch sein.", parent=self)
                return None
            if not math.isfinite(value):
                messagebox.showerror("Fehler", f"{caption} darf nicht NaN/Infinity sein.", parent=self)
                return None
            return value

        x = parse_required("x", "X")
        y = parse_required("y", "Y")
        if None in (x, y):
            return False
        self._parsed = BSFCoordinatePosition(x=x, y=y)
        return True

    def apply(self):
        self.result = self._parsed


class _CoordinatePasteDialog(simpledialog.Dialog):
    def __init__(self, parent, hint: Optional[str] = None):
        self.result_text: Optional[str] = None
        self._hint = hint or (
            "Eine Position pro Zeile (Semikolon oder Tab):\n"
            "3 Spalten: X;Y;Z\n"
            "4 Spalten: X;Y;Z;Gewindetiefe\n"
            "5 Spalten: X;Y;Z;Gewindetiefe;Kernloch"
        )
        super().__init__(parent, title="Koordinaten einfuegen")

    def body(self, master):
        ttk.Label(master, text=self._hint).pack(anchor=tk.W)
        self.text = tk.Text(master, width=56, height=12, font=("Consolas", 10))
        self.text.pack(fill=tk.BOTH, expand=True, pady=4)
        return self.text

    def apply(self):
        self.result_text = self.text.get("1.0", tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    app = BSFGeneratorGUI(root)
    root.mainloop()
