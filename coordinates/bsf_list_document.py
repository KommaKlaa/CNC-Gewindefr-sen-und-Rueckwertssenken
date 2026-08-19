"""Natives HEULE-BSF-Positionslistenformat (.bsf.json).

Version 2 speichert das gewaehlte HEULE-Werkzeugprofil ueber seinen stabilen Key.
Version 3 erweitert das workpiece-Modell um raw_surface_z (optional).
Legacy-Version 1 wird weiterhin geladen, aber ohne Auto-Mapping auf ein Profil.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Sequence, Tuple

from bsf_chain import BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE, BSF_END_MODE_VALUES, validate_bsf_end_mode
from heule_bsf_tools import BSF_TOOL_PROFILES, profile_by_key
from nc_programmer import ProgrammerError, normalize_programmer

from .bsf_position import BSFCoordinatePosition

FORMAT_NAME = "HEULE_BSF_POSITION_LIST"
FORMAT_VERSION = 3
MAX_BSF_POSITIONS = 10_000
MAX_FILE_BYTES = 5_000_000

Z_REF_BOTTOM = "BOTTOM_EDGE"
Z_REF_TOP = "TOP_EDGE"
ALLOWED_Z_REFERENCES = (Z_REF_BOTTOM, Z_REF_TOP)

Z0_LABEL_BOTTOM = "Z0 ist Unterkante Bund"
Z0_LABEL_TOP = "Z0 ist Oberkante Bund"

ACTIVATE_PRESETS = (
    "IKZ Ein (M7)",
    "IKZ Ein (M8)",
    "Innenluft Ein (M89)",
    "Freitext / Eigener M-Befehl",
)
DEACTIVATE_PRESETS = (
    "Alles AUS (M9)",
    "Eigener M-Befehl",
)

APPROACH_FEED_FACTOR_REDUCED = 0.5
APPROACH_FEED_FACTOR_FULL = 1.0

NEWER_VERSION_MESSAGE = (
    "Diese HEULE-BSF-Datei wurde mit einer neueren Formatversion erstellt "
    "und kann nicht sicher geladen werden."
)


class BSFDocumentError(Exception):
    """Benutzerverstaendlicher Persistenzfehler (kein Traceback in der GUI)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class BSFPositionListDocument:
    version: int
    program_name: str
    tool_number: int
    blank_size: float
    blank_height: float
    z_reference: str
    tool_profile_key: str | None
    bund_thickness: float
    sink_finish: float
    clearance: float
    spindle_speed: int
    feed: float
    dwell_time: float
    reduce_approach: bool
    approach_feed_factor: float
    activate_preset: str
    activate_custom: str
    deactivate_preset: str
    deactivate_custom: str
    safe_z: float
    end_safe_z: float
    positions: Tuple[BSFCoordinatePosition, ...] = field(default_factory=tuple)
    programmer: str = ""
    reference_z: float = 0.0
    raw_stock_top_z: float = 0.0
    raw_surface_z: float | None = None
    end_mode: str = BSF_END_MODE_CHAIN

    @property
    def format_name(self) -> str:
        return FORMAT_NAME

    @property
    def z0_is_flange_bottom(self) -> bool:
        return self.z_reference == Z_REF_BOTTOM

    @property
    def z0_label(self) -> str:
        return Z0_LABEL_BOTTOM if self.z0_is_flange_bottom else Z0_LABEL_TOP


def _optional_programmer(raw: Any) -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise BSFDocumentError("Feld 'program.programmer' muss Text sein.")
    try:
        return normalize_programmer(raw)
    except ProgrammerError as exc:
        raise BSFDocumentError(f"Feld 'program.programmer': {exc.message}") from exc


def z_reference_from_label(label: str) -> str:
    text = (label or "").strip()
    if text == Z0_LABEL_BOTTOM:
        return Z_REF_BOTTOM
    if text == Z0_LABEL_TOP:
        return Z_REF_TOP
    raise BSFDocumentError("Z0-Definition ist unbekannt.")


