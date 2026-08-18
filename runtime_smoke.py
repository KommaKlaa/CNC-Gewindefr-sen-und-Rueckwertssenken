"""Optionaler Runtime-Smoke fuer die kompilierte Standalone-EXE.

Aktivierung: Umgebungsvariable NC_GENERATOR_RUNTIME_SMOKE=1
Schreibt einen Report nach %%TEMP%%\\nc_generator_smoke_report.json
und beendet die Anwendung. Keine CNC-Logikaenderung.
"""

from __future__ import annotations

import json
import os
import tempfile
import traceback
from typing import Any, Dict, List

from app_info import APP_AUTHOR, APP_EMAIL, APP_NAME, APP_VERSION, APP_WEBSITE
from app_paths import APP_ICON_PNG_REL, resource_path
from coordinates import BGFCoordinatePosition, BSFCoordinatePosition
from ui import MODE_BGF, MODE_BSF


def schedule_runtime_smoke_if_requested(app) -> None:
    if os.environ.get("NC_GENERATOR_RUNTIME_SMOKE") != "1":
        return
    app.root.after(400, lambda: _run_and_exit(app))


def _run_and_exit(app) -> None:
    report = _execute_smoke(app)
    out = os.environ.get("NC_GENERATOR_SMOKE_REPORT") or os.path.join(
        tempfile.gettempdir(), "nc_generator_smoke_report.json"
    )
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    code = 0 if report.get("ok") else 1
    app.root.after(100, lambda: _quit(app, code))


def _quit(app, code: int) -> None:
    try:
        app.root.destroy()
    finally:
        os._exit(code)


def _silence_boxes() -> None:
    import tkinter.messagebox as mb

    mb.showerror = lambda *a, **k: None
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None
    mb.askyesno = lambda *a, **k: True
    mb.askyesnocancel = lambda *a, **k: True


def _execute_smoke(app) -> Dict[str, Any]:
    steps: Dict[str, Any] = {}
    errors: List[str] = []
    _silence_boxes()

    def record(name: str, fn) -> None:
        try:
            steps[name] = fn()
        except Exception as exc:
            steps[name] = f"FAIL: {exc}"
            errors.append(f"{name}: {exc}\n{traceback.format_exc()}")

    record("png_icon", lambda: resource_path(APP_ICON_PNG_REL).is_file())
    record("about", lambda: _open_about(app))
    record("programmer", lambda: _programmer_runtime(app))
    record("bgf_nc", lambda: _bgf_nc(app))
    record("bgf_list_files", lambda: _bgf_files(app))
    record("bgf_preview_help", lambda: _bgf_windows(app))
    record("bsf_nc", lambda: _bsf_nc(app))
    record("bsf_list_files", lambda: _bsf_files(app))
    record("bsf_preview_help", lambda: _bsf_windows(app))
    record("heidenhain_h", lambda: _export_h(app))
    record("file_dialogs_cancel", lambda: _file_dialogs_cancel(app))

    return {
        "ok": not errors,
        "app": APP_NAME,
        "version": APP_VERSION,
        "steps": steps,
        "errors": errors,
    }


def _open_about(app) -> str:
    from ui.about import open_about_window

    win = open_about_window(app.root)
    title = win.title()
    texts: List[str] = []

    def collect(widget) -> None:
        try:
            texts.append(str(widget.cget("text")))
        except Exception:
            pass
        for child in widget.winfo_children():
            collect(child)

    collect(win)
    blob = "\n".join(texts)
    win.destroy()
    if APP_AUTHOR not in blob or APP_WEBSITE not in blob or APP_EMAIL not in blob:
        raise RuntimeError("Info-Fenster ohne Jens Behm / Website / E-Mail.")
    return title


def _prepare_bgf_single(app) -> None:
    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    app.bgf_size_var.set("M10")
    app.load_bgf_values()
    app.position_mode_var.set("Einzelposition")
    app.on_position_mode_change(None)
    for key, val in (
        ("single_x", "0"),
        ("single_y", "0"),
        ("single_surface_z", "0"),
        ("approach_clearance", "5"),
        ("bgf_thread_depth", "20"),
        ("bgf_core_hole_depth", ""),
    ):
        app.entries[key].delete(0, "end")
        app.entries[key].insert(0, val)


