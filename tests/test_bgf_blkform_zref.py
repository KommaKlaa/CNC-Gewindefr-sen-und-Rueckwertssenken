"""PHASE BLKFORM.ZREF.1 – Rohteil-Oberkante und Bearbeitungsflaeche trennen."""

from __future__ import annotations

import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tkinter as tk

import bsf_generator_verbessert_v3 as gen
from coordinates import BGFCoordinatePosition, BSFCoordinatePosition, import_bgf_csv_text, write_bgf_csv_file
from coordinates.bgf_csv import CSV_HEADER
from coordinates.bsf_list_document import build_bsf_document, document_to_dict, parse_document_dict
from heule_bsf_tools import BSF_TOOL_PROFILES
from nc_state import NC_STATE_CURRENT, NC_STATE_STALE, collect_nc_input_payload, fingerprint_nc_inputs
from stock_z import SURFACE_OUTSIDE_STOCK_MESSAGE, blk_form_z_extents, is_surface_inside_stock
from ui import MODE_BGF, MODE_BSF

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]


def _set(app, key: str, value) -> None:
    if key not in app.entries:
        return
    app.entries[key].delete(0, tk.END)
    app.entries[key].insert(0, str(value))


def _blk_lines(code: str) -> list[str]:
    return [ln.rstrip() for ln in code.splitlines() if ln.startswith("BLK FORM")]


def _machining_without_blk(code: str) -> list[str]:
    return [ln for ln in code.splitlines() if not ln.startswith("BLK FORM")]


def _prepare_bgf_circle(
    app,
    *,
    diameter="430",
    count="6",
    start_angle="0",
    center_x="0",
    center_y="0",
    surface_z="-10",
    raw_stock_top_z="0",
    blank_height="60",
    blank_size="1000",
    approach_clearance="10",
    size="M16",
) -> None:
    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    app.position_mode_var.set("Teilkreis")
    app.on_position_mode_change(None)
    app.bgf_size_var.set(size)
    app.load_bgf_values()
    _set(app, "diameter", diameter)
    _set(app, "count", count)
    _set(app, "start_angle", start_angle)
    _set(app, "center_x", center_x)
    _set(app, "center_y", center_y)
    _set(app, "circle_surface_z", surface_z)
    _set(app, "approach_clearance", approach_clearance)
    _set(app, "blank_size", blank_size)
    _set(app, "blank_height", blank_height)
    _set(app, "raw_stock_top_z", raw_stock_top_z)
    _set(app, "program_name", "HPR5000M16")


def _widget_texts(widget) -> list[str]:
    texts = []
    try:
        texts.append(str(widget.cget("text")))
    except Exception:
        pass
    for child in widget.winfo_children():
        texts.extend(_widget_texts(child))
    return texts


class TestStockZHelpers(unittest.TestCase):
    def test_blk_form_z_extents(self):
        self.assertEqual(blk_form_z_extents(0.0, 60.0), (-60.0, 0.0))
        self.assertEqual(blk_form_z_extents(20.0, 60.0), (-40.0, 20.0))
        self.assertEqual(blk_form_z_extents(-10.0, 60.0), (-70.0, -10.0))

    def test_surface_inside_stock_user_case(self):
        self.assertTrue(is_surface_inside_stock(-10.0, 0.0, 60.0))
        self.assertTrue(is_surface_inside_stock(0.0, 0.0, 60.0))
        self.assertTrue(is_surface_inside_stock(-60.0, 0.0, 60.0))
        self.assertFalse(is_surface_inside_stock(5.0, 0.0, 60.0))
        self.assertFalse(is_surface_inside_stock(-65.0, 0.0, 60.0))


