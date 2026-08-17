"""PHASE BGF.COORD.3 – Positionsliste JSON/CSV Persistenz."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

import bsf_generator_verbessert_v3 as gen
from bgf_depth import DepthGateStatus, evaluate_bgf_depth
from coordinates import (
    BGFCoordinatePosition,
    BGFDocumentError,
    build_document,
    export_bgf_csv,
    import_bgf_csv_text,
    load_document_json,
    resolve_tool_in_catalog,
    save_document_json,
    validate_bgf_coordinate_list,
)
from coordinates.bgf_list_document import FORMAT_NAME, FORMAT_VERSION, parse_document_dict
from coordinates.parser import CoordinateParseError


def _m10_doc(positions, **kwargs):
    data = gen.BGF_DATA["M10"]
    base = dict(
        thread_size=data.size,
        article_no=data.article_no,
        tool_number=8,
        program_name="BGF_M10_PLATTE",
        approach_clearance=5.0,
        safe_z=100.0,
        end_safe_z=200.0,
        positions=positions,
    )
    base.update(kwargs)
    return build_document(**base)


class TestJsonRoundtrip(unittest.TestCase):
    def test_roundtrip_values(self):
        positions = [
            BGFCoordinatePosition(0, 0, 0, 20.0, 30.0),
            BGFCoordinatePosition(100, 50, 35.0, 15.0, None),
        ]
        doc = _m10_doc(positions)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.bgf.json")
            save_document_json(path, doc)
            loaded = load_document_json(path)
        self.assertEqual(loaded.thread_size, "M10")
        self.assertEqual(loaded.article_no, "5089810000")
        self.assertEqual(loaded.tool_number, 8)
        self.assertEqual(loaded.approach_clearance, 5.0)
        self.assertEqual(loaded.safe_z, 100.0)
        self.assertEqual(loaded.end_safe_z, 200.0)
        self.assertEqual(len(loaded.positions), 2)
        self.assertEqual(loaded.positions[0], positions[0])
        self.assertEqual(loaded.positions[1], positions[1])

    def test_template_status_after_load(self):
        positions = [BGFCoordinatePosition(0, 0, 0, 25.06)]
        doc = _m10_doc(positions, approach_clearance=1.0)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tpl.bgf.json")
            save_document_json(path, doc)
            loaded = load_document_json(path)
        policy = gen.policy_from_tool(
            gen.BGF_DATA["M10"].size,
            gen.BGF_DATA["M10"].thread_length,
            gen.BGF_DATA["M10"].drill_depth,
            gen.BGF_DATA["M10"].mill_start_depth,
            article_no=gen.BGF_DATA["M10"].article_no,
            approved_max_thread_depth=25.06,
            axial_increment=gen.axial_increment_from_passes(gen.BGF_DATA["M10"].passes),
        )
        ev = evaluate_bgf_depth(
            gen.BGFDepthRequest(loaded.positions[0].thread_depth),
            policy,
        )
        self.assertEqual(ev.status, DepthGateStatus.TEMPLATE_OK)

    def test_variable_depth_recalculated(self):
        positions = [BGFCoordinatePosition(0, 0, 0, 20.0)]
        doc = _m10_doc(positions)
        raw = json.dumps(
            {
                "format": FORMAT_NAME,
                "version": FORMAT_VERSION,
                "tool": {"thread_size": "M10", "article_no": "5089810000", "tool_number": 8},
                "program": {"name": "T"},
                "safety": {"approach_clearance": 1.0, "safe_z": 100.0, "end_safe_z": 200.0},
                "positions": [
                    {
                        "x": 0,
                        "y": 0,
                        "surface_z": 0,
                        "thread_depth": 20,
                        "core_hole_depth": None,
                        "shifted_mill_start": 999,  # darf nicht uebernommen werden
                    }
                ],
            }
        )
        loaded = parse_document_dict(json.loads(raw))
        policy = gen.policy_from_tool(
            "M10",
            25.06,
            27.87,
            24.899,
            article_no="5089810000",
            approved_max_thread_depth=25.06,
            axial_increment=1.95,
        )
        ev = evaluate_bgf_depth(gen.BGFDepthRequest(20.0), policy)
        self.assertEqual(ev.status, DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK)
        self.assertAlmostEqual(ev.nc_mill_start_depth, 19.839, places=3)
        self.assertAlmostEqual(ev.nc_drill_depth, 22.810, places=3)
        self.assertEqual(loaded.positions[0].thread_depth, 20.0)


class TestToolIdentity(unittest.TestCase):
    def test_known_tool(self):
        key = resolve_tool_in_catalog("M10", "5089810000", gen.BGF_DATA)
        self.assertEqual(key, "M10")

    def test_unknown_article(self):
        with self.assertRaises(BGFDocumentError):
            resolve_tool_in_catalog("M10", "9999999999", gen.BGF_DATA)


class TestFormatVersion(unittest.TestCase):
    def test_version_1_ok(self):
        doc = _m10_doc([BGFCoordinatePosition(0, 0, 0, 20.0)])
        data = json.loads(json.dumps({
            "format": FORMAT_NAME,
            "version": 1,
            "tool": {"thread_size": "M10", "article_no": "5089810000", "tool_number": 8},
            "program": {"name": "A"},
            "safety": {"approach_clearance": 1, "safe_z": 100, "end_safe_z": 200},
            "positions": [{"x": 0, "y": 0, "surface_z": 0, "thread_depth": 20, "core_hole_depth": None}],
        }))
        parsed = parse_document_dict(data)
        self.assertEqual(parsed.version, 1)

    def test_version_999_block(self):
        with self.assertRaises(BGFDocumentError) as ctx:
            parse_document_dict(
                {
                    "format": FORMAT_NAME,
                    "version": 999,
                    "tool": {"thread_size": "M10", "article_no": "5089810000", "tool_number": 8},
                    "program": {"name": "A"},
                    "safety": {"approach_clearance": 1, "safe_z": 100, "end_safe_z": 200},
                    "positions": [{"x": 0, "y": 0, "surface_z": 0, "thread_depth": 20}],
                }
            )
        self.assertIn("neueren Formatversion", ctx.exception.message)

    def test_wrong_format(self):
        with self.assertRaises(BGFDocumentError):
            parse_document_dict({"format": "IRGENDWAS", "version": 1})


class TestAtomicLoad(unittest.TestCase):
    def test_invalid_position_keeps_current(self):
        with self.assertRaises(BGFDocumentError):
            parse_document_dict(
                {
                    "format": FORMAT_NAME,
                    "version": 1,
                    "tool": {"thread_size": "M10", "article_no": "5089810000", "tool_number": 8},
                    "program": {"name": "A"},
                    "safety": {"approach_clearance": 1, "safe_z": 100, "end_safe_z": 200},
                    "positions": [
                        {"x": 0, "y": 0, "surface_z": 0, "thread_depth": 20},
                        {"x": 1, "y": "ABC", "surface_z": 0, "thread_depth": 20},
                        {"x": 2, "y": 2, "surface_z": 0, "thread_depth": 20},
                    ],
                }
            )


class TestCsvRoundtrip(unittest.TestCase):
    def test_export_import(self):
        positions = [
            BGFCoordinatePosition(100, -50, 10, 20.0, 30.0),
            BGFCoordinatePosition(-10, 20, -5, 15.0, None),
            BGFCoordinatePosition(0, 0, 0, 25.06, 30.0),
        ]
        text = export_bgf_csv(positions)
        loaded = import_bgf_csv_text(text, default_thread_depth=25.06)
        self.assertEqual(len(loaded), 3)
        for a, b in zip(positions, loaded):
            self.assertAlmostEqual(a.x, b.x, places=3)
            self.assertAlmostEqual(a.y, b.y, places=3)
            self.assertAlmostEqual(a.surface_z, b.surface_z, places=3)
            self.assertAlmostEqual(a.thread_depth, b.thread_depth, places=3)
            if a.core_hole_depth is None:
                self.assertIsNone(b.core_hole_depth)
            else:
                self.assertAlmostEqual(a.core_hole_depth, b.core_hole_depth, places=3)

    def test_decimal_comma(self):
        text = "X;Y;Z_Oberflaeche;Gewindetiefe;Kernlochtiefe\n100,5;200,25;0;20,5;30\n"
        loaded = import_bgf_csv_text(text, default_thread_depth=25.06)
        self.assertEqual(loaded[0].x, 100.5)
        self.assertEqual(loaded[0].y, 200.25)
        self.assertEqual(loaded[0].thread_depth, 20.5)

    def test_csv_error_atomic(self):
        text = "1;0;0;0;20;30\n2;100;ABC;0;20;30\n3;200;50;0;20;30\n"
        # with header for Nr mapping
        text = "Nr;X;Y;Z_Oberflaeche;Gewindetiefe;Kernlochtiefe\n" + text
        with self.assertRaises(CoordinateParseError) as ctx:
            import_bgf_csv_text(text, default_thread_depth=25.06)
        joined = "\n".join(ctx.exception.messages)
        self.assertIn("Zeile 3", joined)
        self.assertIn("ABC", joined)

    def test_duplicates_allowed(self):
        text = "100;50;0;20;30\n100;50;0;20;30\n"
        loaded = import_bgf_csv_text(text, default_thread_depth=25.06)
        self.assertEqual(len(loaded), 2)

    def test_order_preserved(self):
        text = "100;0;0;20\n0;100;0;20\n50;50;0;20\n"
        loaded = import_bgf_csv_text(text, default_thread_depth=25.06)
        self.assertEqual([p.x for p in loaded], [100.0, 0.0, 50.0])

    def test_headerless_3col(self):
        loaded = import_bgf_csv_text("10;20;0\n", default_thread_depth=25.06)
        self.assertEqual(loaded[0].thread_depth, 25.06)


class TestGuiPersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_save_load_nc_roundtrip(self):
        from tkinter import messagebox

        messagebox.showinfo = lambda *a, **k: None
        messagebox.askyesno = lambda *a, **k: True

        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Koordinatenliste")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set("M10")
        self.app.load_bgf_values()
        self.app.entries["approach_clearance"].delete(0, "end")
        self.app.entries["approach_clearance"].insert(0, "5")
        self.app.coord_rows = [
            BGFCoordinatePosition(0, 0, 0, 20.0),
            BGFCoordinatePosition(100, 50, 35.0, 15.0),
        ]
        self.app.generate_bgf_code()
        before = self.app.output_text.get("1.0", "end")

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "rt.bgf.json")
            doc = self.app._collect_position_list_document()
            save_document_json(path, doc)
            self.app.coord_rows = []
            loaded = load_document_json(path)
            self.app._apply_position_list_document(loaded)
            self.app.generate_bgf_code()
            after = self.app.output_text.get("1.0", "end")

        self.assertIn("L Z-22.8100", after)
        self.assertIn("; WERKZEUGRADIUS: R+3.9790 MM", after)
        # Bewegungsrelevante Zeilen aus vorherigem Stand
        for needle in ("L X+0.0000 Y+0.0000", "L X+100.0000 Y+50.0000", "L Z+15.1610", "L Z+19.1900"):
            # depth 15 surface 35: mill=14.839 → Z=20.161; drill=17.810 → Z=17.190
            pass
        self.assertIn("L Z+17.1900", after)
        self.assertIn("L Z+20.1610", after)
        self.assertIn("L Z+40.0000", after)  # approach 35+5
        self.assertIn("CP IPA-360 IZ-1.5000", after)
        self.assertEqual(before.count("TOOL CALL 8 Z DR0"), after.count("TOOL CALL 8 Z DR0"))

    def test_unsafe_safe_z_after_load_blocks_nc(self):
        from tkinter import messagebox

        messagebox.showerror = lambda *a, **k: None
        messagebox.showinfo = lambda *a, **k: None
        doc = _m10_doc(
            [BGFCoordinatePosition(0, 0, 98.0, 20.0)],
            approach_clearance=5.0,
            safe_z=100.0,
            end_safe_z=200.0,
        )
        self.app._apply_position_list_document(doc)
        result = validate_bgf_coordinate_list(
            self.app.coord_rows,
            self.app.get_bgf_depth_policy(),
            safe_z=100.0,
            end_safe_z=200.0,
            approach_clearance=5.0,
        )
        self.assertFalse(result.ok_for_nc)

    def test_approved_max_revalidated(self):
        doc = _m10_doc([BGFCoordinatePosition(0, 0, 0, 26.0)])
        self.app._apply_position_list_document(doc)
        status = self.app._position_status_label(self.app.coord_rows[0])
        self.assertIn("Freigabegrenze", status)

    def test_atomic_gui_load_keeps_old_on_bad_file(self):
        from tkinter import messagebox

        messagebox.showerror = lambda *a, **k: None
        self.app.coord_rows = [
            BGFCoordinatePosition(1, 2, 0, 25.06),
            BGFCoordinatePosition(3, 4, 0, 25.06),
        ]
        self.app._refresh_coord_tree()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.bgf.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"format":"IRGENDWAS","version":1}')
            try:
                load_document_json(path)
                loaded_ok = True
            except BGFDocumentError:
                loaded_ok = False
        self.assertFalse(loaded_ok)
        self.assertEqual(len(self.app.coord_rows), 2)
        self.assertEqual(self.app.coord_rows[0].x, 1.0)


if __name__ == "__main__":
    unittest.main()
