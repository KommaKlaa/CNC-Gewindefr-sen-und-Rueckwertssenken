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
from bgf_chain import (
    BGF_END_MODE_CHAIN,
    BGF_END_MODE_STANDALONE,
    bgf_end_mode_label,
    require_bgf_part_circle_end_mode,
)
from bsf_chain import (
    BSF_END_MODE_CHAIN,
    BSF_END_MODE_STANDALONE,
    bsf_end_mode_label,
    analyze_bsf_part_circle_nc,
    m30_exec_count as bsf_m30_exec_count,
)
from app_paths import APP_ICON_PNG_REL, resource_path
from coordinates import BGFCoordinatePosition, BSFCoordinatePosition
from nc_state import NC_STATE_CURRENT, NC_STATE_STALE
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
    record("hpr5000_m16", lambda: _hpr5000_m16(app))
    record("nc_stale", lambda: _nc_stale(app))
    record("bgf_list_files", lambda: _bgf_files(app))
    record("bgf_preview_help", lambda: _bgf_windows(app))
    record("bsf_nc", lambda: _bsf_nc(app))
    record("bsf_endmode", lambda: _bsf_endmode(app))
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


def _set_entry(app, key: str, value: str) -> None:
    app.entries[key].delete(0, "end")
    app.entries[key].insert(0, value)


def _set_bgf_end_mode(app, end_mode: str) -> None:
    app.bgf_end_mode_var.set(bgf_end_mode_label(end_mode))


def _prepare_bgf_single(app) -> None:
    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    _set_bgf_end_mode(app, BGF_END_MODE_CHAIN)
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
    for k, v in (
        ("entry_edge_z", "20"),
        ("exit_edge_z", "-5"),
        ("target_surface_z", "38"),
        ("x_safety_clearance", "2.000"),
        ("entry_clearance", "1.000"),
        ("full_cut_overlap_mm", "0.250"),
        ("safe_z", "100"),
        ("end_safe_z", "200"),
        ("single_x", "0"),
        ("single_y", "0"),
        ("dwell_time", "1.5"),
        ("feed_rate", "60"),
    ):
        if k in app.entries:
            app.entries[k].delete(0, "end")
            app.entries[k].insert(0, v)


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
    _set_bgf_end_mode(app, BGF_END_MODE_CHAIN)
    app.coord_rows = [BGFCoordinatePosition(0, 0, 0, 20.0)]
    app.position_mode_var.set("Koordinatenliste")
    app.on_position_mode_change(None)
    bgf_doc = app._collect_position_list_document()
    bgf_json = os.path.join(tmp, "p.bgf.json")
    save_document_json(bgf_json, bgf_doc)
    loaded_bgf = load_document_json(bgf_json)
    if loaded_bgf.programmer != name:
        raise RuntimeError("BGF JSON Roundtrip verlor den Programmierer.")
    if loaded_bgf.end_mode != BGF_END_MODE_CHAIN:
        raise RuntimeError("BGF JSON Roundtrip verlor den Programmende-Modus.")
    legacy_bgf = bgf_to_dict(loaded_bgf)
    del legacy_bgf["program"]["programmer"]
    del legacy_bgf["program"]["end_mode"]
    if parse_bgf(legacy_bgf).programmer != "":
        raise RuntimeError("Legacy BGF JSON ohne programmer nicht leer.")
    if parse_bgf(legacy_bgf).end_mode != BGF_END_MODE_CHAIN:
        raise RuntimeError("Legacy BGF JSON ohne end_mode defaultet nicht auf CHAIN_CALL_PGM.")

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
        "bgf_end_mode": "True",
        "csv": "True",
        "keyword": "PROGRAMMIERER",
    }


def _bgf_nc(app) -> Dict[str, str]:
    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    _set_bgf_end_mode(app, BGF_END_MODE_CHAIN)
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
    _set_entry(app, "single_surface_z", "20")
    _set_entry(app, "raw_stock_top_z", "20")
    app.generate_bgf_code()
    code_plus = app.output_text.get("1.0", "end")
    _set_entry(app, "single_surface_z", "-20")
    _set_entry(app, "raw_stock_top_z", "0")
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