def _prepare_bsf_single(app) -> None:
    app.mode_var.set(MODE_BSF)
    app.on_mode_change(None)
    app.position_mode_var.set("Einzelposition")
    app.on_position_mode_change(None)
    app.bsf_tool_profile_var.set("BSF-C-1000/050-10.5-23")
    app.on_bsf_tool_profile_change()


def _programmer_runtime(app) -> Dict[str, str]:
    from coordinates import (
        import_bgf_csv_text,
        load_bsf_document_json,
        load_document_json,
        save_bsf_document_json,
        save_document_json,
        write_bgf_csv_file,
    )
    from coordinates.bgf_list_document import document_to_dict as bgf_to_dict
    from coordinates.bgf_list_document import parse_document_dict as parse_bgf
    from coordinates.bsf_list_document import document_to_dict as bsf_to_dict
    from coordinates.bsf_list_document import parse_document_dict as parse_bsf

    if "programmer" not in app.entries:
        raise RuntimeError("Programmierer-Feld fehlt in der GUI.")
    if app.programmer_var.get() != "":
        raise RuntimeError("Programmierer-Feld ist nicht leer beim Start.")

    app.programmer_var.set("")
    _prepare_bgf_single(app)
    app.generate_bgf_code()
    bgf_empty = app.output_text.get("1.0", "end")
    if "PROGRAMMIERER" in bgf_empty or "Jens Behm" in bgf_empty:
        raise RuntimeError("Leerer Programmierer: BGF-NC enthaelt PROGRAMMIERER oder Jens Behm.")

    _prepare_bsf_single(app)
    app.generate_bsf_code()
    bsf_empty = app.output_text.get("1.0", "end")
    if "PROGRAMMIERER" in bsf_empty or "Jens Behm" in bsf_empty:
        raise RuntimeError("Leerer Programmierer: BSF-NC enthaelt PROGRAMMIERER oder Jens Behm.")

    name = "Jörg Müller"
    line = f"; PROGRAMMIERER: {name}"
    app.programmer_var.set(name)
    _prepare_bgf_single(app)
    app.generate_bgf_code()
    bgf_named = app.output_text.get("1.0", "end")
    if bgf_named.count(line) != 1:
        raise RuntimeError("BGF-Programmierer-Kommentar fehlt oder mehrfach.")

    _prepare_bsf_single(app)
    app.generate_bsf_code()
    bsf_named = app.output_text.get("1.0", "end")
    if bsf_named.count(line) != 1:
        raise RuntimeError("BSF-Programmierer-Kommentar fehlt oder mehrfach.")

    h_path = os.path.join(tempfile.gettempdir(), "nc_generator_programmer.H")
    with open(h_path, "w", encoding="cp1252", errors="strict") as handle:
        handle.write(bsf_named)
    with open(h_path, "r", encoding="cp1252") as handle:
        h_text = handle.read()
    if name not in h_text:
        raise RuntimeError("cp1252 .H-Export ohne Umlaut-Programmierer.")

    tmp = tempfile.mkdtemp(prefix="nc_smoke_prog_")
    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    app.coord_rows = [BGFCoordinatePosition(0, 0, 0, 20.0)]
    app.position_mode_var.set("Koordinatenliste")
    app.on_position_mode_change(None)
    bgf_doc = app._collect_position_list_document()
    bgf_json = os.path.join(tmp, "p.bgf.json")
    save_document_json(bgf_json, bgf_doc)
    loaded_bgf = load_document_json(bgf_json)
    if loaded_bgf.programmer != name:
        raise RuntimeError("BGF JSON Roundtrip verlor den Programmierer.")
    legacy_bgf = bgf_to_dict(loaded_bgf)
    del legacy_bgf["program"]["programmer"]
    if parse_bgf(legacy_bgf).programmer != "":
        raise RuntimeError("Legacy BGF JSON ohne programmer nicht leer.")

    app.mode_var.set(MODE_BSF)
    app.on_mode_change(None)
    app.bsf_coord_rows = [BSFCoordinatePosition(0, 0)]
    app.position_mode_var.set("Koordinatenliste")
    app.on_position_mode_change(None)
    bsf_doc = app._collect_bsf_position_list_document()
    bsf_json = os.path.join(tmp, "p.bsf.json")
    save_bsf_document_json(bsf_json, bsf_doc)
    loaded_bsf = load_bsf_document_json(bsf_json)
    if loaded_bsf.programmer != name:
        raise RuntimeError("BSF JSON Roundtrip verlor den Programmierer.")
    legacy_bsf = bsf_to_dict(loaded_bsf)
    del legacy_bsf["program"]["programmer"]
    if parse_bsf(legacy_bsf).programmer != "":
        raise RuntimeError("Legacy BSF JSON ohne programmer nicht leer.")

    csv_path = os.path.join(tmp, "pos.csv")
    write_bgf_csv_file(csv_path, app.coord_rows)
    with open(csv_path, "r", encoding="utf-8") as handle:
        csv_text = handle.read()
        import_bgf_csv_text(csv_text, default_thread_depth=20.0)
    if app.programmer_var.get() != name:
        raise RuntimeError("CSV-Import hat den Programmierer veraendert.")
    if "programmer" in csv_text.lower() or "jörg" in csv_text.lower():
        raise RuntimeError("CSV enthaelt Programmierer-Daten.")

    app.programmer_var.set("")
    return {
        "field_visible": "True",
        "empty_bgf": "True",
        "empty_bsf": "True",
        "named_bgf": "True",
        "named_bsf": "True",
        "cp1252": "True",
        "bgf_json": "True",
        "bsf_json": "True",
        "legacy_json": "True",
        "csv": "True",
        "keyword": "PROGRAMMIERER",
    }


