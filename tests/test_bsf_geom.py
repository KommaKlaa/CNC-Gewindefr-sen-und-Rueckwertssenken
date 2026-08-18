from __future__ import annotations

import unittest

import bsf_generator_verbessert_v3 as gen
from bsf_blade import apply_workpiece_reference_z, calculate_workpiece_bsf_z, spindle_on_z
from heule_bsf_tools import (
    BSF_TOOL_PROFILES,
    TOOL_SELECTION_REQUIRED,
    cutting_edge_z_from_holder_z,
    programmed_holder_z_for_cutting_edge,
)
from ui import MODE_BSF

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]
TOOL_E = BSF_TOOL_PROFILES["BSF_E_1350_050_16_5_14"]


class TestToolProfiles(unittest.TestCase):
    def test_catalog_metadata(self):
        self.assertEqual(TOOL_C.designation, "BSF-C-1000/050-10.5-23")
        self.assertEqual(TOOL_C.holder_to_cutting_edge_mm, 8.55)
        self.assertEqual(TOOL_C.activation_speed_rpm, 2000)
        self.assertEqual(TOOL_E.designation, "BSF-E-1350/050-16.5-14")
        self.assertEqual(TOOL_E.holder_to_cutting_edge_mm, 11.40)
        self.assertEqual(TOOL_E.activation_speed_rpm, 1500)

    def test_holder_cutting_edge_invariant(self):
        for tool, target in ((TOOL_C, 38.0), (TOOL_E, 38.0), (TOOL_C, 58.0), (TOOL_E, 18.0)):
            holder = programmed_holder_z_for_cutting_edge(target, tool)
            self.assertAlmostEqual(cutting_edge_z_from_holder_z(holder, tool), target, places=4)


class TestGuiBsfToolarch(unittest.TestCase):
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
        app = self.app
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        for key, val in (
            ("bund_thickness", "18"),
            ("sink_depth", "38"),
            ("clearance", "23"),
            ("dwell_time", "1.5"),
            ("spindle_speed", "800"),
            ("feed_rate", "60"),
            ("safe_z", "100"),
            ("end_safe_z", "200"),
            ("bsf_reference_z", "0"),
            ("single_x", "0"),
            ("single_y", "0"),
        ):
            app.entries[key].delete(0, "end")
            app.entries[key].insert(0, val)
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)

    def test_fail_closed_without_tool(self):
        import tkinter.messagebox as mb

        self.app.bsf_tool_profile_var.set(TOOL_SELECTION_REQUIRED)
        self.app.on_bsf_tool_profile_change()
        self.app.output_text.delete("1.0", "end")
        orig = mb.showerror
        mb.showerror = lambda *a, **k: None
        try:
            self.app.generate_bsf_code()
        finally:
            mb.showerror = orig
        self.assertEqual(self.app.output_text.get("1.0", "end").strip(), "")

    def test_header_uses_tool_profile(self):
        self.app.bsf_tool_profile_var.set(TOOL_C.designation)
        self.app.on_bsf_tool_profile_change()
        self.app.generate_bsf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("; WERKZEUG: BSF-C-1000/050-10.5-23", code)
        self.assertIn("; VERMESSUNG: HALTER", code)
        self.assertIn("; HALTER -> SCHNEIDE: 8.550 MM", code)
        self.assertIn("; HEULE AKTIVIERUNGSDREHZAHL: 2000 U/MIN", code)
        self.assertNotIn("SCHWERTDICKE", code)

    def test_reference_z_and_tool_c_generate_holder_z(self):
        self.app.bsf_tool_profile_var.set(TOOL_C.designation)
        self.app.on_bsf_tool_profile_change()
        self.app.entries["bsf_reference_z"].delete(0, "end")
        self.app.entries["bsf_reference_z"].insert(0, "20")
        self.app.generate_bsf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("L Z+49.4500 R0 F30 ; Senken mit 50 Prozent Vorschub", code)
        self.assertIn("L Z+21.0000 R0 FMAX S2000 M3 ; Spindel einschalten", code)
        self.assertIn("TOOL CALL 8 Z S800", code)

    def test_reference_z_and_tool_e_generate_holder_z(self):
        self.app.bsf_tool_profile_var.set(TOOL_E.designation)
        self.app.on_bsf_tool_profile_change()
        self.app.generate_bsf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("L Z+26.6000 R0 F30 ; Senken mit 50 Prozent Vorschub", code)
        self.assertIn("L Z+1.0000 R0 FMAX S1500 M3 ; Spindel einschalten", code)
        self.assertIn("; HEULE AKTIVIERUNGSDREHZAHL: 1500 U/MIN", code)
        self.assertIn("L Z+100.0000 R0 FMAX ; Aus der Bohrung", code)

    def test_tool_switch_changes_activation_speed(self):
        self.app.bsf_tool_profile_var.set(TOOL_C.designation)
        self.app.on_bsf_tool_profile_change()
        self.app.generate_bsf_code()
        code_c = self.app.output_text.get("1.0", "end")
        self.app.bsf_tool_profile_var.set(TOOL_E.designation)
        self.app.on_bsf_tool_profile_change()
        self.app.generate_bsf_code()
        code_e = self.app.output_text.get("1.0", "end")
        self.assertIn("S2000 M3 ; Spindel einschalten", code_c)
        self.assertIn("S1500 M3 ; Spindel einschalten", code_e)
        self.assertNotIn("S1500 M3 ; Spindel einschalten", code_c)
        self.assertNotIn("S2000 M3 ; Spindel einschalten", code_e)

    def test_m_functions_unchanged(self):
        self.app.bsf_tool_profile_var.set(TOOL_C.designation)
        self.app.on_bsf_tool_profile_change()
        self.app.generate_bsf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("M5 ; Spindel aus", code)
        self.assertIn("M7 ; Messer unten aktivieren", code)
        self.assertIn("M9 ; Messer schliessen", code)

    def test_spindle_on_z_remains_reference_relative(self):
        self.assertEqual(spindle_on_z(0.0), 1.0)
        self.assertEqual(spindle_on_z(20.0), 21.0)

    def test_workpiece_relative_geometry_unchanged(self):
        wp = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=True)
        shifted = apply_workpiece_reference_z(wp, 20.0)
        self.assertEqual(wp["z_sink_finish"], 38.0)
        self.assertEqual(shifted["z_sink_finish"], 58.0)


if __name__ == "__main__":
    unittest.main()
