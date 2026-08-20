"""PHASE APP.PROGRAMMER.1 – CNC-Programmierer getrennt vom Software-Autor."""

from __future__ import annotations

import os
import tempfile
import unittest

from app_info import APP_AUTHOR
from bgf_chain import BGF_END_MODE_CHAIN, BGF_END_MODE_STANDALONE, bgf_end_mode_label
from coordinates import (
    BGFCoordinatePosition,
    BSFCoordinatePosition,
    build_bsf_document,
    build_document,
    import_bgf_csv_text,
    load_bsf_document_json,
    load_document_json,
    save_bsf_document_json,
    save_document_json,
    write_bgf_csv_file,
)
from coordinates.bgf_list_document import FORMAT_VERSION as BGF_FORMAT_VERSION
from coordinates.bgf_list_document import document_to_dict as bgf_document_to_dict
from coordinates.bgf_list_document import parse_document_dict as parse_bgf_dict
from coordinates.bsf_list_document import FORMAT_VERSION as BSF_FORMAT_VERSION
from coordinates.bsf_list_document import document_to_dict as bsf_document_to_dict
from coordinates.bsf_list_document import parse_document_dict as parse_bsf_dict
from bsf_blade import BladeMeasurementReference, MEASUREMENT_LABELS
from nc_programmer import (
    MAX_PROGRAMMER_LENGTH,
    ProgrammerError,
    normalize_programmer,
    programmer_comment_line,
)
import bsf_generator_verbessert_v3 as gen
from ui import MODE_BGF, MODE_BSF
from ui.about import open_about_window


class TestProgrammerNormalize(unittest.TestCase):
    def test_empty_and_whitespace(self):
        self.assertEqual(normalize_programmer(""), "")
        self.assertEqual(normalize_programmer("   "), "")
        self.assertEqual(normalize_programmer(None), "")

    def test_trim(self):
        self.assertEqual(normalize_programmer("   Peter Müller   "), "Peter Müller")

    def test_newline_blocked(self):
        with self.assertRaises(ProgrammerError):
            normalize_programmer("Peter\nM30")
        with self.assertRaises(ProgrammerError):
            normalize_programmer("Peter\rM30")

    def test_semicolon_blocked(self):
        with self.assertRaises(ProgrammerError):
            normalize_programmer("Firma; Name")

    def test_control_char_blocked(self):
        with self.assertRaises(ProgrammerError):
            normalize_programmer("Peter\tMustermann")

    def test_length_limit(self):
        ok = "A" * MAX_PROGRAMMER_LENGTH
        self.assertEqual(normalize_programmer(ok), ok)
        with self.assertRaises(ProgrammerError):
            normalize_programmer("A" * (MAX_PROGRAMMER_LENGTH + 1))

    def test_comment_line(self):
        self.assertIsNone(programmer_comment_line(""))
        self.assertEqual(
            programmer_comment_line("Max Mustermann"),
            "; PROGRAMMIERER: Max Mustermann",
        )


