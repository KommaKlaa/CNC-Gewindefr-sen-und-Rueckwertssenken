"""CSV Import/Export fuer BGF-Koordinatenlisten."""

from __future__ import annotations

import csv
import io
from typing import List, Optional, Sequence, Tuple

from .bgf_list_parser import parse_bgf_coordinate_line, parse_bgf_coordinate_text
from .bgf_position import BGFCoordinatePosition
from .parser import CoordinateParseError, _split_fields, parse_number

CSV_HEADER = ["Nr", "X", "Y", "Z_Oberflaeche", "Gewindetiefe", "Kernlochtiefe"]
MAX_CSV_POSITIONS = 10_000


def _normalize_header_token(token: str) -> str:
    text = token.strip().lower()
    repl = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        " ": "_",
        "-": "_",
    }
    for src, dst in repl.items():
        text = text.replace(src, dst)
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def _classify_header(fields: Sequence[str]) -> Optional[dict]:
    """Erkennt bekannte Header. Liefert Spaltenzuordnung oder None (kein Header)."""
    norms = [_normalize_header_token(f) for f in fields]
    joined = "|".join(norms)
    # Kein Header, wenn alle Felder numerisch aussehen
    numeric_looking = 0
    for f in fields:
        try:
            parse_number(f, line_no=0, raw_line=f)
            numeric_looking += 1
        except CoordinateParseError:
            pass
    if numeric_looking == len(fields) and len(fields) >= 3:
        return None

    aliases = {
        "nr": {"nr", "nr.", "no", "nummer", "n"},
        "x": {"x"},
        "y": {"y"},
        "surface_z": {
            "z_oberflaeche",
            "zoberflaeche",
            "surface_z",
            "surfacez",
            "z",
        },
        "thread_depth": {"gewindetiefe", "threaddepth", "thread_depth"},
        "core_hole_depth": {
            "kernlochtiefe",
            "kernloch",
            "coreholedepth",
            "core_hole_depth",
            "core_hole",
        },
    }

    mapping: dict = {}
    for idx, token in enumerate(norms):
        matched = None
        for key, names in aliases.items():
            if token in names:
                matched = key
                break
        if matched is None:
            raise CoordinateParseError(
                [
                    f"CSV-Header unbekannt/mehrdeutig: Spalte '{fields[idx]}' "
                    f"(Header: {joined})"
                ]
            )
        if matched in mapping:
            raise CoordinateParseError(
                [f"CSV-Header doppelt: '{matched}'"]
            )
        mapping[matched] = idx

    required = {"x", "y", "surface_z", "thread_depth"}
    if not required.issubset(mapping.keys()):
        missing = ", ".join(sorted(required - set(mapping.keys())))
        raise CoordinateParseError(
            [f"CSV-Header unvollstaendig. Fehlend: {missing}"]
        )
    return mapping