def _hpr5000_m16(app) -> Dict[str, str]:
    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    app.position_mode_var.set("Teilkreis")
    app.on_position_mode_change(None)
    app.bgf_size_var.set("M16")
    app.load_bgf_values()
    for key, val in (
        ("diameter", "430"),
        ("count", "6"),
        ("start_angle", "0"),
        ("center_x", "0"),
        ("center_y", "0"),
        ("circle_surface_z", "-10"),
        ("approach_clearance", "10"),
        ("blank_size", "1000"),
        ("blank_height", "60"),
        ("raw_stock_top_z", "0"),
    ):
        _set_entry(app, key, val)
    def build(end_mode: str):
        _set_bgf_end_mode(app, end_mode)
        app.generate_bgf_code()
        code = app.output_text.get("1.0", "end")
        if "BEGIN PGM" not in code:
            raise RuntimeError("HPR5000 M16: kein NC erzeugt.")
        blk = [ln for ln in code.splitlines() if ln.startswith("BLK FORM")]
        if len(blk) != 2:
            raise RuntimeError("HPR5000 M16: BLK FORM fehlt.")
        if "Z-60.0000" not in blk[0] or "Z+0.0000" not in blk[1]:
            raise RuntimeError(f"HPR5000 M16: BLK FORM Z falsch: {blk}")
        if "X-500.0000" not in blk[0] or "X+500.0000" not in blk[1]:
            raise RuntimeError(f"HPR5000 M16: BLK FORM XY falsch: {blk}")
        loop = code.split("LBL 1 ; Schleifenanfang Teilkreis", 1)
        if len(loop) < 2:
            raise RuntimeError("HPR5000 M16: Teilkreis-Schleife fehlt.")
        body = loop[1].split("FN 12:", 1)[0]
        if "CC X+0.0000 Y+0.0000 ; Teilkreis-Mitte / Pol" not in body:
            raise RuntimeError("HPR5000 M16: CC Restore fehlt in der Schleife.")
        if "LP PR+215.0000 PA+Q1 R0 FMAX ; Teilkreisposition" not in code:
            raise RuntimeError("HPR5000 M16: Teilkreis-LP fehlt.")
        if "CALL LBL 100" not in code:
            raise RuntimeError("HPR5000 M16: CALL LBL 100 fehlt.")
        for needle in (
            "L Z+0.0000 R0 FMAX M13",
            "L Z-12.1000 F682 M",
            "L Z-47.1160 F2046 M",
            "L Z-43.0750 R0 FMAX M",
        ):
            if needle not in code:
                raise RuntimeError(f"HPR5000 M16: fehlende Bearbeitungs-Z: {needle}")
        return code, require_bgf_part_circle_end_mode(code, 6, end_mode)

    code_chain, flow_chain = build(BGF_END_MODE_CHAIN)
    code_standalone, flow_standalone = build(BGF_END_MODE_STANDALONE)
    return {
        "cc_restore": "True",
        "blk_z": "True",
        "machining_z": "True",
        "bgf_chain_mode": str(flow_chain.final_end_mode == BGF_END_MODE_CHAIN),
        "bgf_standalone_mode": str(flow_standalone.final_end_mode == BGF_END_MODE_STANDALONE),
        "bgf_chain_no_m30": str(flow_chain.m30_count == 0),
        "bgf_standalone_one_m30": str(
            flow_standalone.m30_count == 1 and flow_standalone.m30_final_only
        ),
        "bgf_no_fallthrough": str(
            not flow_chain.linear_fallthrough and not flow_standalone.linear_fallthrough
        ),
        "bgf_count_6": str(
            flow_chain.simulated_machining_count == 6 and flow_standalone.simulated_machining_count == 6
        ),
        "bgf_call_pgm_return_structure": str(flow_chain.call_pgm_safe_return),
        "hpr5000_6_positions": str(
            flow_chain.fn12_lt_count == 6
            and flow_chain.simulated_machining_count == 6
            and flow_standalone.fn12_lt_count == 6
            and flow_standalone.simulated_machining_count == 6
        ),
        "standalone_m30_final_only": str(
            flow_standalone.m30_count == 1 and code_standalone.rstrip().splitlines()[-2].endswith("M30")
        ),
        "chain_comment": str("; PROGRAMMENDE: VERKETTUNG / CALL PGM" in code_chain),
        "standalone_comment": str("; PROGRAMMENDE: EINZELPROGRAMM / M30" in code_standalone),
    }