def _bgf_nc(app) -> Dict[str, str]:
    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    app.bgf_size_var.set("M10")
    app.load_bgf_values()
    app.position_mode_var.set("Einzelposition")
    app.on_position_mode_change(None)
    for key, val in (
        ("single_x", "0"),
        ("single_y", "0"),
        ("single_surface_z", "0"),
        ("approach_clearance", "5"),
        ("bgf_thread_depth", "20"),
        ("bgf_core_hole_depth", ""),
    ):
        app.entries[key].delete(0, "end")
        app.entries[key].insert(0, val)
    app.generate_bgf_code()
    code_zero = app.output_text.get("1.0", "end")
    app.entries["single_surface_z"].delete(0, "end")
    app.entries["single_surface_z"].insert(0, "20")
    app.generate_bgf_code()
    code_plus = app.output_text.get("1.0", "end")
    app.entries["single_surface_z"].delete(0, "end")
    app.entries["single_surface_z"].insert(0, "-20")
    app.generate_bgf_code()
    code_minus = app.output_text.get("1.0", "end")
    return {
        "has_begin": str("BEGIN PGM" in code_zero),
        "surface_z0_ok": str("Z-19.8390" in code_zero and "Z-22.8100" in code_zero),
        "surface_z_plus20_ok": str("Z+0.1610" in code_plus and "Z-2.8100" in code_plus and "Z+25.0000" in code_plus),
        "surface_z_minus20_ok": str("Z-39.8390" in code_minus and "Z-42.8100" in code_minus and "Z-15.0000" in code_minus),
        "snippet_ok": str(
            "Z-19.8390" in code_zero
            and "Z-22.8100" in code_zero
            and "Z+0.1610" in code_plus
            and "Z-39.8390" in code_minus
        ),
    }