class TestProgrammerNcGui(unittest.TestCase):
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
        self.app.programmer_var.set("")
        self.app.output_text.delete("1.0", "end")

    def _prepare_bgf_single(self):
        app = self.app
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

    def _prepare_bsf_single(self):
        app = self.app
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.entries["blade_thickness"].delete(0, "end")
        app.entries["blade_thickness"].insert(0, "3")
        app.blade_measurement_var.set(MEASUREMENT_LABELS[BladeMeasurementReference.SPINDLE_SIDE_EDGE])

    def test_default_empty_and_no_jens_in_header(self):
        app = self.app
        self.assertEqual(app.programmer_var.get(), "")
        self.assertIn("programmer", app.entries)
        for child in app.main_frame.winfo_children():
            try:
                text = str(child.cget("text"))
            except Exception:
                continue
            self.assertNotIn("Jens Behm", text)
            self.assertNotIn("Programmierung von", text)

    def test_empty_programmer_omits_comment_bgf_bsf(self):
        self.assertEqual(APP_AUTHOR, "Jens Behm")
        self.app.programmer_var.set("")
        self._prepare_bgf_single()
        self.app.generate_bgf_code()
        bgf = self.app.output_text.get("1.0", "end")
        self.assertNotIn("PROGRAMMIERER", bgf)
        self.assertNotIn("Jens Behm", bgf)

        self._prepare_bsf_single()
        self.app.generate_bsf_code()
        bsf = self.app.output_text.get("1.0", "end")
        self.assertNotIn("PROGRAMMIERER", bsf)
        self.assertNotIn("Jens Behm", bsf)

    def test_named_programmer_once_bgf_bsf(self):
        self.app.programmer_var.set("  Peter Müller  ")
        self._prepare_bgf_single()
        self.app.generate_bgf_code()
        bgf = self.app.output_text.get("1.0", "end")
        self.assertEqual(bgf.count("; PROGRAMMIERER: Peter Müller"), 1)
        self.assertIn("BEGIN PGM", bgf)

        self._prepare_bsf_single()
        self.app.generate_bsf_code()
        bsf = self.app.output_text.get("1.0", "end")
        self.assertEqual(bsf.count("; PROGRAMMIERER: Peter Müller"), 1)

    def test_mode_switch_preserves_programmer(self):
        self.app.programmer_var.set("M. Mustermann")
        self.app.mode_var.set(MODE_BGF)
        self.app.on_mode_change(None)
        self.app.mode_var.set(MODE_BSF)
        self.app.on_mode_change(None)
        self.app.mode_var.set(MODE_BGF)
        self.app.on_mode_change(None)
        self.assertEqual(self.app.programmer_var.get(), "M. Mustermann")

    def test_newline_blocks_nc(self):
        from unittest import mock

        self._prepare_bgf_single()
        self.app.generate_bgf_code()
        before = self.app.output_text.get("1.0", "end")
        self.assertIn("BEGIN PGM", before)
        with mock.patch.object(self.app.programmer_var, "get", return_value="Peter\nM30"):
            self.app.generate_bgf_code()
            after = self.app.output_text.get("1.0", "end")
        self.assertEqual(before, after)
        self.assertNotIn("; PROGRAMMIERER: Peter", after)
        self.assertNotIn("\nM30\n", after)

    def test_umlaut_cp1252_export(self):
        self.app.programmer_var.set("Jörg Müller")
        self._prepare_bgf_single()
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("; PROGRAMMIERER: Jörg Müller", code)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "umlaut.H")
            with open(path, "w", encoding="cp1252", errors="replace") as handle:
                handle.write(code)
            loaded = open(path, "r", encoding="cp1252").read()
        self.assertIn("Jörg Müller", loaded)

    def test_info_window_still_has_author(self):
        win = open_about_window(self.app.root)
        texts = []

        def collect(widget):
            try:
                texts.append(str(widget.cget("text")))
            except Exception:
                pass
            for child in widget.winfo_children():
                collect(child)

        collect(win)
        blob = "\n".join(texts)
        self.assertIn(APP_AUTHOR, blob)
        self.assertIn("behm-it.de", blob)
        win.destroy()

    def test_csv_does_not_change_programmer(self):
        self.app.programmer_var.set("CSV Guard")
        self.app.mode_var.set(MODE_BGF)
        self.app.on_mode_change(None)
        rows = [
            BGFCoordinatePosition(0, 0, 0, 20.0),
            BGFCoordinatePosition(10, 10, 0, 20.0),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.csv")
            write_bgf_csv_file(path, rows)
            text = open(path, encoding="utf-8").read()
            imported = import_bgf_csv_text(text, default_thread_depth=20.0)
        self.app.coord_rows = imported
        self.assertEqual(self.app.programmer_var.get(), "CSV Guard")
        self.assertNotIn("programmer", text.lower())


class TestProgrammerJson(unittest.TestCase):
    def test_bgf_roundtrip_and_legacy(self):
        data = gen.BGF_DATA["M10"]
        doc = build_document(
            thread_size=data.size,
            article_no=data.article_no,
            tool_number=8,
            program_name="BGF_M10_PLATTE",
            approach_clearance=5.0,
            safe_z=100.0,
            end_safe_z=200.0,
            positions=[BGFCoordinatePosition(0, 0, 0, 20.0)],
            programmer="Max Mustermann",
        )
        self.assertEqual(BGF_FORMAT_VERSION, 1)
        payload = bgf_document_to_dict(doc)
        self.assertEqual(payload["program"]["programmer"], "Max Mustermann")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.bgf.json")
            save_document_json(path, doc)
            loaded = load_document_json(path)
        self.assertEqual(loaded.programmer, "Max Mustermann")

        legacy = bgf_document_to_dict(
            build_document(
                thread_size=data.size,
                article_no=data.article_no,
                tool_number=8,
                program_name="LEGACY",
                approach_clearance=5.0,
                safe_z=100.0,
                end_safe_z=200.0,
                positions=[BGFCoordinatePosition(1, 2, 0, 20.0)],
            )
        )
        del legacy["program"]["programmer"]
        parsed = parse_bgf_dict(legacy)
        self.assertEqual(parsed.programmer, "")

    def test_bsf_roundtrip_and_legacy(self):
        doc = build_bsf_document(
            program_name="BSF_PLATTE",
            tool_number=8,
            blank_size=1000.0,
            blank_height=60.0,
                tool_profile_key="BSF_C_1000_050_10_5_23",
                        spindle_speed=1500,
            feed=120.0,
            dwell_time=1.5,
            reduce_approach=True,
            approach_feed_factor=0.5,
            activate_preset="IKZ Ein (M7)",
            activate_custom="",
            deactivate_preset="Alles AUS (M9)",
            deactivate_custom="",
            safe_z=100.0,
            end_safe_z=200.0,
            positions=[BSFCoordinatePosition(0, 0)],
            entry_edge_z=20.0,
            exit_edge_z=-5.0,
            target_surface_z=38.0,
            programmer="Max Mustermann",
        )
        self.assertEqual(BSF_FORMAT_VERSION, 5)
        payload = bsf_document_to_dict(doc)
        self.assertEqual(payload["program"]["programmer"], "Max Mustermann")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.bsf.json")
            save_bsf_document_json(path, doc)
            loaded = load_bsf_document_json(path)
        self.assertEqual(loaded.programmer, "Max Mustermann")

        legacy = bsf_document_to_dict(
            build_bsf_document(
                program_name="BSF_LEGACY",
                tool_number=8,
                blank_size=1000.0,
                blank_height=60.0,
                        tool_profile_key="BSF_C_1000_050_10_5_23",
                                        spindle_speed=1500,
                feed=120.0,
                dwell_time=1.5,
                reduce_approach=False,
                approach_feed_factor=1.0,
                activate_preset="IKZ Ein (M7)",
                activate_custom="",
                deactivate_preset="Alles AUS (M9)",
                deactivate_custom="",
                safe_z=100.0,
                end_safe_z=200.0,
                positions=[BSFCoordinatePosition(1, 1)],
                entry_edge_z=20.0,
                exit_edge_z=-5.0,
                target_surface_z=38.0,
            )
        )
        del legacy["program"]["programmer"]
        legacy["version"] = 1
        legacy["blade"] = {"thickness": 3.0, "measurement_reference": "SPINDLE_SIDE_EDGE"}
        del legacy["tool"]
        legacy["workpiece"] = {
            "z_reference": "BOTTOM_EDGE",
            "reference_z": 0.0,
            "bund_thickness": 18.0,
            "sink_finish": 38.0,
            "clearance": 23.0,
        }
        parsed = parse_bsf_dict(legacy)
        self.assertEqual(parsed.programmer, "")

    def test_gui_json_roundtrip_sets_field(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.bgf_size_var.set("M10")
        app.load_bgf_values()
        app.programmer_var.set("Max Mustermann")
        app.bgf_end_mode_var.set(bgf_end_mode_label(BGF_END_MODE_STANDALONE))
        app.coord_rows = [BGFCoordinatePosition(0, 0, 0, 20.0)]
        doc = app._collect_position_list_document()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gui.bgf.json")
            save_document_json(path, doc)
            loaded = load_document_json(path)
        app.programmer_var.set("")
        app.bgf_end_mode_var.set(bgf_end_mode_label(BGF_END_MODE_CHAIN))
        app._apply_position_list_document(loaded)
        self.assertEqual(app.programmer_var.get(), "Max Mustermann")
        self.assertEqual(app.get_bgf_end_mode(), BGF_END_MODE_STANDALONE)
        app.generate_bgf_code()
        self.assertIn("; PROGRAMMIERER: Max Mustermann", app.output_text.get("1.0", "end"))
        self.assertIn("; PROGRAMMENDE: EINZELPROGRAMM / M30", app.output_text.get("1.0", "end"))
        root.destroy()


if __name__ == "__main__":
    unittest.main()
