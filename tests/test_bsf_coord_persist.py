"""PHASE BSF.COORD.2 – HEULE-BSF Projektdatei (.bsf.json) und CSV."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from bsf_blade import (
    MEASUREMENT_LABELS,
    BladeMeasurementReference,
    apply_blade_offset,
    blade_reference_offset,
    calculate_workpiece_bsf_z,
)
import bsf_generator_verbessert_v3 as gen
from coordinates import (
    BSFCoordinatePosition,
    BSFDocumentError,
    build_bsf_document,
    export_bsf_csv,
    import_bsf_csv_text,
    load_bsf_document_json,
    save_bsf_document_json,
    validate_bsf_coordinate_list,
)
from coordinates.bsf_list_document import (
    FORMAT_NAME,
    FORMAT_VERSION,
    NEWER_VERSION_MESSAGE,
    document_to_dict,
    parse_document_dict,
)
from coordinates.parser import CoordinateParseError
from ui import MODE_BSF

SPINDLE_LABEL = MEASUREMENT_LABELS[BladeMeasurementReference.SPINDLE_SIDE_EDGE]
TIP_LABEL = MEASUREMENT_LABELS[BladeMeasurementReference.TOOL_TIP_SIDE_EDGE]


def _doc(positions=None, **kwargs):
    base = dict(
        program_name="BSF_TEST",
        tool_number=8,
        blank_size=1000.0,
        blank_height=60.0,
        z_reference="BOTTOM_EDGE",
        bund_thickness=18.0,
        sink_finish=38.0,
        clearance=23.0,
        blade_thickness=3.0,
        blade_measurement_reference=BladeMeasurementReference.SPINDLE_SIDE_EDGE,
        spindle_speed=1500,
        feed=120.0,
        dwell_time=1.5,
        reduce_approach=True,
        approach_feed_factor=0.5,
        activate_preset="IKZ Ein (M7)",
        activate_custom="M107",
        deactivate_preset="Alles AUS (M9)",
        deactivate_custom="M9",
        safe_z=100.0,
        end_safe_z=200.0,
        positions=positions
        or [
            BSFCoordinatePosition(0.0, 0.0),
            BSFCoordinatePosition(100.0, 50.0),
            BSFCoordinatePosition(-50.0, 75.0),
        ],
    )
    base.update(kwargs)
    return build_bsf_document(**base)


def _fill_bsf_app(app, *, positions=None, measurement=SPINDLE_LABEL, **overrides):
    app.mode_var.set(MODE_BSF)
    app.on_mode_change(None)
    app.position_mode_var.set("Koordinatenliste")
    app.on_position_mode_change(None)
    values = {
        "program_name": "BSF_TEST",
        "tool_num": "8",
        "bund_thickness": "18",
        "sink_depth": "38",
        "clearance": "23",
        "dwell_time": "1.5",
        "blade_thickness": "3",
        "spindle_speed": "1500",
        "feed_rate": "120",
        "safe_z": "100",
        "end_safe_z": "200",
        "blank_size": "1000",
        "blank_height": "60",
    }
    values.update(overrides)
    for key, val in values.items():
        app.entries[key].delete(0, "end")
        app.entries[key].insert(0, val)
    app.z0_var.set("Z0 ist Unterkante Bund")
    app.blade_measurement_var.set(measurement)
    app.reduce_approach_var.set(True)
    app.m_activate_var.set("IKZ Ein (M7)")
    app.on_m_activate_change(None)
    app.m_deactivate_var.set("Alles AUS (M9)")
    app.on_m_deactivate_change(None)
    app.bsf_coord_rows = list(
        positions
        or [
            BSFCoordinatePosition(0.0, 0.0),
            BSFCoordinatePosition(100.0, 50.0),
            BSFCoordinatePosition(-50.0, 75.0),
        ]
    )
    app._refresh_bsf_coord_tree()


def _silence_boxes():
    import tkinter.messagebox as mb

    orig = {
        "error": mb.showerror,
        "warn": mb.showwarning,
        "info": mb.showinfo,
        "yesno": mb.askyesno,
        "yesnocancel": mb.askyesnocancel,
    }
    mb.showerror = lambda *a, **k: None
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None
    mb.askyesno = lambda *a, **k: True
    mb.askyesnocancel = lambda *a, **k: True
    return mb, orig


def _restore_boxes(mb, orig) -> None:
    for key, fn in orig.items():
        setattr(mb, "ask" + key if key in ("yesno", "yesnocancel") else "show" + key, fn)
    mb.showerror = orig["error"]
    mb.showwarning = orig["warn"]
    mb.showinfo = orig["info"]
    mb.askyesno = orig["yesno"]
    mb.askyesnocancel = orig["yesnocancel"]


class TestBsfJsonRoundtrip(unittest.TestCase):
    def test_roundtrip_values(self):
        doc = _doc()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "BSF_TEST.bsf.json")
            save_bsf_document_json(path, doc)
            loaded = load_bsf_document_json(path)
        self.assertEqual(loaded.format_name, FORMAT_NAME)
        self.assertEqual(loaded.version, FORMAT_VERSION)
        self.assertEqual(loaded.program_name, "BSF_TEST")
        self.assertEqual(loaded.tool_number, 8)
        self.assertEqual(loaded.bund_thickness, 18.0)
        self.assertEqual(loaded.sink_finish, 38.0)
        self.assertEqual(loaded.clearance, 23.0)
        self.assertEqual(loaded.z_reference, "BOTTOM_EDGE")
        self.assertEqual(loaded.blade_thickness, 3.0)
        self.assertIs(loaded.blade_measurement_reference, BladeMeasurementReference.SPINDLE_SIDE_EDGE)
        self.assertEqual(loaded.safe_z, 100.0)
        self.assertEqual(loaded.end_safe_z, 200.0)
        self.assertEqual(list(loaded.positions), list(doc.positions))

    def test_tip_edge_roundtrip(self):
        doc = _doc(blade_measurement_reference=BladeMeasurementReference.TOOL_TIP_SIDE_EDGE)
        payload = document_to_dict(doc)
        loaded = parse_document_dict(payload)
        self.assertIs(loaded.blade_measurement_reference, BladeMeasurementReference.TOOL_TIP_SIDE_EDGE)
        offset = blade_reference_offset(loaded.blade_thickness, loaded.blade_measurement_reference)
        wp = calculate_workpiece_bsf_z(
            loaded.bund_thickness,
            loaded.sink_finish,
            loaded.clearance,
            z0_is_flange_bottom=loaded.z0_is_flange_bottom,
        )
        programmed = apply_blade_offset(wp, offset)
        spindle_off = blade_reference_offset(3.0, BladeMeasurementReference.SPINDLE_SIDE_EDGE)
        self.assertAlmostEqual(programmed["z_sink_finish"] - (wp["z_sink_finish"] + spindle_off), -3.0)

    def test_no_derived_data_in_json(self):
        raw = json.dumps(document_to_dict(_doc()))
        for forbidden in (
            "z_sink_finish",
            "z_clearance",
            "blade_reference_offset",
            "physical_finish",
            "NC_CODE_ALLOWED",
            "duplicate",
        ):
            self.assertNotIn(forbidden, raw)

    def test_z_recalculated_after_load_not_from_file(self):
        payload = document_to_dict(_doc())
        payload["workpiece"]["z_sink_finish"] = 999.0
        loaded = parse_document_dict(payload)
        wp = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=True)
        offset = blade_reference_offset(3.0, BladeMeasurementReference.SPINDLE_SIDE_EDGE)
        programmed = apply_blade_offset(wp, offset)
        self.assertEqual(programmed["z_sink_finish"], wp["z_sink_finish"])
        self.assertNotEqual(programmed["z_sink_finish"], 999.0)

    def test_order_preserved(self):
        positions = [
            BSFCoordinatePosition(10, 1),
            BSFCoordinatePosition(-2, 8),
            BSFCoordinatePosition(3, 3),
        ]
        loaded = parse_document_dict(document_to_dict(_doc(positions=positions)))
        self.assertEqual(list(loaded.positions), positions)

    def test_wrong_format_blocked(self):
        payload = document_to_dict(_doc())
        payload["format"] = "BGF_POSITION_LIST"
        with self.assertRaises(BSFDocumentError):
            parse_document_dict(payload)

    def test_newer_version_blocked(self):
        payload = document_to_dict(_doc())
        payload["version"] = 999
        with self.assertRaises(BSFDocumentError) as ctx:
            parse_document_dict(payload)
        self.assertEqual(ctx.exception.message, NEWER_VERSION_MESSAGE)

    def test_unknown_enum_blocked(self):
        payload = document_to_dict(_doc())
        payload["blade"]["measurement_reference"] = "BOTTOM"
        with self.assertRaises(BSFDocumentError) as ctx:
            parse_document_dict(payload)
        self.assertIn("BOTTOM", ctx.exception.message)

    def test_unknown_z_reference_blocked(self):
        payload = document_to_dict(_doc())
        payload["workpiece"]["z_reference"] = "AUTO"
        with self.assertRaises(BSFDocumentError):
            parse_document_dict(payload)

    def test_blade_zero_blocked(self):
        with self.assertRaises(BSFDocumentError):
            _doc(blade_thickness=0.0)

    def test_no_pickle(self):
        import inspect
        from coordinates import bsf_list_document

        self.assertNotIn("pickle", inspect.getsource(bsf_list_document))


class TestBsfCsv(unittest.TestCase):
    def test_roundtrip(self):
        positions = [
            BSFCoordinatePosition(0.0, 0.0),
            BSFCoordinatePosition(100.5, 50.25),
            BSFCoordinatePosition(-125.75, -80.5),
        ]
        text = export_bsf_csv(positions)
        self.assertTrue(text.startswith("Nr;X;Y"))
        loaded = import_bsf_csv_text(text)
        self.assertEqual(loaded, positions)

    def test_header_xy_only(self):
        loaded = import_bsf_csv_text("X;Y\n0;0\n100.500;50.250\n")
        self.assertEqual(loaded[1], BSFCoordinatePosition(100.5, 50.25))

    def test_headerless(self):
        loaded = import_bsf_csv_text("0;0\n100;50\n200;-75\n")
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[2], BSFCoordinatePosition(200.0, -75.0))

    def test_decimal_comma(self):
        loaded = import_bsf_csv_text("X;Y\n100,5;50,25\n-20,75;10,125\n")
        self.assertEqual(loaded[0], BSFCoordinatePosition(100.5, 50.25))
        self.assertAlmostEqual(loaded[1].x, -20.75)
        self.assertAlmostEqual(loaded[1].y, 10.125)

    def test_tab_decimal_comma(self):
        loaded = import_bsf_csv_text("100,5\t50,25\n")
        self.assertEqual(loaded[0], BSFCoordinatePosition(100.5, 50.25))

    def test_atomic_fail(self):
        with self.assertRaises(CoordinateParseError):
            import_bsf_csv_text("0;0\n100;ABC\n200;50\n")

    def test_encoding_roundtrip_file(self):
        from coordinates.bsf_csv import read_bsf_csv_file, write_bsf_csv_file

        positions = [BSFCoordinatePosition(-100.5, 50.25)]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "BSF_TEST.csv")
            write_bsf_csv_file(path, positions)
            with open(path, "rb") as handle:
                raw = handle.read()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            loaded = read_bsf_csv_file(path)
        self.assertEqual(loaded, positions)


class TestBsfPersistGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        _fill_bsf_app(self.app)

    def test_gui_json_roundtrip(self):
        doc = self.app._collect_bsf_position_list_document()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "BSF_TEST.bsf.json")
            save_bsf_document_json(path, doc)
            self.app.bsf_coord_rows = []
            self.app.entries["bund_thickness"].delete(0, "end")
            self.app.entries["bund_thickness"].insert(0, "99")
            loaded = load_bsf_document_json(path)
            self.app._apply_bsf_position_list_document(loaded)
        self.assertEqual(self.app.entries["program_name"].get(), "BSF_TEST")
        self.assertEqual(self.app.entries["bund_thickness"].get(), "18")
        self.assertEqual(self.app.entries["sink_depth"].get(), "38")
        self.assertEqual(self.app.entries["clearance"].get(), "23")
        self.assertEqual(self.app.z0_var.get(), "Z0 ist Unterkante Bund")
        self.assertEqual(self.app.entries["blade_thickness"].get(), "3")
        self.assertEqual(self.app.blade_measurement_var.get(), SPINDLE_LABEL)
        self.assertEqual(self.app.entries["safe_z"].get(), "100")
        self.assertEqual(len(self.app.bsf_coord_rows), 3)
        self.assertEqual(self.app.bsf_coord_rows[1], BSFCoordinatePosition(100.0, 50.0))

    def test_m_function_roundtrip_then_nc(self):
        self.app.m_activate_var.set("Freitext / Eigener M-Befehl")
        self.app.on_m_activate_change(None)
        self.app.m_activate_custom.config(state="normal")
        self.app.m_activate_custom.delete(0, "end")
        self.app.m_activate_custom.insert(0, "M107")
        self.app.m_deactivate_var.set("Eigener M-Befehl")
        self.app.on_m_deactivate_change(None)
        self.app.m_deactivate_custom.config(state="normal")
        self.app.m_deactivate_custom.delete(0, "end")
        self.app.m_deactivate_custom.insert(0, "M108")
        mb, orig = _silence_boxes()
        try:
            self.app.generate_bsf_code()
            before = self.app.output_text.get("1.0", "end")
            doc = self.app._collect_bsf_position_list_document()
            self.app.m_activate_var.set("IKZ Ein (M8)")
            self.app.on_m_activate_change(None)
            self.app._apply_bsf_position_list_document(doc)
            self.assertEqual(self.app.m_activate_var.get(), "Freitext / Eigener M-Befehl")
            self.assertEqual(self.app.m_activate_custom.get(), "M107")
            self.assertEqual(self.app.m_deactivate_var.get(), "Eigener M-Befehl")
            self.assertEqual(self.app.m_deactivate_custom.get(), "M108")
            self.app.generate_bsf_code()
            after = self.app.output_text.get("1.0", "end")
        finally:
            _restore_boxes(mb, orig)
        self.assertEqual(before, after)
        self.assertIn("M107", after)
        self.assertIn("M108", after)

    def test_nc_roundtrip(self):
        mb, orig = _silence_boxes()
        try:
            self.app.generate_bsf_code()
            before = self.app.output_text.get("1.0", "end")
            doc = self.app._collect_bsf_position_list_document()
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "rt.bsf.json")
                save_bsf_document_json(path, doc)
                self.app.bsf_coord_rows = [BSFCoordinatePosition(9, 9)]
                self.app.entries["bund_thickness"].delete(0, "end")
                self.app.entries["bund_thickness"].insert(0, "11")
                self.app.entries["blade_thickness"].delete(0, "end")
                self.app.entries["blade_thickness"].insert(0, "5")
                self.app.blade_measurement_var.set(TIP_LABEL)
                self.app.entries["program_name"].delete(0, "end")
                self.app.entries["program_name"].insert(0, "OTHER")
                loaded = load_bsf_document_json(path)
                self.app._apply_bsf_position_list_document(loaded)
                self.app.generate_bsf_code()
                after = self.app.output_text.get("1.0", "end")
        finally:
            _restore_boxes(mb, orig)
        self.assertEqual(before, after)
        self.assertIn("BEGIN PGM BSF_TEST MM", after)
        self.assertIn("M5 ; Spindel aus", after)
        self.assertIn("CYCL DEF 9.1 V.ZEIT 1.5", after)

    def test_atomic_load_keeps_project(self):
        payload = document_to_dict(_doc())
        payload["positions"] = [
            {"x": 1.0, "y": 1.0},
            {"x": 2.0, "y": 2.0},
            {"x": 3.0},
        ]
        before_rows = list(self.app.bsf_coord_rows)
        before_bund = self.app.entries["bund_thickness"].get()
        with self.assertRaises(BSFDocumentError):
            parse_document_dict(payload)
        self.assertEqual(list(self.app.bsf_coord_rows), before_rows)
        self.assertEqual(self.app.entries["bund_thickness"].get(), before_bund)

    def test_csv_does_not_change_process(self):
        before = (
            self.app.entries["bund_thickness"].get(),
            self.app.entries["sink_depth"].get(),
            self.app.entries["blade_thickness"].get(),
            self.app.blade_measurement_var.get(),
            self.app.entries["spindle_speed"].get(),
            self.app.m_activate_var.get(),
            self.app.entries["safe_z"].get(),
        )
        imported = import_bsf_csv_text("0;0\n200;80\n")
        self.app.bsf_coord_rows = list(imported)
        self.assertEqual(
            (
                self.app.entries["bund_thickness"].get(),
                self.app.entries["sink_depth"].get(),
                self.app.entries["blade_thickness"].get(),
                self.app.blade_measurement_var.get(),
                self.app.entries["spindle_speed"].get(),
                self.app.m_activate_var.get(),
                self.app.entries["safe_z"].get(),
            ),
            before,
        )
        self.assertEqual(len(self.app.bsf_coord_rows), 2)

    def test_csv_append(self):
        existing = list(self.app.bsf_coord_rows)
        imported = import_bsf_csv_text("300;1\n400;2\n")
        self.app.bsf_coord_rows.extend(imported)
        self.assertEqual(self.app.bsf_coord_rows[:3], existing)
        self.assertEqual(self.app.bsf_coord_rows[3], BSFCoordinatePosition(300.0, 1.0))
        self.assertEqual(self.app.bsf_coord_rows[4], BSFCoordinatePosition(400.0, 2.0))

    def test_csv_atomic_gui_unchanged(self):
        previous = list(self.app.bsf_coord_rows)
        with self.assertRaises(CoordinateParseError):
            import_bsf_csv_text("0;0\n100;ABC\n")
        self.assertEqual(list(self.app.bsf_coord_rows), previous)

    def test_duplicates_recalculated(self):
        payload = document_to_dict(
            _doc(
                positions=[
                    BSFCoordinatePosition(0, 0),
                    BSFCoordinatePosition(0, 0),
                ]
            )
        )
        self.assertNotIn("duplicate", json.dumps(payload))
        loaded = parse_document_dict(payload)
        result = validate_bsf_coordinate_list(loaded.positions)
        self.assertTrue(result.ok)
        self.assertTrue(result.warnings)
        self.app._apply_bsf_position_list_document(loaded)
        self.app._refresh_bsf_coord_tree()
        self.assertEqual(self.app.bsf_coord_tree.set("0", "status"), "Doppelte XY-Position")

    def test_preview_after_load(self):
        self.app._apply_bsf_position_list_document(_doc())
        snap = self.app.build_bsf_preview_snapshot()
        self.assertEqual(len(snap.points), 3)
        self.assertAlmostEqual(snap.points[1].x, 100.0)
        self.assertAlmostEqual(snap.points[1].y, 50.0)

    def test_help_after_load(self):
        self.app._apply_bsf_position_list_document(_doc())
        help_snap = self.app.build_bsf_geometry_help_snapshot()
        self.assertEqual(help_snap.bund_thickness, 18.0)
        self.assertEqual(help_snap.blade_thickness, 3.0)
        self.assertIs(help_snap.measurement_reference, BladeMeasurementReference.SPINDLE_SIDE_EDGE)
        wp = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=True)
        offset = blade_reference_offset(3.0, BladeMeasurementReference.SPINDLE_SIDE_EDGE)
        programmed = apply_blade_offset(wp, offset)
        self.assertEqual(help_snap.programmed_z_sink_finish, programmed["z_sink_finish"])
        self.assertEqual(help_snap.programmed_z_clearance, programmed["z_clearance"])

    def test_bgf_json_not_accepted(self):
        with self.assertRaises(BSFDocumentError):
            parse_document_dict(
                {
                    "format": "BGF_POSITION_LIST",
                    "version": 1,
                    "tool": {"thread_size": "M10", "article_no": "x", "tool_number": 8},
                    "program": {"name": "X"},
                    "safety": {"approach_clearance": 1, "safe_z": 100, "end_safe_z": 200},
                    "positions": [{"x": 0, "y": 0, "surface_z": 0, "thread_depth": 20}],
                }
            )

    def test_fail_closed_invalid_blade_not_applied(self):
        before = self.app.blade_measurement_var.get()
        payload = document_to_dict(_doc())
        payload["blade"]["measurement_reference"] = "UNKNOWN"
        with self.assertRaises(BSFDocumentError):
            parse_document_dict(payload)
        self.assertEqual(self.app.blade_measurement_var.get(), before)

    def test_buttons_exist_in_bsf_panel(self):
        self.assertTrue(hasattr(self.app, "bsf_coord_save_list"))
        self.assertTrue(hasattr(self.app, "bsf_coord_load_list"))
        self.assertTrue(hasattr(self.app, "bsf_coord_import_csv"))
        self.assertTrue(hasattr(self.app, "bsf_coord_export_csv"))


if __name__ == "__main__":
    unittest.main()
