"""CSV Import/Export fuer HEULE-BSF-Koordinatenlisten (nur X/Y)."""

from __future__ import annotations

import csv
import io
from typing import List, Optional, Sequence

from .bsf_list_document import MAX_BSF_POSITIONS
from .bsf_position import BSFCoordinatePosition
from .parser import CoordinateParseError, _split_fields, parse_number

CSV_HEADER = ["Nr", "X", "Y"]


def _normalize_header_token(token: str) -> str:
    text = token.strip().lower()
    repl = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        " ": "_",
        "-": "_",
        ".": "",
    }
    for src, dst in repl.items():
        text = text.replace(src, dst)
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def _classify_header(fields: Sequence[str]) -> Optional[dict]:
    norms = [_normalize_header_token(f) for f in fields]
    numeric_looking = 0
    for field in fields:
        try:
            parse_number(field, line_no=0, raw_line=field)
            numeric_looking += 1
        except CoordinateParseError:
            pass
    if numeric_looking == len(fields) and len(fields) >= 2:
        return None

    aliases = {
        "nr": {"nr", "no", "nummer", "n"},
        "x": {"x"},
        "y": {"y"},
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
                [f"CSV-Header unbekannt: Spalte '{fields[idx]}'"]
            )
        if matched in mapping:
            raise CoordinateParseError([f"CSV-Header doppelt: '{matched}'"])
        mapping[matched] = idx
    if not {"x", "y"}.issubset(mapping.keys()):
        missing = ", ".join(sorted({"x", "y"} - set(mapping.keys())))
        raise CoordinateParseError([f"CSV-Header unvollstaendig. Fehlend: {missing}"])
    return mapping


def export_bsf_csv(positions: Sequence[BSFCoordinatePosition]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_HEADER)
    for idx, pos in enumerate(positions, start=1):
        writer.writerow([str(idx), f"{pos.x:.3f}", f"{pos.y:.3f}"])
    return buf.getvalue()


def _xy_from_parts(parts: List[str], mapping: Optional[dict], line_no: int, raw: str) -> BSFCoordinatePosition:
    if mapping is not None:
        def num(key: str, label: str) -> float:
            idx = mapping[key]
            if idx >= len(parts):
                raise CoordinateParseError([f"CSV-Zeile {line_no}: Spalte {label} fehlt."])
            token = parts[idx]
            try:
                return parse_number(token, line_no=line_no, raw_line=raw)
            except CoordinateParseError:
                raise CoordinateParseError(
                    [f'CSV-Zeile {line_no}: Spalte {label} enthaelt keinen gueltigen Zahlenwert ("{token}").']
                ) from None

        return BSFCoordinatePosition(x=num("x", "X"), y=num("y", "Y"))

    values = [p for p in parts if p != ""]
    if len(values) == 3:
        try:
            parse_number(values[0], line_no=line_no, raw_line=raw)
            x = parse_number(values[1], line_no=line_no, raw_line=raw)
            y = parse_number(values[2], line_no=line_no, raw_line=raw)
        except CoordinateParseError:
            raise CoordinateParseError(
                [f"CSV-Zeile {line_no}: erwartete Nr;X;Y oder X;Y (Zeile: '{raw}')."]
            ) from None
        return BSFCoordinatePosition(x=x, y=y)
    if len(values) != 2:
        raise CoordinateParseError(
            [
                f"CSV-Zeile {line_no}: erwartete genau 2 Werte (X Y), "
                f"gefunden {len(values)} (Zeile: '{raw}')"
            ]
        )
    try:
        x = parse_number(values[0], line_no=line_no, raw_line=raw)
        y = parse_number(values[1], line_no=line_no, raw_line=raw)
    except CoordinateParseError as exc:
        remapped = []
        for msg in exc.messages:
            remapped.append("CSV-" + msg if msg.startswith("Zeile ") else msg)
        raise CoordinateParseError(remapped) from None
    return BSFCoordinatePosition(x=x, y=y)


def import_bsf_csv_text(text: str) -> List[BSFCoordinatePosition]:
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    content_indices = [i for i, line in enumerate(lines) if line.strip()]
    if not content_indices:
        raise CoordinateParseError(["Keine gueltigen Koordinaten gefunden."])

    first_idx = content_indices[0]
    first_line = lines[first_idx].strip()
    first_parts = [p for p in _split_fields(first_line) if p != ""]
    try:
        mapping = _classify_header(first_parts)
    except CoordinateParseError:
        numeric_looking = 0
        for field in first_parts:
            try:
                parse_number(field, line_no=0, raw_line=field)
                numeric_looking += 1
            except CoordinateParseError:
                pass
        if numeric_looking < len(first_parts):
            raise
        mapping = None

    errors: List[str] = []
    result: List[BSFCoordinatePosition] = []
    data_indices = content_indices[1:] if mapping is not None else content_indices
    if mapping is not None and not data_indices:
        raise CoordinateParseError(["CSV enthaelt nur einen Header, keine Datenzeilen."])

    for line_idx in data_indices:
        physical_no = line_idx + 1
        raw = lines[line_idx].strip()
        if not raw or raw.startswith("#"):
            continue
        parts = [p.strip() for p in _split_fields(raw)]
        try:
            result.append(_xy_from_parts(parts, mapping, physical_no, raw))
        except CoordinateParseError as exc:
            errors.extend(exc.messages)

    if errors:
        raise CoordinateParseError(errors)
    if not result:
        raise CoordinateParseError(["Keine gueltigen Koordinaten gefunden."])
    if len(result) > MAX_BSF_POSITIONS:
        raise CoordinateParseError(
            [f"Zu viele Positionen ({len(result)}). Maximum: {MAX_BSF_POSITIONS}."]
        )
    return result


def write_bsf_csv_file(path: str, positions: Sequence[BSFCoordinatePosition]) -> None:
    text = export_bsf_csv(positions)
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write(text)


def read_bsf_csv_file(path: str) -> List[BSFCoordinatePosition]:
    with open(path, "r", encoding="utf-8-sig") as handle:
        text = handle.read()
    return import_bsf_csv_text(text)