class TestBlkFormZref(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_raw_stock_top_z_default_zero(self):
        root = tk.Tk()
        root.withdraw()
        try:
            fresh = gen.BSFGeneratorGUI(root)
            self.assertEqual(float(fresh.entries["raw_stock_top_z"].get().replace(",", ".")), 0.0)
            self.assertEqual(fresh.entries["raw_stock_top_z"].get(), "0.000")
        finally:
            root.destroy()

    def test_gui_labels_separate_stock_and_surface(self):
        texts = " | ".join(_widget_texts(self.app.common_frame))
        self.assertIn("Rohteil-Oberkante Z [mm]:", texts)
        self.assertIn("Rohteil-Hoehe Z (mm):", texts)
        self.assertEqual(self.app._circle_surface_z_label.cget("text"), "Bohrungsanfang Z [mm]:")
        self.assertEqual(self.app._single_surface_z_label.cget("text"), "Bohrungsanfang Z [mm]:")

    def test_user_case_blk_form_and_m16_machining(self):
        app = self.app
        _prepare_bgf_circle(app)
        app.generate_code()
        code = app.output_text.get("1.0", tk.END)
        blk = _blk_lines(code)
        self.assertEqual(
            blk[0],
            "BLK FORM 0.1 Z X-500.0000 Y-500.0000 Z-60.0000",
        )
        self.assertEqual(
            blk[1],
            "BLK FORM 0.2 X+500.0000 Y+500.0000 Z+0.0000",
        )
        self.assertNotIn("Z-70.0000", blk[0])
        self.assertNotIn("Z-10.0000", " ".join(blk))
        self.assertIn("LP PR+215.0000 PA+Q1 R0 FMAX ; Teilkreisposition", code)
        self.assertIn("CC X+0.0000 Y+0.0000 ; Teilkreis-Mitte / Pol", code)
        self.assertIn("LBL 1 ; Schleifenanfang Teilkreis", code)
        self.assertIn("CALL LBL 100", code)
        self.assertIn("L Z+0.0000 R0 FMAX M13", code)
        self.assertIn("L Z-12.1000 F682 M", code)
        self.assertIn("L Z-47.1160 F2046 M", code)
        self.assertIn("L Z-43.0750 R0 FMAX M", code)

    def test_top_zero_surface_minus_ten(self):
        app = self.app
        _prepare_bgf_circle(app, raw_stock_top_z="0", surface_z="-10", blank_height="60")
        app.generate_code()
        blk = _blk_lines(app.output_text.get("1.0", tk.END))
        self.assertIn("Z-60.0000", blk[0])
        self.assertIn("Z+0.0000", blk[1])

    def test_positive_top_and_independent_surface(self):
        app = self.app
        _prepare_bgf_circle(app, raw_stock_top_z="+20", surface_z="+10", blank_height="60")
        app.generate_code()
        code = app.output_text.get("1.0", tk.END)
        blk = _blk_lines(code)
        self.assertIn("Z-40.0000", blk[0])
        self.assertIn("Z+20.0000", blk[1])
        self.assertIn("L Z+20.0000 R0 FMAX M13", code)
        self.assertIn("L Z+7.9000 F682 M", code)
        self.assertIn("L Z-27.1160 F2046 M", code)
        self.assertIn("L Z-23.0750 R0 FMAX M", code)

    def test_negative_top_and_independent_surface(self):
        app = self.app
        _prepare_bgf_circle(app, raw_stock_top_z="-10", surface_z="-20", blank_height="60")
        app.generate_code()
        code = app.output_text.get("1.0", tk.END)
        blk = _blk_lines(code)
        self.assertIn("Z-70.0000", blk[0])
        self.assertIn("Z-10.0000", blk[1])
        self.assertIn("L Z-10.0000 R0 FMAX M13", code)
        self.assertIn("L Z-22.1000 F682 M", code)
        self.assertIn("L Z-57.1160 F2046 M", code)
        self.assertIn("L Z-53.0750 R0 FMAX M", code)

    def test_blk_form_depends_only_on_raw_stock_top(self):
        app = self.app
        _prepare_bgf_circle(app, raw_stock_top_z="0", surface_z="-10")
        app.generate_code()
        blk_a = _blk_lines(app.output_text.get("1.0", tk.END))
        _set(app, "circle_surface_z", "-20")
        app.generate_code()
        blk_b = _blk_lines(app.output_text.get("1.0", tk.END))
        self.assertEqual(blk_a, blk_b)
        self.assertIn("Z-60.0000", blk_b[0])
        self.assertIn("Z+0.0000", blk_b[1])

    def test_bgf_machining_depends_only_on_surface_z(self):
        app = self.app
        _prepare_bgf_circle(app, raw_stock_top_z="0", surface_z="-10")
        app.generate_code()
        motion_a = _machining_without_blk(app.output_text.get("1.0", tk.END))
        _set(app, "raw_stock_top_z", "0")
        app.generate_code()
        motion_same = _machining_without_blk(app.output_text.get("1.0", tk.END))
        self.assertEqual(motion_a, motion_same)

        _set(app, "raw_stock_top_z", "-5")
        app.generate_code()
        code_b = app.output_text.get("1.0", tk.END)
        motion_b = _machining_without_blk(code_b)
        self.assertEqual(motion_a, motion_b)
        blk = _blk_lines(code_b)
        self.assertIn("Z-65.0000", blk[0])
        self.assertIn("Z-5.0000", blk[1])
        self.assertIn("L Z-47.1160 F2046 M", code_b)

    def test_surface_above_stock_blocked(self):
        app = self.app
        _prepare_bgf_circle(app, raw_stock_top_z="0", surface_z="+5", blank_height="60")
        app.output_text.delete("1.0", tk.END)
        errors = []

        def _err(*args, **kwargs):
            errors.append(args)
            return None

        with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror", side_effect=_err):
            app.generate_code()
        self.assertEqual(app.output_text.get("1.0", tk.END).strip(), "")
        self.assertTrue(any(SURFACE_OUTSIDE_STOCK_MESSAGE in str(item) for item in errors))

    def test_surface_below_stock_blocked(self):
        app = self.app
        _prepare_bgf_circle(app, raw_stock_top_z="0", surface_z="-65", blank_height="60")
        app.output_text.delete("1.0", tk.END)
        errors = []

        def _err(*args, **kwargs):
            errors.append(args)
            return None

        with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror", side_effect=_err):
            app.generate_code()
        self.assertEqual(app.output_text.get("1.0", tk.END).strip(), "")
        self.assertTrue(any(SURFACE_OUTSIDE_STOCK_MESSAGE in str(item) for item in errors))

    def test_coord_list_mixed_valid_then_outside_blocked(self):
        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        app.bgf_size_var.set("M16")
        app.load_bgf_values()
        depth = gen.BGF_DATA["M16"].thread_length
        _set(app, "raw_stock_top_z", "0")
        _set(app, "blank_height", "60")
        _set(app, "approach_clearance", "10")
        app.coord_rows = [
            BGFCoordinatePosition(0, 0, -10.0, depth),
            BGFCoordinatePosition(100, 0, -20.0, depth),
            BGFCoordinatePosition(200, 0, -30.0, depth),
        ]
        app.generate_bgf_code()
        code = app.output_text.get("1.0", tk.END)
        self.assertIn("BEGIN PGM", code)
        self.assertIn("L X+0.0000 Y+0.0000", code)
        self.assertIn("L X+200.0000 Y+0.0000", code)

        app.coord_rows.append(BGFCoordinatePosition(300, 0, 5.0, depth))
        app.output_text.delete("1.0", tk.END)
        errors = []

        def _err(*args, **kwargs):
            errors.append(args)
            return None

        with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror", side_effect=_err):
            app.generate_bgf_code()
        self.assertEqual(app.output_text.get("1.0", tk.END).strip(), "")
        self.assertTrue(any(SURFACE_OUTSIDE_STOCK_MESSAGE in str(item) for item in errors))

    def test_stale_after_raw_stock_top_z_change(self):
        app = self.app
        _prepare_bgf_circle(app)
        app.generate_code()
        output = app.output_text.get("1.0", tk.END)
        self.assertEqual(app.nc_guard.nc_state(app, output_text=output), NC_STATE_CURRENT)
        self.assertIn("raw_stock_top_z", collect_nc_input_payload(app)["entries"])
        before = fingerprint_nc_inputs(app)
        _set(app, "raw_stock_top_z", "5")
        app.refresh_nc_output_status()
        self.assertNotEqual(fingerprint_nc_inputs(app), before)
        self.assertEqual(
            app.nc_guard.nc_state(app, output_text=app.output_text.get("1.0", tk.END)),
            NC_STATE_STALE,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "stale.H")
            with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror"):
                with mock.patch("bsf_generator_verbessert_v3.filedialog.asksaveasfilename", return_value=path):
                    app.export_to_h()
            self.assertFalse(Path(path).exists())
            with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror"):
                with mock.patch.object(app.root, "clipboard_append") as clip:
                    app.copy_to_clipboard()
                    clip.assert_not_called()

    def test_decimal_comma_raw_stock_top_z(self):
        app = self.app
        _prepare_bgf_circle(app, raw_stock_top_z="20,5", surface_z="10", blank_height="60")
        common = app.validate_common()
        self.assertIsNotNone(common)
        self.assertAlmostEqual(common["raw_stock_top_z"], 20.5)
        app.generate_code()
        blk = _blk_lines(app.output_text.get("1.0", tk.END))
        self.assertIn("Z-39.5000", blk[0])
        self.assertIn("Z+20.5000", blk[1])

    def test_bsf_blk_form_uses_raw_stock_top_z(self):
        app = self.app
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.bsf_tool_profile_var.set("BSF-C-1000/050-10.5-23")
        app.on_bsf_tool_profile_change()
        _set(app, "blank_size", "1000")
        _set(app, "blank_height", "60")
        _set(app, "raw_stock_top_z", "0")
        _set(app, "bsf_reference_z", "0")
        # FAIL-CLOSED: Pflichtparameter setzen
        for k, v in [
            
            ("safe_z", "100"), ("end_safe_z", "200"),
            ("spindle_speed", "800"), ("feed_rate", "60"), ("dwell_time", "1.5"),
            ("single_x", "0"), ("single_y", "0"),
            ("entry_edge_z", "20"), ("exit_edge_z", "-5"), ("target_surface_z", "38"),
            ("x_safety_clearance", "2.000"), ("entry_clearance", "1.000"),
            ("full_cut_overlap_mm", "0.250"),
        ]:
            _set(app, k, v)
        app.generate_bsf_code()
        code_a = app.output_text.get("1.0", tk.END)
        blk_a = _blk_lines(code_a)
        self.assertIn("Z-60.0000", blk_a[0])
        self.assertIn("Z+0.0000", blk_a[1])
        motion_a = _machining_without_blk(code_a)

        _set(app, "raw_stock_top_z", "20")
        app.generate_bsf_code()
        code_b = app.output_text.get("1.0", tk.END)
        blk_b = _blk_lines(code_b)
        self.assertIn("Z-40.0000", blk_b[0])
        self.assertIn("Z+20.0000", blk_b[1])
        self.assertEqual(motion_a, _machining_without_blk(code_b))

        _set(app, "bsf_reference_z", "0")
        _set(app, "raw_stock_top_z", "-10")
        app.generate_bsf_code()
        blk_c = _blk_lines(app.output_text.get("1.0", tk.END))
        self.assertIn("Z-70.0000", blk_c[0])
        self.assertIn("Z-10.0000", blk_c[1])

    def test_legacy_bsf_json_defaults_raw_stock_top_z(self):
        doc = build_bsf_document(
            program_name="BSF_LEGACY",
            tool_number=8,
            blank_size=1000.0,
            blank_height=60.0,
                tool_profile_key=TOOL_C.key,
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
            raw_stock_top_z=12.5,
        )
        payload = document_to_dict(doc)
        self.assertEqual(payload["program"]["raw_stock_top_z"], 12.5)
        del payload["program"]["raw_stock_top_z"]
        loaded = parse_document_dict(payload)
        self.assertEqual(loaded.raw_stock_top_z, 0.0)
        self.assertIsNone(loaded.reference_z)

    def test_csv_does_not_store_or_change_raw_stock_top_z(self):
        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        _set(app, "raw_stock_top_z", "12.5")
        joined = "|".join(CSV_HEADER).lower()
        self.assertNotIn("raw_stock", joined)
        self.assertNotIn("rohteile", joined)
        rows = [BGFCoordinatePosition(10, 20, -10.0, 32.96)]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pos.csv")
            write_bgf_csv_file(path, rows)
            text = Path(path).read_text(encoding="utf-8")
        self.assertNotIn("raw_stock_top_z", text)
        imported = import_bgf_csv_text(text, default_thread_depth=32.96)
        self.assertEqual(len(imported), 1)
        self.assertEqual(app.entries["raw_stock_top_z"].get(), "12.5")

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as handle:
            handle.write(text)
            csv_path = handle.name
        try:
            with mock.patch("bsf_generator_verbessert_v3.filedialog.askopenfilename", return_value=csv_path):
                with mock.patch("bsf_generator_verbessert_v3.messagebox.showinfo"):
                    with mock.patch("bsf_generator_verbessert_v3.messagebox.askyesnocancel", return_value=True):
                        app.coord_import_csv()
        finally:
            os.unlink(csv_path)
        self.assertEqual(app.entries["raw_stock_top_z"].get(), "12.5")

    def test_teilkreis_and_xy_hardening_unchanged(self):
        app = self.app
        _prepare_bgf_circle(app, blank_size="715")
        app.generate_code()
        code = app.output_text.get("1.0", tk.END)
        blk = _blk_lines(code)
        self.assertIn("X-357.5000", blk[0])
        self.assertIn("Y-357.5000", blk[0])
        self.assertIn("X+357.5000", blk[1])
        self.assertIn("Y+357.5000", blk[1])
        self.assertIn("LBL 1 ; Schleifenanfang Teilkreis", code)
        self.assertIn("CC X+0.0000 Y+0.0000 ; Teilkreis-Mitte / Pol", code)
        self.assertIn("CALL LBL 100", code)


class TestStockZMathFinite(unittest.TestCase):
    def test_extents_keep_signed_height_without_abs(self):
        z_min, z_max = blk_form_z_extents(0.0, 60.0)
        self.assertEqual(z_max, 0.0)
        self.assertEqual(z_min, -60.0)
        self.assertTrue(math.isfinite(z_min) and math.isfinite(z_max))


if __name__ == "__main__":
    unittest.main()
