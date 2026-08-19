"""BGF.BLKFORM.1 – GUI-to-Export Rohteilgeometrie End-to-End.

Kein Formelwechsel: nur nachweisen, welchen Wert generate/export tatsaechlich nutzen.
"""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tkinter as tk
from tkinter import ttk

import bsf_generator_verbessert_v3 as gen
from ui import MODE_BGF, MODE_BSF


def _set(app, key: str, value) -> None:
    app.entries[key].delete(0, tk.END)
    app.entries[key].insert(0, str(value))


def _blk_lines(code: str) -> list[str]:
    return [ln.rstrip() for ln in code.splitlines() if ln.startswith("BLK FORM")]


def _prepare_user_repro(app) -> None:
    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    app.position_mode_var.set("Teilkreis")
    app.on_position_mode_change(None)
    app.bgf_size_var.set("M16")
    app.load_bgf_values()
    _set(app, "diameter", "580")
    _set(app, "count", "8")
    _set(app, "start_angle", "0")
    _set(app, "center_x", "0")
    _set(app, "center_y", "0")
    _set(app, "circle_surface_z", "0")
    _set(app, "bgf_thread_depth", "22")
    _set(app, "bgf_core_hole_depth", "25")
    _set(app, "approach_clearance", "10")
    _set(app, "blank_size", "1500")
    _set(app, "blank_height", "60")
    _set(app, "raw_stock_top_z", "0.000")
    _set(app, "program_name", "LPR_5_AUF_M16")


class TestBlkFormGuiToExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_single_entry_binding_no_parallel_var(self):
        app = self.app
        self.assertIn("blank_size", app.entries)
        self.assertIsInstance(app.entries["blank_size"], ttk.Entry)
        self.assertFalse(hasattr(app, "blank_size_var"))
        self.assertFalse(hasattr(app, "raw_stock_size_var"))
        self.assertFalse(hasattr(app, "stock_edge_var"))
        self.assertEqual(app.entries["blank_size"].get() != "", True)

    def test_default_blank_size_is_1000(self):
        root = tk.Tk()
        root.withdraw()
        try:
            fresh = gen.BSFGeneratorGUI(root)
            self.assertEqual(fresh.entries["blank_size"].get(), "1000")
            self.assertEqual(fresh.entries["blank_height"].get(), "60")
            self.assertEqual(float(fresh.entries["raw_stock_top_z"].get().replace(",", ".")), 0.0)
        finally:
            root.destroy()

    def test_generate_reads_live_gui_not_cached_default(self):
        app = self.app
        _prepare_user_repro(app)
        self.assertEqual(app.entries["blank_size"].get(), "1500")
        common = app.validate_common()
        self.assertIsNotNone(common)
        self.assertEqual(common["blank_size"], 1500.0)
        self.assertEqual(common["blank_height"], 60.0)
        app.generate_code()
        code = app.output_text.get("1.0", tk.END)
        blk = _blk_lines(code)
        self.assertEqual(len(blk), 2)
        self.assertIn("X-750.0000", blk[0])
        self.assertIn("Y-750.0000", blk[0])
        self.assertIn("X+750.0000", blk[1])
        self.assertIn("Y+750.0000", blk[1])
        self.assertNotIn("X-500", code.split("TOOL CALL")[0])
        self.assertNotIn("X+500.0000", blk[1])

    def test_user_repro_z_uses_raw_stock_top_not_surface(self):
        app = self.app
        _prepare_user_repro(app)
        app.generate_code()
        blk = _blk_lines(app.output_text.get("1.0", tk.END))
        self.assertIn("Z-60.0000", blk[0])
        self.assertIn("Z+0.0000", blk[1])
        self.assertNotIn("Z-30.0000", blk[0])
        self.assertNotIn("Z+30.0000", blk[1])

    def test_blank_size_matrix(self):
        app = self.app
        _prepare_user_repro(app)
        cases = {
            "1000": 1000.0,
            "1500": 1500.0,
            "580": 580.0,
            "715": 715.0,
            "1500.5": 1500.5,
            "1500,5": 1500.5,
        }
        for size, width in cases.items():
            with self.subTest(blank_size=size):
                _set(app, "blank_size", size)
                half = width / 2.0
                self.assertEqual(app.validate_common()["blank_size"], width)
                app.generate_code()
                blk = _blk_lines(app.output_text.get("1.0", tk.END))
                self.assertEqual(
                    blk[0],
                    f"BLK FORM 0.1 Z {gen.fmt_axis('X', -half)} {gen.fmt_axis('Y', -half)} "
                    f"{gen.fmt_axis('Z', -60.0)}",
                )
                self.assertEqual(
                    blk[1],
                    f"BLK FORM 0.2 {gen.fmt_axis('X', half)} {gen.fmt_axis('Y', half)} "
                    f"{gen.fmt_axis('Z', 0.0)}",
                )
                self.assertAlmostEqual(2.0 * half, width)

    def test_comma_decimal_keeps_exact_half(self):
        app = self.app
        _prepare_user_repro(app)
        _set(app, "blank_size", "1500,5")
        common = app.validate_common()
        self.assertEqual(common["blank_size"], 1500.5)
        app.generate_code()
        blk = "\n".join(_blk_lines(app.output_text.get("1.0", tk.END)))
        self.assertIn("X-750.2500", blk)
        self.assertIn("Y-750.2500", blk)
        self.assertIn("X+750.2500", blk)
        self.assertIn("Y+750.2500", blk)

    def test_export_writes_visible_nc_without_regeneration(self):
        app = self.app
        _prepare_user_repro(app)
        app.generate_code()
        visible = app.output_text.get("1.0", tk.END).strip()
        self.assertIn("X-750", visible)
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "LPR_5_AUF_M16.H")
            with mock.patch("bsf_generator_verbessert_v3.filedialog.asksaveasfilename", return_value=path):
                with mock.patch("bsf_generator_verbessert_v3.messagebox.showinfo"):
                    app.export_to_h()
            exported = Path(path).read_text(encoding="cp1252").strip()
        self.assertEqual(exported, visible)
        exp_blk = _blk_lines(exported)
        vis_blk = _blk_lines(visible)
        self.assertEqual(exp_blk, vis_blk)

    def test_export_blocked_if_gui_changed_without_regenerate(self):
        app = self.app
        _prepare_user_repro(app)
        app.generate_code()
        visible_blk = _blk_lines(app.output_text.get("1.0", tk.END))
        self.assertIn("X-750.0000", visible_blk[0])
        _set(app, "blank_size", "1000")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "after_gui_change.H")
            with mock.patch("bsf_generator_verbessert_v3.filedialog.asksaveasfilename", return_value=path):
                with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror"):
                    with mock.patch("bsf_generator_verbessert_v3.messagebox.showinfo"):
                        app.export_to_h()
            self.assertFalse(Path(path).exists())
        self.assertEqual(_blk_lines(app.output_text.get("1.0", tk.END)), visible_blk)

    def test_clipboard_matches_visible_nc(self):
        app = self.app
        _prepare_user_repro(app)
        app.generate_code()
        visible = app.output_text.get("1.0", tk.END).strip()
        with mock.patch("bsf_generator_verbessert_v3.messagebox.showinfo"):
            app.copy_to_clipboard()
        clip = app.root.clipboard_get().strip()
        self.assertEqual(clip, visible)
        self.assertEqual(_blk_lines(clip), _blk_lines(visible))

    def test_bsf_uses_same_blank_size_entry(self):
        app = self.app
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.bsf_tool_profile_var.set("BSF-C-1000/050-10.5-23")
        app.on_bsf_tool_profile_change()
        _set(app, "blank_size", "1500")
        _set(app, "blank_height", "60")
        # FAIL-CLOSED: Pflichtparameter ref=0, sink=38 -> target=38; dep=-5 OK
        for k, v in [
            ("bund_thickness", "18"), ("sink_depth", "38"), ("clearance", "23"),
            ("bsf_reference_z", "0"), ("safe_z", "100"), ("end_safe_z", "200"),
            ("spindle_speed", "800"), ("feed_rate", "60"), ("dwell_time", "1.5"),
            ("single_x", "0"), ("single_y", "0"),
            ("deployment_edge_z", "-5"), ("entry_edge_z", "20"),
            ("x_safety_clearance", "2.000"), ("entry_clearance", "1.000"),
            ("full_cut_overlap_mm", "0.250"),
        ]:
            _set(app, k, v)
        app.generate_bsf_code()
        blk = _blk_lines(app.output_text.get("1.0", tk.END))
        self.assertIn("X-750.0000", blk[0])
        self.assertIn("Y-750.0000", blk[0])
        self.assertIn("X+750.0000", blk[1])
        self.assertIn("Y+750.0000", blk[1])

    def test_teilkreis_hotfix_still_present(self):
        app = self.app
        _prepare_user_repro(app)
        app.generate_code()
        code = app.output_text.get("1.0", tk.END)
        self.assertIn("LBL 1 ; Schleifenanfang Teilkreis", code)
        self.assertIn("CC X+0.0000 Y+0.0000 ; Teilkreis-Mitte / Pol", code)
        self.assertIn("LP PR+290.0000 PA+Q1 R0 FMAX ; Teilkreisposition", code)
        self.assertIn("CALL LBL 100", code)
        header = code.split("LBL 1 ;")[0]
        self.assertNotIn("CC X+0.0000 Y+0.0000", header)

    def test_invalid_blank_size_blocked(self):
        app = self.app
        _prepare_user_repro(app)
        with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror"):
            for bad in ("abc", "", "0", "-1000", "nan", "NaN", "inf", "+inf", "-inf"):
                with self.subTest(bad=bad):
                    _set(app, "blank_size", bad)
                    self.assertIsNone(app.validate_common())

    def test_invalid_blank_height_blocked(self):
        app = self.app
        _prepare_user_repro(app)
        with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror"):
            for bad in ("abc", "", "0", "-60", "nan", "inf", "-inf"):
                with self.subTest(bad=bad):
                    _set(app, "blank_height", bad)
                    self.assertIsNone(app.validate_common())

    def test_raw_stock_top_z_finite_allows_signed_values(self):
        app = self.app
        _prepare_user_repro(app)
        for good in ("0", "0.000", "+20", "-10", "20,5", "-10,25"):
            with self.subTest(good=good):
                _set(app, "raw_stock_top_z", good)
                common = app.validate_common()
                self.assertIsNotNone(common)
                self.assertTrue(math.isfinite(common["raw_stock_top_z"]))

    def test_invalid_raw_stock_top_z_blocked(self):
        app = self.app
        _prepare_user_repro(app)
        with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror"):
            for bad in ("abc", "", "nan", "NaN", "inf", "+inf", "-inf"):
                with self.subTest(bad=bad):
                    _set(app, "raw_stock_top_z", bad)
                    self.assertIsNone(app.validate_common())


if __name__ == "__main__":
    unittest.main()