def export_bgf_csv(positions: Sequence[BGFCoordinatePosition]) -> str:
    """Semikolon, Header, Dezimalpunkt, utf-8-sig geeignet (BOM separat beim Schreiben)."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_HEADER)
    for idx, pos in enumerate(positions, start=1):
        core = "" if pos.core_hole_depth is None else f"{pos.core_hole_depth:.3f}"
        writer.writerow(
            [
                str(idx),
                f"{pos.x:.3f}",
                f"{pos.y:.3f}",
                f"{pos.surface_z:.3f}",
                f"{pos.thread_depth:.3f}",
                core,
            ]
        )
    return buf.getvalue()


def _parse_row_by_mapping(
    parts: List[str],
    mapping: dict,
    line_no: int,
    raw_line: str,
) -> BGFCoordinatePosition:
    def get(key: str) -> str:
        idx = mapping[key]
        if idx >= len(parts):
            raise CoordinateParseError(
                [f"CSV-Zeile {line_no}: Spalte {key} fehlt."]
            )
        return parts[idx]

    def num(key: str, label: str) -> float:
        token = get(key)
        try:
            return parse_number(token, line_no=line_no, raw_line=raw_line)
        except CoordinateParseError:
            raise CoordinateParseError(
                [f'CSV-Zeile {line_no}: Spalte {label} enthaelt keinen gueltigen Zahlenwert ("{token}").']
            ) from None

    x = num("x", "X")
    y = num("y", "Y")
    surface_z = num("surface_z", "Z_Oberflaeche")
    thread_depth = num("thread_depth", "Gewindetiefe")

    core: Optional[float] = None
    if "core_hole_depth" in mapping:
        token = get("core_hole_depth").strip()
        if token != "":
            try:
                core = parse_number(token, line_no=line_no, raw_line=raw_line)
            except CoordinateParseError:
                raise CoordinateParseError(
                    [
                        f'CSV-Zeile {line_no}: Spalte Kernlochtiefe enthaelt keinen '
                        f'gueltigen Zahlenwert ("{token}").'
                    ]
                ) from None

    return BGFCoordinatePosition(
        x=x,
        y=y,
        surface_z=surface_z,
        thread_depth=thread_depth,
        core_hole_depth=core,
    )


def import_bgf_csv_text(
    text: str,
    *,
    default_thread_depth: float,
) -> List[BGFCoordinatePosition]:
    """Parst CSV atomar. Unterstuetzt Header, ohne Nr., Headerless 3/4/5 Spalten."""
    if text.startswith("\ufeff"):
        text = text[1:]

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # Trailing empty lines remove for emptiness check but keep line numbers
    content_indices = [i for i, line in enumerate(lines) if line.strip()]
    if not content_indices:
        raise CoordinateParseError(["Keine gueltigen Koordinaten gefunden."])

    first_idx = content_indices[0]
    first_line = lines[first_idx].strip()
    first_parts = [p for p in _split_fields(first_line) if p != ""]

    mapping: Optional[dict] = None
    try:
        mapping = _classify_header(first_parts)
    except CoordinateParseError:
        # Wenn es wie Header aussieht (nicht rein numerisch), Fehler durchreichen
        numeric_looking = 0
        for f in first_parts:
            try:
                parse_number(f, line_no=0, raw_line=f)
                numeric_looking += 1
            except CoordinateParseError:
                pass
        if numeric_looking < len(first_parts):
            raise
        mapping = None

    errors: List[str] = []
    result: List[BGFCoordinatePosition] = []

    if mapping is not None:
        data_line_indices = content_indices[1:]
        if not data_line_indices:
            raise CoordinateParseError(["CSV enthaelt nur einen Header, keine Datenzeilen."])
        for line_idx in data_line_indices:
            physical_no = line_idx + 1
            raw = lines[line_idx].strip()
            if not raw or raw.startswith("#"):
                continue
            parts = [p for p in _split_fields(raw)]
            # trailing empty from split keep for index mapping; strip only values
            parts = [p.strip() for p in parts]
            # drop pure trailing empties beyond last mapped index
            max_idx = max(mapping.values())
            while len(parts) <= max_idx:
                parts.append("")
            try:
                pos = _parse_row_by_mapping(parts, mapping, physical_no, raw)
            except CoordinateParseError as exc:
                errors.extend(exc.messages)
                continue
            result.append(pos)
    else:
        # Headerless: 3/4/5 Spalten, optional fuehrende Nr-Spalte (6 Werte)
        for line_idx in content_indices:
            physical_no = line_idx + 1
            raw = lines[line_idx]
            stripped = raw.strip()
            parts = [p for p in _split_fields(stripped) if p != ""]
            try:
                if len(parts) == 6:
                    # Nr;X;Y;Z;Gewinde;Kernloch ohne Header
                    line_body = ";".join(parts[1:])
                    pos = parse_bgf_coordinate_line(
                        line_body, physical_no, default_thread_depth=default_thread_depth
                    )
                else:
                    pos = parse_bgf_coordinate_line(
                        raw, physical_no, default_thread_depth=default_thread_depth
                    )
            except CoordinateParseError as exc:
                remapped = []
                for msg in exc.messages:
                    if msg.startswith("Zeile "):
                        remapped.append("CSV-" + msg)
                    else:
                        remapped.append(msg)
                errors.extend(remapped)
                continue
            if pos is not None:
                result.append(pos)

    if errors:
        raise CoordinateParseError(errors)
    if not result:
        raise CoordinateParseError(["Keine gueltigen Koordinaten gefunden."])
    if len(result) > MAX_CSV_POSITIONS:
        raise CoordinateParseError(
            [f"Zu viele Positionen ({len(result)}). Maximum: {MAX_CSV_POSITIONS}."]
        )
    return result


def write_bgf_csv_file(path: str, positions: Sequence[BGFCoordinatePosition]) -> None:
    text = export_bgf_csv(positions)
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write(text)


def read_bgf_csv_file(path: str, *, default_thread_depth: float) -> List[BGFCoordinatePosition]:
    with open(path, "r", encoding="utf-8-sig") as handle:
        text = handle.read()
    return import_bgf_csv_text(text, default_thread_depth=default_thread_depth)
