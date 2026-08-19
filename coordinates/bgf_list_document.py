"""Natives BGF-Positionslistenformat (.bgf.json) – Persistenz ohne Derived Data.

format = BGF_POSITION_LIST, version = 1
Herstellerdaten (Radius, Passes, Feeds) werden NICHT gespeichert.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from bgf_chain import BGF_END_MODE_CHAIN, validate_bgf_end_mode
from .bgf_position import BGFCoordinatePosition
from nc_programmer import ProgrammerError, normalize_programmer

FORMAT_NAME = "BGF_POSITION_LIST"
FORMAT_VERSION = 1
MAX_POSITIONS = 10_000
MAX_FILE_BYTES = 5_000_000


class BGFDocumentError(Exception):
    """Benutzerverständlicher Persistenzfehler (kein Traceback in der GUI)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class BGFPositionListDocument:
    version: int
    thread_size: str
    article_no: str
    tool_number: int
    program_name: str
    approach_clearance: float
    safe_z: float
    end_safe_z: float
    positions: Tuple[BGFCoordinatePosition, ...] = field(default_factory=tuple)
    programmer: str = ""
    end_mode: str = BGF_END_MODE_CHAIN

    @property
    def format_name(self) -> str:
        return FORMAT_NAME


def _optional_programmer(raw: Any) -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise BGFDocumentError("Feld 'program.programmer' muss Text sein.")
    try:
        return normalize_programmer(raw)
    except ProgrammerError as exc:
        raise BGFDocumentError(f"Feld 'program.programmer': {exc.message}") from exc


def _require_finite(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BGFDocumentError(f"Feld '{field_name}' muss eine Zahl sein.")
    number = float(value)
    if not math.isfinite(number):
        raise BGFDocumentError(f"Feld '{field_name}' darf nicht NaN/Infinity sein.")
    return number


def _require_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BGFDocumentError(f"Feld '{field_name}' muss eine ganze Zahl sein.")
    if float(value) != int(value):
        raise BGFDocumentError(f"Feld '{field_name}' muss eine ganze Zahl sein.")
    return int(value)


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BGFDocumentError(f"Feld '{field_name}' fehlt oder ist leer.")
    return value.strip()


def _parse_position(raw: Any, index: int) -> BGFCoordinatePosition:
    if not isinstance(raw, dict):
        raise BGFDocumentError(f"Position {index} ist kein Objekt.")
    try:
        x = _require_finite(raw.get("x"), f"Position {index}.x")
        y = _require_finite(raw.get("y"), f"Position {index}.y")
        surface_z = _require_finite(raw.get("surface_z"), f"Position {index}.surface_z")
        thread_depth = _require_finite(raw.get("thread_depth"), f"Position {index}.thread_depth")
    except BGFDocumentError as exc:
        raise BGFDocumentError(f"Position {index} enthaelt ungueltige Daten: {exc.message}") from exc

    core_raw = raw.get("core_hole_depth", None)
    if core_raw is None:
        core: Optional[float] = None
    else:
        core = _require_finite(core_raw, f"Position {index}.core_hole_depth")

    # Unbekannte Keys ignorieren (Derived Data aus aelteren Dateien)
    return BGFCoordinatePosition(
        x=x,
        y=y,
        surface_z=surface_z,
        thread_depth=thread_depth,
        core_hole_depth=core,
    )


def document_to_dict(doc: BGFPositionListDocument) -> Dict[str, Any]:
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "tool": {
            "thread_size": doc.thread_size,
            "article_no": doc.article_no,
            "tool_number": doc.tool_number,
        },
        "program": {
            "name": doc.program_name,
            "programmer": doc.programmer,
            "end_mode": doc.end_mode,
        },
        "safety": {
            "approach_clearance": doc.approach_clearance,
            "safe_z": doc.safe_z,
            "end_safe_z": doc.end_safe_z,
        },
        "positions": [
            {
                "x": p.x,
                "y": p.y,
                "surface_z": p.surface_z,
                "thread_depth": p.thread_depth,
                "core_hole_depth": p.core_hole_depth,
            }
            for p in doc.positions
        ],
    }