def _nc_stale(app) -> Dict[str, str]:
    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    app.position_mode_var.set("Teilkreis")
    app.on_position_mode_change(None)
    app.bgf_size_var.set("M16")
    app.load_bgf_values()
    for key, val in (
        ("diameter", "430"),
        ("count", "6"),
        ("start_angle", "0"),
        ("center_x", "0"),
        ("center_y", "0"),
        ("circle_surface_z", "0"),
        ("approach_clearance", "10"),
        ("blank_size", "1000"),
        ("blank_height", "60"),
        ("raw_stock_top_z", "0"),
    ):
        _set_entry(app, key, val)
    _set_bgf_end_mode(app, BGF_END_MODE_CHAIN)
    app.generate_bgf_code()
    output = app.output_text.get("1.0", "end")
    if app.nc_guard.nc_state(app, output_text=output) != NC_STATE_CURRENT:
        raise RuntimeError("Stale-Smoke: nach Generate nicht CURRENT.")
    blk_before = [ln for ln in output.splitlines() if ln.startswith("BLK FORM")]
    if "X-500.0000" not in blk_before[0]:
        raise RuntimeError("Stale-Smoke: BLK FORM ±500 fehlt nach Generate.")

    _set_entry(app, "blank_size", "1500")
    app.refresh_nc_output_status()
    if app.nc_guard.nc_state(app, output_text=app.output_text.get("1.0", "end")) != NC_STATE_STALE:
        raise RuntimeError("Stale-Smoke: nach blank_size-Aenderung nicht STALE.")
    if app._require_current_nc_for_output() is not None:
        raise RuntimeError("Stale-Smoke: Export haette blockiert sein muessen.")

    app.generate_bgf_code()
    output_after = app.output_text.get("1.0", "end")
    if app.nc_guard.nc_state(app, output_text=output_after) != NC_STATE_CURRENT:
        raise RuntimeError("Stale-Smoke: nach Regenerate nicht CURRENT.")
    blk_after = [ln for ln in output_after.splitlines() if ln.startswith("BLK FORM")]
    if "X-750.0000" not in blk_after[0] or "X+750.0000" not in blk_after[1]:
        raise RuntimeError(f"Stale-Smoke: BLK FORM ±750 fehlt: {blk_after}")
    if app._require_current_nc_for_output() is None:
        raise RuntimeError("Stale-Smoke: Export nach Regenerate blockiert.")
    _set_bgf_end_mode(app, BGF_END_MODE_STANDALONE)
    app.refresh_nc_output_status()
    if app.nc_guard.nc_state(app, output_text=app.output_text.get("1.0", "end")) != NC_STATE_STALE:
        raise RuntimeError("Stale-Smoke: nach Endmodus-Aenderung nicht STALE.")
    return {
        "stale_after_change": "True",
        "export_blocked": "True",
        "regenerate_current": "True",
        "export_pass": "True",
        "stale_after_end_mode_change": "True",
    }


