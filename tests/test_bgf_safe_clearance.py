"""PHASE BGF.SAFE.1 – approach_clearance / Sicherheitsabstand ueber Oberflaeche."""

from __future__ import annotations

import math
import re
import unittest

import bsf_generator_verbessert_v3 as gen
from bgf_surface import above_surface, validate_approach_clearance
from coordinates import BGFCoordinatePosition, validate_bgf_coordinate_list
from coordinates.bgf_list_validation import validate_safe_z_against_surfaces


def _m10_policy():
    data = gen.BGF_DATA["M10"]
    return gen.policy_from_tool(
        data.size,
        data.thread_length,
        data.drill_depth,
        data.mill_start_depth,
        article_no=data.article_no,
        approved_max_thread_depth=gen.approved_max_thread_depth(data.size, data.article_no),
        axial_increment=gen.axial_increment_from_passes(data.passes),
        variable_depth_rule_validated=False,
    )


class TestApproachHelper(unittest.TestCase):
    def test_clearance_examples(self):
        self.assertEqual(above_surface(0.0, 1.0), 1.0)
        self.assertEqual(above_surface(0.0, 5.0), 5.0)
        self.assertEqual(above_surface(35.0, 5.0), 40.0)
        self.assertEqual(above_surface(-10.0, 2.0), -8.0)


class TestClearanceValidation(unittest.TestCase):
    def test_pass_values(self):
        self.assertIsNone(validate_approach_clearance(1.0))
        self.assertIsNone(validate_approach_clearance(0.1))
        self.assertIsNone(validate_approach_clearance(5.0))

    def test_block_values(self):
        self.assertIsNotNone(validate_approach_clearance(0.0))
        self.assertIsNotNone(validate_approach_clearance(-1.0))
        self.assertIsNotNone(validate_approach_clearance(float("nan")))
        self.assertIsNotNone(validate_approach_clearance(float("inf")))