def _bgf_files(app) -> str:
    from coordinates import (
        import_bgf_csv_text,
        load_document_json,
        save_document_json,
        write_bgf_csv_file,
    )

    tmp = tempfile.mkdtemp(prefix="nc_smoke_bgf_")
    app.coord_rows = [
        BGFCoordinatePosition(0, 0, 20.0, 20.0),
        BGFCoordinatePosition(100, 50, 25.0, 20.0),
        BGFCoordinatePosition(-10, 20, -10.0, 20.0),
    ]
    app.position_mode_var.set("Koordinatenliste")
    app.on_position_mode_change(None)
    doc = app._collect_position_list_document()
    json_path = os.path.join(tmp, "smoke.bgf.json")
    csv_path = os.path.join(tmp, "smoke.csv")
    save_document_json(json_path, doc)
    write_bgf_csv_file(csv_path, app.coord_rows)
    loaded = load_document_json(json_path)
    if len(loaded.positions) != 3:
        raise RuntimeError("BGF JSON-Rundlauf fehlgeschlagen.")
    if [p.surface_z for p in loaded.positions] != [20.0, 25.0, -10.0]:
        raise RuntimeError("BGF JSON-Rundlauf verlor surface_z pro Position.")
    with open(csv_path, "r", encoding="utf-8") as handle:
        imported = import_bgf_csv_text(handle.read(), default_thread_depth=20.0)
    if len(imported) != 3:
        raise RuntimeError("BGF CSV-Rundlauf fehlgeschlagen.")
    return tmp


def _bgf_windows(app) -> str:
    from help_views.bgf_geometry_help import BGFGeometryHelpWindow
    from preview.bgf_preview_window import BGFPreviewWindow

    preview = BGFPreviewWindow(app.root, snapshot_provider=app.build_preview_snapshot)
    preview.win.update_idletasks()
    help_win = BGFGeometryHelpWindow(app.root, source_provider=app.collect_bgf_help_source)
    help_win.win.update_idletasks()
    titles = f"{preview.win.title()} | {help_win.win.title()}"
    preview.win.destroy()
    help_win.win.destroy()
    return titles


def _bsf_nc(app) -> Dict[str, str]:
    app.mode_var.set(MODE_BSF)
    app.on_mode_change(None)
    app.position_mode_var.set("Einzelposition")
    app.on_position_mode_change(None)
    app.entries["spindle_speed"].delete(0, "end")
    app.entries["spindle_speed"].insert(0, "777")
    app.entries["bsf_reference_z"].delete(0, "end")
    app.entries["bsf_reference_z"].insert(0, "0")
    app.bsf_tool_profile_var.set("BSF-C-1000/050-10.5-23")
    app.on_bsf_tool_profile_change()
    app.generate_bsf_code()
    code_c = app.output_text.get("1.0", "end")
    app.entries["bsf_reference_z"].delete(0, "end")
    app.entries["bsf_reference_z"].insert(0, "20")
    app.generate_bsf_code()
    code_c_plus = app.output_text.get("1.0", "end")
    app.entries["bsf_reference_z"].delete(0, "end")
    app.entries["bsf_reference_z"].insert(0, "-20")
    app.generate_bsf_code()
    code_c_minus = app.output_text.get("1.0", "end")
    app.entries["bsf_reference_z"].delete(0, "end")
    app.entries["bsf_reference_z"].insert(0, "0")
    app.bsf_tool_profile_var.set("BSF-E-1350/050-16.5-14")
    app.on_bsf_tool_profile_change()
    app.generate_bsf_code()
    code_e = app.output_text.get("1.0", "end")
    return {
        "has_begin": str("BEGIN PGM" in code_c),
        "has_m5": str("M5 ; Spindel aus" in code_c),
        "has_cycl9": str("CYCL DEF 9.1" in code_c),
        "tool_c_activation": str("S2000 M3 ; Spindel einschalten" in code_c),
        "tool_e_activation": str("S1500 M3 ; Spindel einschalten" in code_e),
        "process_speed_separate": str("TOOL CALL 8 Z S777" in code_c and "TOOL CALL 8 Z S777" in code_e),
        "spindle_on_z_0": str("L Z+1.0000 R0 FMAX S2000 M3 ; Spindel einschalten" in code_c),
        "spindle_on_z_plus20": str("L Z+21.0000 R0 FMAX S2000 M3 ; Spindel einschalten" in code_c_plus),
        "spindle_on_z_minus20": str("L Z-19.0000 R0 FMAX S2000 M3 ; Spindel einschalten" in code_c_minus),
    }