def _require_finite(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BSFDocumentError(f"Feld '{field_name}' muss eine Zahl sein.")
    number = float(value)
    if not math.isfinite(number):
        raise BSFDocumentError(f"Feld '{field_name}' darf nicht NaN/Infinity sein.")
    return number


def _require_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BSFDocumentError(f"Feld '{field_name}' muss eine ganze Zahl sein.")
    if float(value) != int(value):
        raise BSFDocumentError(f"Feld '{field_name}' muss eine ganze Zahl sein.")
    return int(value)


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BSFDocumentError(f"Feld '{field_name}' fehlt oder ist leer.")
    return value.strip()


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise BSFDocumentError(f"Feld '{field_name}' muss true oder false sein.")
    return value


def _parse_tool_profile_key(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise BSFDocumentError("tool.profile fehlt oder ist leer.")
    key = raw.strip()
    if key not in BSF_TOOL_PROFILES:
        raise BSFDocumentError(f"Unbekanntes HEULE-Werkzeugprofil '{key}'.")
    return key


def _parse_z_reference(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise BSFDocumentError("workpiece.z_reference fehlt oder ist leer.")
    name = raw.strip()
    if name not in ALLOWED_Z_REFERENCES:
        raise BSFDocumentError(
            f"Unbekannte Z0-Referenz '{name}'. "
            f"Erlaubt: {', '.join(ALLOWED_Z_REFERENCES)}."
        )
    return name


def _parse_position(raw: Any, index: int) -> BSFCoordinatePosition:
    if not isinstance(raw, dict):
        raise BSFDocumentError(f"Position {index} ist kein Objekt.")
    extra_depth = [key for key in ("surface_z", "thread_depth", "core_hole_depth") if key in raw]
    if extra_depth:
        raise BSFDocumentError(
            f"Position {index} enthaelt BGF-Tiefenfelder, die in HEULE BSF nicht erlaubt sind."
        )
    try:
        x = _require_finite(raw.get("x"), f"Position {index}.x")
        y = _require_finite(raw.get("y"), f"Position {index}.y")
    except BSFDocumentError as exc:
        raise BSFDocumentError(f"Position {index} enthaelt ungueltige Daten: {exc.message}") from exc
    return BSFCoordinatePosition(x=x, y=y)


def document_to_dict(doc: BSFPositionListDocument) -> Dict[str, Any]:
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "program": {
            "name": doc.program_name,
            "programmer": doc.programmer,
            "tool_number": doc.tool_number,
            "blank_size": doc.blank_size,
            "blank_height": doc.blank_height,
            "raw_stock_top_z": doc.raw_stock_top_z,
        },
        "workpiece": {
            "z_reference": doc.z_reference,
            "reference_z": doc.reference_z,
            "bund_thickness": doc.bund_thickness,
            "sink_finish": doc.sink_finish,
            "clearance": doc.clearance,
            "raw_surface_z": doc.raw_surface_z,
        },
        "tool": {
            "profile": doc.tool_profile_key,
        },
        "process": {
            "spindle_speed": doc.spindle_speed,
            "feed": doc.feed,
            "dwell_time": doc.dwell_time,
            "reduce_approach": doc.reduce_approach,
            "approach_feed_factor": doc.approach_feed_factor,
        },
        "machine": {
            "activate_preset": doc.activate_preset,
            "activate_custom": doc.activate_custom,
            "deactivate_preset": doc.deactivate_preset,
            "deactivate_custom": doc.deactivate_custom,
        },
        "safety": {
            "safe_z": doc.safe_z,
            "end_safe_z": doc.end_safe_z,
        },
        "positions": [{"x": p.x, "y": p.y} for p in doc.positions],
        "program_end": {
            "end_mode": doc.end_mode,
        },
    }


def parse_document_dict(data: Any) -> BSFPositionListDocument:
    if not isinstance(data, dict):
        raise BSFDocumentError("Die Datei ist kein gueltiges HEULE-BSF-Positionslistenformat.")

    fmt = data.get("format")
    if fmt != FORMAT_NAME:
        raise BSFDocumentError("Die Datei ist kein gueltiges HEULE-BSF-Positionslistenformat.")

    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise BSFDocumentError("Formatversion fehlt oder ist ungueltig.")
    if version > FORMAT_VERSION:
        raise BSFDocumentError(NEWER_VERSION_MESSAGE)
    if version < 1:
        raise BSFDocumentError(f"Unbekannte Formatversion: {version}")

    program = data.get("program")
    if not isinstance(program, dict):
        raise BSFDocumentError("Abschnitt 'program' fehlt oder ist ungueltig.")
    program_name = _require_str(program.get("name"), "program.name")
    programmer = _optional_programmer(program.get("programmer"))
    tool_number = _require_int(program.get("tool_number"), "program.tool_number")
    if tool_number <= 0:
        raise BSFDocumentError("Werkzeugnummer T muss groesser 0 sein.")
    blank_size = _require_finite(program.get("blank_size", 1000.0), "program.blank_size")
    blank_height = _require_finite(program.get("blank_height", 60.0), "program.blank_height")
    raw_stock_top_z = _require_finite(program.get("raw_stock_top_z", 0.0), "program.raw_stock_top_z")

    workpiece = data.get("workpiece")
    if not isinstance(workpiece, dict):
        raise BSFDocumentError("Abschnitt 'workpiece' fehlt oder ist ungueltig.")
    z_reference = _parse_z_reference(workpiece.get("z_reference"))
    if "reference_z" in workpiece:
        reference_z = _require_finite(workpiece.get("reference_z"), "workpiece.reference_z")
    else:
        reference_z = 0.0
    bund_thickness = _require_finite(workpiece.get("bund_thickness"), "workpiece.bund_thickness")
    sink_finish = _require_finite(workpiece.get("sink_finish"), "workpiece.sink_finish")
    clearance = _require_finite(workpiece.get("clearance"), "workpiece.clearance")
    if "raw_surface_z" in workpiece:
        raw_surface_raw = workpiece.get("raw_surface_z")
        if raw_surface_raw is None:
            raw_surface_z = None
        else:
            raw_surface_z = _require_finite(raw_surface_raw, "workpiece.raw_surface_z")
    else:
        raw_surface_z = None

    tool_profile_key: str | None = None
    if version >= 2:
        tool = data.get("tool")
        if not isinstance(tool, dict):
            raise BSFDocumentError("Abschnitt 'tool' fehlt oder ist ungueltig.")
        tool_profile_key = _parse_tool_profile_key(tool.get("profile"))
    else:
        blade = data.get("blade")
        if not isinstance(blade, dict):
            raise BSFDocumentError("Abschnitt 'blade' fehlt oder ist ungueltig.")
        # Legacy v1: Blade-Daten bewusst NICHT in ein neues Profil mappen.
        _require_finite(blade.get("thickness"), "blade.thickness")
        if not isinstance(blade.get("measurement_reference"), str):
            raise BSFDocumentError("blade.measurement_reference fehlt oder ist leer.")

    process = data.get("process")
    if not isinstance(process, dict):
        raise BSFDocumentError("Abschnitt 'process' fehlt oder ist ungueltig.")
    spindle_speed = _require_int(process.get("spindle_speed"), "process.spindle_speed")
    feed = _require_finite(process.get("feed"), "process.feed")
    dwell_time = _require_finite(process.get("dwell_time"), "process.dwell_time")
    reduce_approach = _require_bool(process.get("reduce_approach"), "process.reduce_approach")
    approach_feed_factor = _require_finite(
        process.get(
            "approach_feed_factor",
            APPROACH_FEED_FACTOR_REDUCED if reduce_approach else APPROACH_FEED_FACTOR_FULL,
        ),
        "process.approach_feed_factor",
    )

    machine = data.get("machine")
    if not isinstance(machine, dict):
        raise BSFDocumentError("Abschnitt 'machine' fehlt oder ist ungueltig.")
    activate_preset = _require_str(machine.get("activate_preset"), "machine.activate_preset")
    if activate_preset not in ACTIVATE_PRESETS:
        raise BSFDocumentError(f"Unbekannte Messer-Aktivierung '{activate_preset}'.")
    deactivate_preset = _require_str(machine.get("deactivate_preset"), "machine.deactivate_preset")
    if deactivate_preset not in DEACTIVATE_PRESETS:
        raise BSFDocumentError(f"Unbekannte Messer-Deaktivierung '{deactivate_preset}'.")
    activate_custom = machine.get("activate_custom", "")
    deactivate_custom = machine.get("deactivate_custom", "")
    if not isinstance(activate_custom, str):
        raise BSFDocumentError("machine.activate_custom muss Text sein.")
    if not isinstance(deactivate_custom, str):
        raise BSFDocumentError("machine.deactivate_custom muss Text sein.")
    activate_custom = activate_custom.strip()
    deactivate_custom = deactivate_custom.strip()
    if activate_preset == "Freitext / Eigener M-Befehl" and not activate_custom:
        raise BSFDocumentError("Eigener M-Befehl fuer Messer-Aktivierung fehlt.")
    if deactivate_preset == "Eigener M-Befehl" and not deactivate_custom:
        raise BSFDocumentError("Eigener M-Befehl fuer Messer-Deaktivierung fehlt.")

    safety = data.get("safety")
    if not isinstance(safety, dict):
        raise BSFDocumentError("Abschnitt 'safety' fehlt oder ist ungueltig.")
    safe_z = _require_finite(safety.get("safe_z"), "safety.safe_z")
    end_safe_z = _require_finite(safety.get("end_safe_z"), "safety.end_safe_z")

    positions_raw = data.get("positions")
    if not isinstance(positions_raw, list):
        raise BSFDocumentError("Abschnitt 'positions' fehlt oder ist ungueltig.")
    if len(positions_raw) > MAX_BSF_POSITIONS:
        raise BSFDocumentError(
            f"Zu viele Positionen ({len(positions_raw)}). Maximum: {MAX_BSF_POSITIONS}."
        )
    if len(positions_raw) == 0:
        raise BSFDocumentError("Die Positionsliste enthaelt keine Positionen.")

    positions = tuple(_parse_position(item, idx) for idx, item in enumerate(positions_raw, start=1))

    program_end = data.get("program_end")
    if program_end is None:
        # Legacy-Datei ohne end_mode: STANDALONE_M30 erhalten altes Verhalten.
        end_mode = BSF_END_MODE_STANDALONE
    else:
        if not isinstance(program_end, dict):
            raise BSFDocumentError("Abschnitt 'program_end' ist ungueltig.")
        raw_end_mode = program_end.get("end_mode")
        if not isinstance(raw_end_mode, str) or not raw_end_mode.strip():
            raise BSFDocumentError("Feld 'program_end.end_mode' fehlt oder ist leer.")
        try:
            end_mode = validate_bsf_end_mode(raw_end_mode.strip())
        except ValueError:
            raise BSFDocumentError(
                f"Ungueltiger BSF-Endmodus '{raw_end_mode}'. "
                f"Erlaubt: {', '.join(BSF_END_MODE_VALUES)}."
            )

    return BSFPositionListDocument(
        version=version,
        program_name=program_name,
        tool_number=tool_number,
        blank_size=blank_size,
        blank_height=blank_height,
        raw_stock_top_z=raw_stock_top_z,
        z_reference=z_reference,
        tool_profile_key=tool_profile_key,
        reference_z=reference_z,
        bund_thickness=bund_thickness,
        sink_finish=sink_finish,
        clearance=clearance,
        spindle_speed=spindle_speed,
        feed=feed,
        dwell_time=dwell_time,
        reduce_approach=reduce_approach,
        approach_feed_factor=approach_feed_factor,
        activate_preset=activate_preset,
        activate_custom=activate_custom,
        deactivate_preset=deactivate_preset,
        deactivate_custom=deactivate_custom,
        safe_z=safe_z,
        end_safe_z=end_safe_z,
        positions=positions,
        programmer=programmer,
        raw_surface_z=raw_surface_z,
        end_mode=end_mode,
    )


def save_bsf_document_json(path: str, doc: BSFPositionListDocument) -> None:
    payload = document_to_dict(doc)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def load_bsf_document_json(path: str) -> BSFPositionListDocument:
    if not os.path.isfile(path):
        raise BSFDocumentError("Die Datei wurde nicht gefunden.")
    size = os.path.getsize(path)
    if size > MAX_FILE_BYTES:
        raise BSFDocumentError(
            f"Die Datei ist zu gross ({size} Bytes). Maximum: {MAX_FILE_BYTES} Bytes."
        )
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw_text = handle.read()
    except OSError as exc:
        raise BSFDocumentError(f"Datei konnte nicht gelesen werden: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise BSFDocumentError("Dateiencoding ungueltig (erwartet UTF-8).") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise BSFDocumentError(
            f"Die Datei enthaelt kein gueltiges JSON (Zeile {exc.lineno})."
        ) from exc

    return parse_document_dict(data)


def build_bsf_document(
    *,
    program_name: str,
    tool_number: int,
    blank_size: float,
    blank_height: float,
    z_reference: str,
    tool_profile_key: str,
    bund_thickness: float,
    sink_finish: float,
    clearance: float,
    spindle_speed: int,
    feed: float,
    dwell_time: float,
    reduce_approach: bool,
    approach_feed_factor: float,
    activate_preset: str,
    activate_custom: str,
    deactivate_preset: str,
    deactivate_custom: str,
    safe_z: float,
    end_safe_z: float,
    positions: Sequence[BSFCoordinatePosition],
    programmer: str = "",
    reference_z: float = 0.0,
    raw_stock_top_z: float = 0.0,
    raw_surface_z: float | None = None,
    end_mode: str = BSF_END_MODE_CHAIN,
) -> BSFPositionListDocument:
    if raw_surface_z is not None and not math.isfinite(raw_surface_z):
        raise BSFDocumentError("Rohflaeche / Ist-Z ist nicht endlich.")
    try:
        end_mode = validate_bsf_end_mode(end_mode)
    except ValueError:
        raise BSFDocumentError(
            f"Ungueltiger BSF-Endmodus '{end_mode}'. "
            f"Erlaubt: {', '.join(BSF_END_MODE_VALUES)}."
        )
    if not positions:
        raise BSFDocumentError("Keine Bearbeitungspositionen vorhanden.")
    if len(positions) > MAX_BSF_POSITIONS:
        raise BSFDocumentError(f"Zu viele Positionen. Maximum: {MAX_BSF_POSITIONS}.")
    if z_reference not in ALLOWED_Z_REFERENCES:
        raise BSFDocumentError("Z0-Definition ist unbekannt.")
    if activate_preset not in ACTIVATE_PRESETS:
        raise BSFDocumentError("Unbekannte Messer-Aktivierung.")
    if deactivate_preset not in DEACTIVATE_PRESETS:
        raise BSFDocumentError("Unbekannte Messer-Deaktivierung.")
    if tool_number <= 0:
        raise BSFDocumentError("Werkzeugnummer T muss groesser 0 sein.")
    if not tool_profile_key or profile_by_key(tool_profile_key) is None:
        raise BSFDocumentError("HEULE_TOOL_SELECTION_REQUIRED")
    try:
        programmer_norm = normalize_programmer(programmer)
    except ProgrammerError as exc:
        raise BSFDocumentError(f"Programmierer: {exc.message}") from exc
    for idx, pos in enumerate(positions, start=1):
        if not math.isfinite(pos.x) or not math.isfinite(pos.y):
            raise BSFDocumentError(f"Position {idx}: X/Y ist nicht endlich.")
    for name, value in (
        ("Bunddicke", bund_thickness),
        ("Senk-Fertigmaß", sink_finish),
        ("Freifahrt", clearance),
        ("Vorschub", feed),
        ("Wartezeit", dwell_time),
        ("Anschnittfaktor", approach_feed_factor),
        ("Sicherheits-Z", safe_z),
        ("End-Sicherheits-Z", end_safe_z),
        ("Rohteil-Kantenlaenge", blank_size),
        ("Rohteil-Hoehe", blank_height),
        ("Rohteil-Oberkante Z", raw_stock_top_z),
        ("Z-Lage Bezugsebene", reference_z),
    ):
        if not math.isfinite(value):
            raise BSFDocumentError(f"{name} ist nicht endlich.")
    return BSFPositionListDocument(
        version=FORMAT_VERSION,
        program_name=program_name,
        tool_number=int(tool_number),
        blank_size=float(blank_size),
        blank_height=float(blank_height),
        raw_stock_top_z=float(raw_stock_top_z),
        z_reference=z_reference,
        tool_profile_key=tool_profile_key,
        bund_thickness=float(bund_thickness),
        sink_finish=float(sink_finish),
        clearance=float(clearance),
        spindle_speed=int(spindle_speed),
        feed=float(feed),
        dwell_time=float(dwell_time),
        reduce_approach=bool(reduce_approach),
        approach_feed_factor=float(approach_feed_factor),
        activate_preset=activate_preset,
        activate_custom=(activate_custom or "").strip(),
        deactivate_preset=deactivate_preset,
        deactivate_custom=(deactivate_custom or "").strip(),
        safe_z=float(safe_z),
        end_safe_z=float(end_safe_z),
        positions=tuple(positions),
        programmer=programmer_norm,
        reference_z=float(reference_z),
        raw_surface_z=float(raw_surface_z) if raw_surface_z is not None else None,
        end_mode=end_mode,
    )
