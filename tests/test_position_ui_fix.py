"""UI-Fix Tests: Positions-Combobox muss Einzelposition anbieten und anschliessen."""

from __future__ import annotations

import unittest

import bsf_generator_verbessert_v3 as gen
from coordinates.model import PositionMode


class TestPositionComboUiFix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_combo_contains_all_position_modes(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        values = tuple(self.app.position_mode_combo.cget("values"))
        self.assertEqual(values, ("Teilkreis", "Einzelposition", "Koordinatenliste"))
        self.assertIn("Koordinatenliste", values)

    def test_einzelposition_shows_xyz_fields(self):
        self.app.position_mode_var.set("Einzelposition")
        self.app.on_position_mode_change(None)
        self.assertEqual(self.app.get_position_mode(), PositionMode.SINGLE)
        self.assertEqual(self.app.single_pos_frame.winfo_manager(), "grid")
        for key in ("single_x", "single_y", "single_surface_z"):
            self.assertEqual(str(self.app.entries[key].cget("state")), "normal")

    def test_teilkreis_hides_xyz_fields(self):
        self.app.position_mode_var.set("Einzelposition")
        self.app.on_position_mode_change(None)
        self.app.position_mode_var.set("Teilkreis")
        self.app.on_position_mode_change(None)
        self.assertEqual(self.app.get_position_mode(), PositionMode.CIRCLE)
        self.assertEqual(self.app.single_pos_frame.winfo_manager(), "")

    def test_xyz_connected_m10_surface_35(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Einzelposition")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set("M10")
        self.app.load_bgf_values()
        for key, val in (("single_x", "100"), ("single_y", "50"), ("single_surface_z", "35")):
            self.app.entries[key].delete(0, "end")
            self.app.entries[key].insert(0, val)
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("L X+100.0000 Y+50.0000 Z+36.0000 R0 FMAX M13", code)
        self.assertIn("L Z+7.1300 F1348 M", code)
        self.assertIn("L Z+10.1010 R0 FMAX M", code)
        self.assertIn("L Z+35.0000 FMAX M", code)
        self.assertIn("CP IPA-360 IZ-1.5000 DR- RR F292 M", code)

    def test_surface_zero_regression_via_gui(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Einzelposition")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set("M10")
        for key, val in (("single_x", "0"), ("single_y", "0"), ("single_surface_z", "0")):
            self.app.entries[key].delete(0, "end")
            self.app.entries[key].insert(0, val)
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("L X+0.0000 Y+0.0000 Z+1.0000 R0 FMAX M13", code)
        self.assertIn("L Z-27.8700 F1348 M", code)
        self.assertIn("L Z-24.8990 R0 FMAX M", code)

    def test_teilkreis_regression_m10(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Teilkreis")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set("M10")
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("; --- TEILKREIS ---", code)
        self.assertIn("FN 12: IF +Q2 LT +24 GOTO LBL 1", code)
        self.assertIn("LP PR+357.5000 PA+Q1 R0 FMAX", code)


if __name__ == "__main__":
    unittest.main()
