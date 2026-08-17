"""Natives HEULE-BSF-Positionslistenformat (.bsf.json) – Persistenz ohne Derived Data.

format = HEULE_BSF_POSITION_LIST, version = 1
Berechnete Z-Werte, Blade-Offset und Statusflags werden NICHT gespeichert.

SAVE_ALLOWED != NC_CODE_ALLOWED:
Ein syntaktisch vollstaendiges Projekt (endliche Zahlen, gueltige Enums,
BladeGeometry thickness > 0, mindestens eine XY-Position) darf gespeichert
und geladen werden. Unzureichendes safe_z bleibt ein korrigierbarer
Projektstatus (NC warnt/prueft spaeter). blade_thickness <= 0 oder unbekannte
Vermessreferenz sind strukturell ungueltig und blockieren Speichern/Laden.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Sequence, Tuple

from bsf_blade import (
    BladeMeasurementReference,
    build_bsf_blade_geometry,
    validate_blade_thickness,
)
from nc_programmer import ProgrammerError, normalize_programmer

from .bsf_position import BSFCoordinatePosition

FORMAT_NAME = "HEULE_BSF_POSITION_LIST"
FORMAT_VERSION = 1
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
    bund_thickness: float
    sink_finish: float
    clearance: float
    blade_thickness: float
    blade_measurement_reference: BladeMeasurementReference
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


def _parse_measurement_reference(raw: Any) -> BladeMeasurementReference:
    if not isinstance(raw, str) or not raw.strip():
        raise BSFDocumentError("blade.measurement_reference fehlt oder ist leer.")
    name = raw.strip()
    allowed = {item.name for item in BladeMeasurementReference}
    if name not in allowed:
        raise BSFDocumentError(
            f"Unbekannte Vermessreferenz '{name}'. "
            f"Erlaubt: {', '.join(sorted(allowed))}."
        )
    return BladeMeasurementReference[name]


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


def _validate_blade(thickness: float, reference: BladeMeasurementReference) -> None:
    err = validate_blade_thickness(thickness)
    if err:
        raise BSFDocumentError(err)
    try:
        build_bsf_blade_geometry(thickness, reference)
    except Exception as exc:
        raise BSFDocumentError(str(exc)) from exc


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
        },
        "workpiece": {
            "z_reference": doc.z_reference,
            "bund_thickness": doc.bund_thickness,
            "sink_finish": doc.sink_finish,
            "clearance": doc.clearance,
        },
        "blade": {
            "thickness": doc.blade_thickness,
            "measurement_reference": doc.blade_measurement_reference.name,
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

    workpiece = data.get("workpiece")
    if not isinstance(workpiece, dict):
        raise BSFDocumentError("Abschnitt 'workpiece' fehlt oder ist ungueltig.")
    z_reference = _parse_z_reference(workpiece.get("z_reference"))
    bund_thickness = _require_finite(workpiece.get("bund_thickness"), "workpiece.bund_thickness")
    sink_finish = _require_finite(workpiece.get("sink_finish"), "workpiece.sink_finish")
    clearance = _require_finite(workpiece.get("clearance"), "workpiece.clearance")

    blade = data.get("blade")
    if not isinstance(blade, dict):
        raise BSFDocumentError("Abschnitt 'blade' fehlt oder ist ungueltig.")
    blade_thickness = _require_finite(blade.get("thickness"), "blade.thickness")
    measurement_reference = _parse_measurement_reference(blade.get("measurement_reference"))
    _validate_blade(blade_thickness, measurement_reference)

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

    return BSFPositionListDocument(
        version=version,
        program_name=program_name,
        tool_number=tool_number,
        blank_size=blank_size,
        blank_height=blank_height,
        z_reference=z_reference,
        bund_thickness=bund_thickness,
        sink_finish=sink_finish,
        clearance=clearance,
        blade_thickness=blade_thickness,
        blade_measurement_reference=measurement_reference,
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
    bund_thickness: float,
    sink_finish: float,
    clearance: float,
    blade_thickness: float,
    blade_measurement_reference: BladeMeasurementReference,
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
) -> BSFPositionListDocument:
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
    try:
        programmer_norm = normalize_programmer(programmer)
    except ProgrammerError as exc:
        raise BSFDocumentError(f"Programmierer: {exc.message}") from exc
    _validate_blade(blade_thickness, blade_measurement_reference)
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
    ):
        if not math.isfinite(value):
            raise BSFDocumentError(f"{name} ist nicht endlich.")
    return BSFPositionListDocument(
        version=FORMAT_VERSION,
        program_name=program_name,
        tool_number=int(tool_number),
        blank_size=float(blank_size),
        blank_height=float(blank_height),
        z_reference=z_reference,
        bund_thickness=float(bund_thickness),
        sink_finish=float(sink_finish),
        clearance=float(clearance),
        blade_thickness=float(blade_thickness),
        blade_measurement_reference=blade_measurement_reference,
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
    )