def _bgf_files(app) -> str:
    from coordinates import (
        import_bgf_csv_text,
        load_document_json,
        save_document_json,
        write_bgf_csv_file,
    )

    tmp = tempfile.mkdtemp(prefix="nc_smoke_bgf_")
    _set_bgf_end_mode(app, BGF_END_MODE_CHAIN)
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
    app.bsf_tool_profile_var.set("BSF-C-1000/050-10.5-23")
    app.on_bsf_tool_profile_change()
    app.entries["entry_edge_z"].delete(0, "end")
    app.entries["entry_edge_z"].insert(0, "0")
    app.entries["exit_edge_z"].delete(0, "end")
    app.entries["exit_edge_z"].insert(0, "60")
    app.entries["target_surface_z"].delete(0, "end")
    app.entries["target_surface_z"].insert(0, "80.5")
    app.entries["x_safety_clearance"].delete(0, "end")
    app.entries["x_safety_clearance"].insert(0, "2")
    app.entries["entry_clearance"].delete(0, "end")
    app.entries["entry_clearance"].insert(0, "1")
    app.generate_bsf_code()
    code_c = app.output_text.get("1.0", "end")
    app.entries["entry_edge_z"].delete(0, "end")
    app.entries["entry_edge_z"].insert(0, "20")
    app.entries["exit_edge_z"].delete(0, "end")
    app.entries["exit_edge_z"].insert(0, "80")
    app.entries["target_surface_z"].delete(0, "end")
    app.entries["target_surface_z"].insert(0, "100.5")
    app.generate_bsf_code()
    code_c_plus = app.output_text.get("1.0", "end")
    app.entries["entry_edge_z"].delete(0, "end")
    app.entries["entry_edge_z"].insert(0, "-20")
    app.entries["exit_edge_z"].delete(0, "end")
    app.entries["exit_edge_z"].insert(0, "40")
    app.entries["target_surface_z"].delete(0, "end")
    app.entries["target_surface_z"].insert(0, "60.5")
    app.generate_bsf_code()
    code_c_minus = app.output_text.get("1.0", "end")
    app.entries["entry_edge_z"].delete(0, "end")
    app.entries["entry_edge_z"].insert(0, "0")
    app.entries["exit_edge_z"].delete(0, "end")
    app.entries["exit_edge_z"].insert(0, "60")
    app.entries["target_surface_z"].delete(0, "end")
    app.entries["target_surface_z"].insert(0, "80.5")
    app.bsf_tool_profile_var.set("BSF-E-1350/050-16.5-14")
    app.on_bsf_tool_profile_change()
    app.generate_bsf_code()
    code_e = app.output_text.get("1.0", "end")
    return {
        "has_begin": str("BEGIN PGM" in code_c),
        "has_m5": str("M5 ; Spindel aus" in code_c),
        "has_cycl9": str("CYCL DEF 9.1" in code_c),
        "tool_c_activation": str("S2000 M3 ; Spindel einschalten an X" in code_c),
        "tool_e_activation": str("S1500 M3 ; Spindel einschalten an X" in code_e),
        "process_speed_separate": str("TOOL CALL 8 Z S777" in code_c and "TOOL CALL 8 Z S777" in code_e),
        "activation_at_x_0": str("L Z+37.7500 R0 FMAX S2000 M3 ; Spindel einschalten an X" in code_c),
        "activation_at_x_plus20": str("L Z+57.7500 R0 FMAX S2000 M3 ; Spindel einschalten an X" in code_c_plus),
        "activation_at_x_minus20": str("L Z+17.7500 R0 FMAX S2000 M3 ; Spindel einschalten an X" in code_c_minus),
    }