def _bsf_files(app) -> str:
    from coordinates import (
        import_bsf_csv_text,
        load_bsf_document_json,
        save_bsf_document_json,
        write_bsf_csv_file,
    )

    tmp = tempfile.mkdtemp(prefix="nc_smoke_bsf_")
    app.bsf_coord_rows = [
        BSFCoordinatePosition(0, 0),
        BSFCoordinatePosition(100, 50),
        BSFCoordinatePosition(-20, 10),
    ]
    app.position_mode_var.set("Koordinatenliste")
    app.on_position_mode_change(None)
    doc = app._collect_bsf_position_list_document()
    json_path = os.path.join(tmp, "smoke.bsf.json")
    csv_path = os.path.join(tmp, "smoke.csv")
    save_bsf_document_json(json_path, doc)
    write_bsf_csv_file(csv_path, app.bsf_coord_rows)
    loaded = load_bsf_document_json(json_path)
    if len(loaded.positions) != 3:
        raise RuntimeError("BSF JSON-Rundlauf fehlgeschlagen.")
    if not loaded.tool_profile_key:
        raise RuntimeError("BSF JSON V2 ohne tool_profile_key.")
    raw_json = open(json_path, "r", encoding="utf-8").read()
    for forbidden in ("blade_thickness", "measurement_reference", "holder_to_cutting_edge", "activation_speed"):
        if forbidden in raw_json:
            raise RuntimeError(f"BSF JSON V2 enthaelt verbotenes Feld: {forbidden}")
    with open(csv_path, "r", encoding="utf-8") as handle:
        imported = import_bsf_csv_text(handle.read())
    if len(imported) != 3:
        raise RuntimeError("BSF CSV-Rundlauf fehlgeschlagen.")
    return tmp


def _bsf_windows(app) -> str:
    from help_views.bsf_geometry_help import BSFGeometryHelpWindow
    from preview.bgf_preview_window import BGFPreviewWindow

    preview = BGFPreviewWindow(app.root, snapshot_provider=app.build_preview_snapshot)
    preview.win.update_idletasks()
    help_win = BSFGeometryHelpWindow(app.root, snapshot_provider=app.build_bsf_geometry_help_snapshot)
    help_win.win.update_idletasks()
    titles = f"{preview.win.title()} | {help_win.win.title()}"
    preview.win.destroy()
    help_win.win.destroy()
    return titles


def _export_h(app) -> str:
    code = app.output_text.get("1.0", "end").strip()
    if not code:
        raise RuntimeError("Kein NC-Code fuer .H-Export.")
    path = os.path.join(tempfile.gettempdir(), "nc_generator_smoke.H")
    with open(path, "w", encoding="cp1252", errors="replace") as handle:
        handle.write(code + "\n")
    return path


def _file_dialogs_cancel(app) -> int:
    """Dateidialoge Abbrechen: kein Tcl-Fehler, kein State-Wechsel."""
    from tkinter import filedialog

    cancelled: List[str] = []

    def _cancel(**kwargs) -> str:
        cancelled.append(str(kwargs.get("title") or kwargs.get("defaultextension") or "dialog"))
        return ""

    filedialog.asksaveasfilename = _cancel  # type: ignore[method-assign]
    filedialog.askopenfilename = _cancel  # type: ignore[method-assign]

    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    app.coord_save_list()
    app.coord_load_list()
    app.coord_export_csv()
    app.coord_import_csv()
    app.export_to_h()

    app.mode_var.set(MODE_BSF)
    app.on_mode_change(None)
    app.bsf_coord_save_list()
    app.bsf_coord_load_list()
    app.bsf_coord_export_csv()
    app.bsf_coord_import_csv()

    if len(cancelled) < 9:
        raise RuntimeError(f"Dateidialoge unerwartet: {cancelled}")
    return len(cancelled)