def parse_document_dict(data: Any) -> BGFPositionListDocument:
    if not isinstance(data, dict):
        raise BGFDocumentError("Die Datei ist kein gueltiges BGF-Positionslistenformat.")

    fmt = data.get("format")
    if fmt != FORMAT_NAME:
        raise BGFDocumentError(
            "Die Datei ist kein gueltiges BGF-Positionslistenformat."
        )

    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise BGFDocumentError("Formatversion fehlt oder ist ungueltig.")
    if version > FORMAT_VERSION:
        raise BGFDocumentError(
            "Diese Positionsliste wurde mit einer neueren Formatversion erstellt "
            "und kann mit dieser Programmversion nicht sicher geladen werden."
        )
    if version < 1:
        raise BGFDocumentError(f"Unbekannte Formatversion: {version}")

    tool = data.get("tool")
    if not isinstance(tool, dict):
        raise BGFDocumentError("Abschnitt 'tool' fehlt oder ist ungueltig.")
    thread_size = _require_str(tool.get("thread_size"), "tool.thread_size")
    article_no = _require_str(tool.get("article_no"), "tool.article_no")
    tool_number = _require_int(tool.get("tool_number", 8), "tool.tool_number")
    if tool_number <= 0:
        raise BGFDocumentError("Werkzeugnummer T muss groesser 0 sein.")

    program = data.get("program")
    if not isinstance(program, dict):
        raise BGFDocumentError("Abschnitt 'program' fehlt oder ist ungueltig.")
    program_name = _require_str(program.get("name"), "program.name")
    programmer = _optional_programmer(program.get("programmer"))
    end_mode = program.get("end_mode", BGF_END_MODE_CHAIN)
    if not isinstance(end_mode, str):
        raise BGFDocumentError("Feld 'program.end_mode' muss Text sein.")
    try:
        end_mode = validate_bgf_end_mode(end_mode)
    except ValueError as exc:
        raise BGFDocumentError(str(exc)) from exc

    safety = data.get("safety")
    if not isinstance(safety, dict):
        raise BGFDocumentError("Abschnitt 'safety' fehlt oder ist ungueltig.")
    approach_clearance = _require_finite(safety.get("approach_clearance"), "safety.approach_clearance")
    safe_z = _require_finite(safety.get("safe_z"), "safety.safe_z")
    end_safe_z = _require_finite(safety.get("end_safe_z"), "safety.end_safe_z")
    if approach_clearance <= 0:
        raise BGFDocumentError("Sicherheitsabstand ueber Oberflaeche muss groesser 0 sein.")

    positions_raw = data.get("positions")
    if not isinstance(positions_raw, list):
        raise BGFDocumentError("Abschnitt 'positions' fehlt oder ist ungueltig.")
    if len(positions_raw) > MAX_POSITIONS:
        raise BGFDocumentError(
            f"Zu viele Positionen ({len(positions_raw)}). Maximum: {MAX_POSITIONS}."
        )
    if len(positions_raw) == 0:
        raise BGFDocumentError("Die Positionsliste enthaelt keine Positionen.")

    positions = tuple(_parse_position(item, idx) for idx, item in enumerate(positions_raw, start=1))

    return BGFPositionListDocument(
        version=version,
        thread_size=thread_size,
        article_no=article_no,
        tool_number=tool_number,
        program_name=program_name,
        approach_clearance=approach_clearance,
        safe_z=safe_z,
        end_safe_z=end_safe_z,
        positions=positions,
        programmer=programmer,
        end_mode=end_mode,
    )


def resolve_tool_in_catalog(
    thread_size: str,
    article_no: str,
    catalog: Mapping[str, Any],
) -> str:
    """Liefert den BGF_DATA-Key bei eindeutigem Match; sonst Fehler."""
    matches: List[str] = []
    for key, data in catalog.items():
        size = getattr(data, "size", None)
        article = getattr(data, "article_no", None)
        if size == thread_size and article == article_no:
            matches.append(key)
    if not matches:
        raise BGFDocumentError(
            f"Werkzeug {thread_size} / Artikel {article_no} ist in dieser "
            "Programmversion nicht bekannt."
        )
    if len(matches) > 1:
        raise BGFDocumentError(
            f"Werkzeug {thread_size} / Artikel {article_no} ist nicht eindeutig."
        )
    return matches[0]


def save_document_json(path: str, doc: BGFPositionListDocument) -> None:
    payload = document_to_dict(doc)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def load_document_json(path: str) -> BGFPositionListDocument:
    if not os.path.isfile(path):
        raise BGFDocumentError("Die Datei wurde nicht gefunden.")
    size = os.path.getsize(path)
    if size > MAX_FILE_BYTES:
        raise BGFDocumentError(
            f"Die Datei ist zu gross ({size} Bytes). Maximum: {MAX_FILE_BYTES} Bytes."
        )
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw_text = handle.read()
    except OSError as exc:
        raise BGFDocumentError(f"Datei konnte nicht gelesen werden: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise BGFDocumentError("Dateiencoding ungueltig (erwartet UTF-8).") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise BGFDocumentError(
            f"Die Datei enthaelt kein gueltiges JSON (Zeile {exc.lineno})."
        ) from exc

    return parse_document_dict(data)


def build_document(
    *,
    thread_size: str,
    article_no: str,
    tool_number: int,
    program_name: str,
    approach_clearance: float,
    safe_z: float,
    end_safe_z: float,
    positions: Sequence[BGFCoordinatePosition],
    programmer: str = "",
    end_mode: str = BGF_END_MODE_CHAIN,
) -> BGFPositionListDocument:
    if not positions:
        raise BGFDocumentError("Keine Bearbeitungspositionen vorhanden.")
    if len(positions) > MAX_POSITIONS:
        raise BGFDocumentError(f"Zu viele Positionen. Maximum: {MAX_POSITIONS}.")
    try:
        programmer_norm = normalize_programmer(programmer)
    except ProgrammerError as exc:
        raise BGFDocumentError(f"Programmierer: {exc.message}") from exc
    try:
        end_mode = validate_bgf_end_mode(end_mode)
    except ValueError as exc:
        raise BGFDocumentError(str(exc)) from exc
    for idx, pos in enumerate(positions, start=1):
        for name, value in (
            ("X", pos.x),
            ("Y", pos.y),
            ("Z Bohrungsanfang", pos.surface_z),
            ("Gewindetiefe", pos.thread_depth),
        ):
            if not math.isfinite(value):
                raise BGFDocumentError(f"Position {idx}: {name} ist nicht endlich.")
        if pos.core_hole_depth is not None and not math.isfinite(pos.core_hole_depth):
            raise BGFDocumentError(f"Position {idx}: Kernlochtiefe ist nicht endlich.")
    return BGFPositionListDocument(
        version=FORMAT_VERSION,
        thread_size=thread_size,
        article_no=article_no,
        tool_number=tool_number,
        program_name=program_name,
        approach_clearance=approach_clearance,
        safe_z=safe_z,
        end_safe_z=end_safe_z,
        positions=tuple(positions),
        programmer=programmer_norm,
        end_mode=end_mode,
    )