class TestM10ClearanceNc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)
        cls.data = gen.BGF_DATA["M10"]

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_z0_clearance_1_regression(self):
        seq = self.app.get_bgf_sequence(self.data, 8, surface_z=0.0, approach_clearance=1.0)
        text = "\n".join(seq)
        self.assertIn("L Z-27.8700 F1348 M", text)
        self.assertIn("L Z-24.8990 R0 FMAX M", text)
        self.assertIn("L Z+0.0000 FMAX M", text)
        self.assertIn("L Z+1.0000 R0 FMAX M", text)

    def test_z0_clearance_5(self):
        seq = self.app.get_bgf_sequence(self.data, 8, surface_z=0.0, approach_clearance=5.0)
        text = "\n".join(seq)
        self.assertIn("L Z-27.8700 F1348 M", text)
        self.assertIn("L Z-24.8990 R0 FMAX M", text)
        self.assertIn("L Z+0.0000 FMAX M", text)
        self.assertIn("L Z+5.0000 R0 FMAX M", text)
        self.assertNotIn("L Z+1.0000 R0 FMAX M", text)

    def test_z35_clearance_5(self):
        seq = self.app.get_bgf_sequence(self.data, 8, surface_z=35.0, approach_clearance=5.0)
        text = "\n".join(seq)
        self.assertIn("L Z+7.1300 F1348 M", text)
        self.assertIn("L Z+10.1010 R0 FMAX M", text)
        self.assertIn("L Z+35.0000 FMAX M", text)
        self.assertIn("L Z+40.0000 R0 FMAX M", text)

    def test_incremental_path_unchanged(self):
        seq1 = "\n".join(self.app.get_bgf_sequence(self.data, 8, 0.0, 1.0))
        seq5 = "\n".join(self.app.get_bgf_sequence(self.data, 8, 0.0, 5.0))
        incr = re.compile(r"\b(CC|CP|IPA|IX|IY|IZ|DR-|RR|F\d+)\b")
        self.assertEqual(incr.findall(seq1), incr.findall(seq5))

    def test_gui_single_clearance_5_surface_35(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Einzelposition")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set("M10")
        self.app.load_bgf_values()
        self.app.entries["approach_clearance"].delete(0, "end")
        self.app.entries["approach_clearance"].insert(0, "5")
        for key, val in (("single_x", "100"), ("single_y", "50"), ("single_surface_z", "35")):
            self.app.entries[key].delete(0, "end")
            self.app.entries[key].insert(0, val)
        self.app.entries["raw_stock_top_z"].delete(0, "end")
        self.app.entries["raw_stock_top_z"].insert(0, "35")
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("L X+100.0000 Y+50.0000 Z+40.0000 R0 FMAX M13", code)
        self.assertIn("L Z+7.1300 F1348 M", code)
        self.assertIn("L Z+40.0000 R0 FMAX M", code)


class TestCoordinateListClearanceGate(unittest.TestCase):
    def test_pass_with_clearance_5(self):
        positions = [
            BGFCoordinatePosition(0, 0, 0, 25.06),
            BGFCoordinatePosition(100, 50, 35, 25.06),
            BGFCoordinatePosition(200, 0, 90, 25.06),
        ]
        result = validate_bgf_coordinate_list(
            positions,
            _m10_policy(),
            safe_z=100,
            end_safe_z=200,
            approach_clearance=5.0,
        )
        self.assertTrue(result.ok_for_nc)
        self.assertEqual(errs := validate_safe_z_against_surfaces(
            100, 200, positions, approach_clearance=5.0
        ), [])
        del errs

    def test_block_surface_98_clearance_5(self):
        positions = [
            BGFCoordinatePosition(0, 0, 0, 25.06),
            BGFCoordinatePosition(100, 50, 35, 25.06),
            BGFCoordinatePosition(200, 0, 98, 25.06),
        ]
        result = validate_bgf_coordinate_list(
            positions,
            _m10_policy(),
            safe_z=100,
            end_safe_z=200,
            approach_clearance=5.0,
        )
        self.assertFalse(result.ok_for_nc)
        joined = "\n".join(result.errors)
        self.assertIn("Position 3", joined)
        self.assertIn("103.000", joined)
        self.assertIn("100.000", joined)

    def test_safe_equal_approach_allowed(self):
        # surface=100, clearance=5 → approach=105; safe_z=105 erlaubt
        positions = [BGFCoordinatePosition(0, 0, 100, 25.06)]
        errs = validate_safe_z_against_surfaces(
            105, 200, positions, approach_clearance=5.0
        )
        self.assertEqual(errs, [])
        errs = validate_safe_z_against_surfaces(
            104, 200, positions, approach_clearance=5.0
        )
        self.assertTrue(errs)

    def test_variable_depth_allowed_with_large_clearance(self):
        positions = [BGFCoordinatePosition(0, 0, 0, 20.0)]
        result = validate_bgf_coordinate_list(
            positions,
            _m10_policy(),
            safe_z=100,
            end_safe_z=200,
            approach_clearance=10.0,
        )
        self.assertTrue(result.ok_for_nc)


class TestGuiClearanceField(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_field_default_and_comma(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.assertIn("approach_clearance", self.app.entries)
        self.assertEqual(self.app.entries["approach_clearance"].get(), "1.000")
        self.app.entries["approach_clearance"].delete(0, "end")
        self.app.entries["approach_clearance"].insert(0, "1,5")
        val = self.app.get_approach_clearance()
        self.assertEqual(val, 1.5)

    def test_invalid_clearance_blocks(self):
        self.app.entries["approach_clearance"].delete(0, "end")
        self.app.entries["approach_clearance"].insert(0, "0")
        blocked = {"n": 0}
        original = gen.messagebox.showerror

        def fake(*a, **k):
            blocked["n"] += 1

        gen.messagebox.showerror = fake
        try:
            self.assertIsNone(self.app.get_approach_clearance())
        finally:
            gen.messagebox.showerror = original
        self.assertGreaterEqual(blocked["n"], 1)


if __name__ == "__main__":
    unittest.main()