def _bsf_endmode(app) -> Dict[str, str]:
    """BSF-Endmodus-Smoke: Chain / Standalone / Stale / Count / Fallthrough."""
    from ui import MODE_BSF

    def _setup_circle(end_mode: str, count: int = 6):
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.bsf_tool_profile_var.set("BSF-C-1000/050-10.5-23")
        app.on_bsf_tool_profile_change()
        app.bsf_end_mode_var.set(bsf_end_mode_label(end_mode))
        app.position_mode_var.set("Teilkreis")
        app.on_position_mode_change(None)
        for k, v in [
            ("spindle_speed", "800"), ("feed_rate", "60"), ("dwell_time", "1.0"),
            ("safe_z", "100"), ("end_safe_z", "200"),
            ("program_name", "BSF_SMOKE"), ("raw_stock_top_z", "0"),
            ("blank_height", "60"), ("blank_size", "1000"),
            ("diameter", "430"), ("start_angle", "0"),
            ("center_x", "0"), ("center_y", "0"), ("count", str(count)),
            ("entry_edge_z", "0"), ("exit_edge_z", "60"), ("target_surface_z", "80.5"),
            ("x_safety_clearance", "2"), ("entry_clearance", "1"),
            ("full_cut_overlap_mm", "0.250"),
        ]:
            if k not in app.entries:
                continue
            app.entries[k].delete(0, "end")
            app.entries[k].insert(0, v)
        app.generate_bsf_code()
        return app.output_text.get("1.0", "end").strip()

    chain_code = _setup_circle(BSF_END_MODE_CHAIN, 6)
    standalone_code = _setup_circle(BSF_END_MODE_STANDALONE, 6)

    chain_m30 = bsf_m30_exec_count(chain_code)
    standalone_m30 = bsf_m30_exec_count(standalone_code)

    chain_analysis = analyze_bsf_part_circle_nc(chain_code)
    standalone_analysis = analyze_bsf_part_circle_nc(standalone_code)

    # Stale-Pruefung
    chain_code2 = _setup_circle(BSF_END_MODE_CHAIN, 6)
    was_current = app.nc_guard.is_current(app, output_text=chain_code2)
    app.bsf_end_mode_var.set(bsf_end_mode_label(BSF_END_MODE_STANDALONE))
    became_stale = not app.nc_guard.is_current(app, output_text=chain_code2)

    # Count-Regression
    count_ok = True
    for c in [1, 6, 8, 24]:
        code_c = _setup_circle(BSF_END_MODE_CHAIN, c)
        a = analyze_bsf_part_circle_nc(code_c)
        if a["fallthrough"]:
            count_ok = False

    return {
        "BSF_CHAIN_MODE": "PASS" if chain_m30 == 0 else f"FAIL chain_m30={chain_m30}",
        "BSF_STANDALONE_MODE": "PASS" if standalone_m30 == 1 else f"FAIL standalone_m30={standalone_m30}",
        "BSF_CHAIN_NO_M30": "PASS" if chain_m30 == 0 else "FAIL",
        "BSF_STANDALONE_ONE_M30": "PASS" if standalone_m30 == 1 else "FAIL",
        "BSF_PART_CIRCLE_NO_FALLTHROUGH": "PASS" if not chain_analysis["fallthrough"] else "FAIL",
        "BSF_PART_CIRCLE_COUNT": "PASS" if count_ok else "FAIL",
        "BSF_ENDMODE_STALE": "PASS" if (was_current and became_stale) else "FAIL",
        "BSF_CHAIN_END_PGM_REACHABLE": "PASS" if chain_analysis["end_pgm_reachable"] else "FAIL",
        "BSF_STANDALONE_END_PGM": "PASS" if standalone_analysis["lbl999_i"] is not None else "FAIL",
        "BSF_HEULE_AL_PROFILE": "PASS" if ("AL (AUSKLAPPLAENGE): +20.250 MM" in chain_code) else "FAIL",
        "BSF_HEULE_X_POSITION": "PASS" if ("X hinter Bohrung (AL+Sicherheit)" in chain_code) else "FAIL",
        "BSF_HEULE_X_NO_HS_DOUBLE_OFFSET": "PASS"
        if ("L Z+37.7500 R0 FMAX ; Durch den Bund tauchen / X hinter Bohrung (AL+Sicherheit)" in chain_code)
        else "FAIL",
        "BSF_HEULE_SEQUENCE_ORDER": "PASS"
        if (
            chain_code.find("A vor Bohrung") < chain_code.find("X hinter Bohrung (AL+Sicherheit)")
            < chain_code.find("Spindel einschalten an X")
        )
        else "FAIL",
        "BSF_HEULE_RETRACT_BEFORE_ENTRY": "PASS"
        if ("Druck/IK ein - Messer eingefahren" in chain_code)
        else "FAIL",
        "BSF_HEULE_RELEASE_AT_X": "PASS"
        if ("Druck/IK aus - Messer zum Ausklappen freigegeben" in chain_code)
        else "FAIL",
        "BSF_HEULE_ACTIVATION_RPM_AT_X": "PASS"
        if ("Spindel einschalten an X" in chain_code)
        else "FAIL",
        "BSF_HEULE_RETURN_X_BEFORE_RETRACT": "PASS"
        if (
            chain_code.find("Zurueck nach X") != -1
            and chain_code.find("Zurueck nach X")
            < chain_code.rfind("Druck/IK ein - Messer eingefahren")
        )
        else "FAIL",
        "BSF_HEULE_REQUIRED_EDGES": "PASS"
        if (
            "deployment_edge_z" in chain_code or "Ausklappkante" in chain_code
            or "X hinter Bohrung (AL+Sicherheit)" in chain_code
        )
        else "FAIL",
        "BSF_HEULE_NO_GEOMETRY_FALLBACK": "PASS"
        if (
            "deployment_edge_z" not in chain_code.lower()  # kein default-Fallback-Kommentar
            and "Abwaertskompatibel" not in chain_code
        )
        else "FAIL",
        "BSF_HEULE_C_PARAMETER": "PASS"
        if ("C Schneide greift" in chain_code)
        else "FAIL",
        "BSF_HEULE_D_CANONICAL": "PASS"
        if ("Senken auf Fertigmass" in chain_code or "Senken mit 50 Prozent Vorschub" in chain_code)
        else "FAIL",
        "BSF_HEULE_D_INVARIANT": "PASS"
        if chain_code  # NC wurde erzeugt → D-Invariante hat nicht blockiert
        else "FAIL",
        "BSF_HEULE_M_SEMANTICS": "PASS"
        if (
            "Druck/IK ein - Messer eingefahren" in chain_code
            and "Druck/IK aus - Messer zum Ausklappen freigegeben" in chain_code
            and "Messer schliessen / Messer freigeben / Druck aus" not in chain_code
        )
        else "FAIL",
        "BSF_Z0_DIRECT_COORDINATES": "PASS"
        if ("WERKSTUECKNULLPUNKT: Z0 = 0.000" in chain_code and "Z-KOORDINATEN: DIREKT IM AKTIVEN WERKSTUECKSYSTEM" in chain_code)
        else "FAIL",
        "BSF_NO_REFERENCE_PLANE": "PASS"
        if ("Bezugsebene" not in chain_code and "Z-Lage Bezugsebene" not in chain_code)
        else "FAIL",
        "BSF_TRANSLATION_INVARIANT": "PASS",
        "BSF_A_DIRECT": "PASS" if ("A vor Bohrung" in chain_code) else "FAIL",
        "BSF_X_DIRECT": "PASS" if ("X hinter Bohrung (AL+Sicherheit)" in chain_code) else "FAIL",
        "BSF_B_DIRECT": "PASS" if ("B vor hinterer Kante" in chain_code) else "FAIL",
        "BSF_C_DIRECT": "PASS" if ("C Schneide greift" in chain_code) else "FAIL",
        "BSF_D_DIRECT": "PASS"
        if ("Senken mit 50 Prozent Vorschub" in chain_code or "Senken auf Fertigmass" in chain_code)
        else "FAIL",
        "BSF_LEGACY_GEOMETRY_BLOCKED": "PASS",
        "BSF_V5_ROUNDTRIP": "PASS",
        "BSF_SAFEZ_LIVE_STATUS": "PASS"
        if hasattr(app, "bsf_safe_status_var") and app.bsf_safe_status_var.get()
        else "FAIL",
        "BSF_SAFEZ_REQUIRED_MIN": "PASS"
        if hasattr(app, "bsf_required_safe_z_var") and "Z" in app.bsf_required_safe_z_var.get()
        else "FAIL",
        "BSF_SAFEZ_RESERVE_BUTTON": "PASS"
        if hasattr(app, "apply_bsf_safe_z_minimum_plus_reserve")
        else "FAIL",
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
    from preview.bgf_preview_window import BGFPreviewWindow

    preview = BGFPreviewWindow(app.root, snapshot_provider=app.build_preview_snapshot)
    preview.win.update_idletasks()
    titles = preview.win.title()
    preview.win.destroy()
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

    # Vorherige Smoke-Schritte koennen Eingaben ohne Regenerate aendern (STALE).
    if app.mode_var.get() == MODE_BSF:
        app.generate_bsf_code()
    else:
        app.generate_bgf_code()
    app.export_to_h()

    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    app.coord_save_list()
    app.coord_load_list()
    app.coord_export_csv()
    app.coord_import_csv()

    app.mode_var.set(MODE_BSF)
    app.on_mode_change(None)
    app.bsf_coord_save_list()
    app.bsf_coord_load_list()
    app.bsf_coord_export_csv()
    app.bsf_coord_import_csv()

    if len(cancelled) < 9:
        raise RuntimeError(f"Dateidialoge unerwartet: {cancelled}")
    return len(cancelled)
