"""Regression: Herstellerdaten und bestehende Sequenzen unveraendert / Modi CIRCLE+SINGLE+COORD."""

from __future__ import annotations

import unittest

import bsf_generator_verbessert_v3 as gen
from coordinates import BGFCoordinatePosition
from coordinates.model import PositionMode


class TestBgfDataIntegrity(unittest.TestCase):
    def test_expected_keys(self):
        self.assertEqual(
            set(gen.BGF_DATA.keys()),
            {"M5", "M6", "M8", "M10", "M16", "M16x1.5"},
        )

    def test_m10_pass_geometry_unchanged(self):
        p0 = gen.BGF_DATA["M10"].passes[0]
        self.assertEqual(p0.y_start, 3.9790)
        self.assertEqual(p0.cc_entry_y, -4.3645)
        self.assertEqual(p0.iz_thread, -1.5000)
        self.assertEqual(p0.feed_thread, 292)

    def test_m5_radius_unchanged(self):
        self.assertEqual(gen.BGF_DATA["M5"].radius, 2.0060)
        self.assertEqual(len(gen.BGF_DATA["M5"].passes), 2)


class TestSequenceRegression(unittest.TestCase):
    def test_bgf_sequence_m10_snapshot(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        data = gen.BGF_DATA["M10"]
        seq = app.get_bgf_sequence(data, 8, surface_z=0.0)
        root.destroy()
        text = "\n".join(seq)
        self.assertIn("L Z-27.8700 F1348 M", text)
        self.assertIn("CP IPA-360 IZ-1.5000 DR- RR F292 M", text)
        self.assertIn("TOOL CALL 8 Z DR0", text)

    def test_bsf_sequence_core_steps_unchanged(self):
        import tkinter as tk
        from types import SimpleNamespace

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        z_values = {"z_sink_finish": 1.5, "z_clearance": -3.0}
        common = {"safe_z": 100.0}
        heule_pos = SimpleNamespace(
            a_measurement_face_z=1.0,
            x_measurement_face_z=-3.0,
            b_measurement_face_z=-1.0,
            c_measurement_face_z=0.5,
            d_measurement_face_z=1.5,
        )
        seq = app.get_bsf_sequence(z_values, heule_pos, 200.0, 0.5, "M7", "M9", common)
        root.destroy()
        self.assertEqual(seq[0], "L Z+1.0000 R0 FMAX ; A vor Bohrung")
        self.assertIn("CYCL DEF 9.0 VERWEILZEIT", seq)
        self.assertIn("L Z-3.0000 R0 FMAX M3 ; Spindel einschalten an X", seq)


class TestGuiModesRegression(unittest.TestCase):
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
        self.app.position_mode_var.set("Teilkreis")
        self.app.on_position_mode_change(None)
        self.app.coord_rows = []

    def test_position_mode_defaults_circle(self):
        self.assertEqual(self.app.get_position_mode(), PositionMode.CIRCLE)

    def test_bgf_circle_contains_loop(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.position_mode_var.set("Teilkreis")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set("M10")
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("; --- TEILKREIS ---", code)
        self.assertIn("FN 12: IF +Q2 LT +24 GOTO LBL 1", code)
        self.assertIn("CALL LBL 100", code)
        self.assertIn("TOOL CALL 8 Z DR0", code)

    def test_bsf_circle_contains_loop(self):
        self.app.mode_var.set("HEULE BSF")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Teilkreis")
        self.app.on_position_mode_change(None)
        self.app.bsf_tool_profile_var.set("BSF-C-1000/050-10.5-23")
        self.app.on_bsf_tool_profile_change()
        self.app.generate_bsf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("; --- TEILKREIS ---", code)
        self.assertIn("LBL 100 ; Unterprogramm BSF", code)
        self.assertIn("M5 ; Spindel aus", code)

    def test_single_xy_zero_matches_legacy_pattern(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Einzelposition")
        self.app.on_position_mode_change(None)
        self.app.entries["single_x"].configure(state="normal")
        self.app.entries["single_y"].configure(state="normal")
        self.app.entries["single_x"].delete(0, "end")
        self.app.entries["single_x"].insert(0, "0")
        self.app.entries["single_y"].delete(0, "end")
        self.app.entries["single_y"].insert(0, "0")
        self.app.bgf_size_var.set("M10")
        self.app.load_bgf_values()
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("; --- EINZELPOSITION ---", code)
        self.assertIn("L X+0.0000 Y+0.0000 Z+1.0000 R0 FMAX M13", code)
        self.assertNotIn("CALL LBL 100", code)

    def test_coordinate_list_inline_per_position_safe_z(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Koordinatenliste")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set("M5")
        self.app.load_bgf_values()
        tpl = gen.BGF_DATA["M5"].thread_length
        self.app.coord_rows = [
            BGFCoordinatePosition(100, 200, 0.0, tpl),
            BGFCoordinatePosition(150, 250, 0.0, tpl),
            BGFCoordinatePosition(200, 300, 0.0, tpl),
        ]
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("; --- KOORDINATENLISTE BGF ---", code)
        self.assertIn("L X+100.0000 Y+200.0000 R0 FMAX", code)
        self.assertIn("L X+150.0000 Y+250.0000 R0 FMAX", code)
        self.assertIn("L X+200.0000 Y+300.0000 R0 FMAX", code)
        self.assertIn("L Z+100.0000 R0 FMAX", code)
        self.assertNotIn("CALL LBL 100", code)
        # Pro Position einmal DR0 (kein gemeinsames LBL)
        self.assertEqual(code.count("TOOL CALL 8 Z DR0"), 3)
        i100 = code.index("L X+100.0000 Y+200.0000 R0 FMAX")
        i150 = code.index("L X+150.0000 Y+250.0000 R0 FMAX")
        i200 = code.index("L X+200.0000 Y+300.0000 R0 FMAX")
        self.assertLess(i100, i150)
        self.assertLess(i150, i200)


if __name__ == "__main__":
    unittest.main()
