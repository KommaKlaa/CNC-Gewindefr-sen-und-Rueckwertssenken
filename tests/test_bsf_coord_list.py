from __future__ import annotations

import unittest

import bsf_generator_verbessert_v3 as gen
from coordinates import BSFCoordinatePosition
from heule_bsf_tools import BSF_TOOL_PROFILES
from ui import MODE_BSF

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]


class TestBsfCoordGui(unittest.TestCase):
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
        app.bsf_tool_profile_var.set(TOOL_C.designation)
        app.on_bsf_tool_profile_change()
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
        ):
            app.entries[key].delete(0, "end")
            app.entries[key].insert(0, val)
        app.bsf_coord_rows = [BSFCoordinatePosition(0, 0), BSFCoordinatePosition(100, 50)]
        app._refresh_bsf_coord_tree()

    def test_coordinate_program_contains_positions(self):
        self.app.position_mode_var.set("Koordinatenliste")
        self.app.on_position_mode_change(None)
        self.app.generate_bsf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("; --- KOORDINATENLISTE BSF ---", code)
        self.assertIn("; POSITION 1  X+0.0000 Y+0.0000", code)
        self.assertIn("; POSITION 2  X+100.0000 Y+50.0000", code)

    def test_single_position_sequence_still_available(self):
        self.app.position_mode_var.set("Einzelposition")
        self.app.on_position_mode_change(None)
        self.app.entries["single_x"].delete(0, "end")
        self.app.entries["single_x"].insert(0, "100")
        self.app.entries["single_y"].delete(0, "end")
        self.app.entries["single_y"].insert(0, "50")
        self.app.generate_bsf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("; --- EINZELPOSITION ---", code)
        self.assertIn("L X+100.0000 Y+50.0000 Z+100.0000 R0 FMAX", code)

    def test_circle_mode_uses_subprogram(self):
        self.app.position_mode_var.set("Teilkreis")
        self.app.on_position_mode_change(None)
        self.app.generate_bsf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("; --- TEILKREIS ---", code)
        self.assertIn("LBL 100 ; Unterprogramm BSF", code)

    def test_preview_is_nc_allowed_with_selected_tool(self):
        snap = self.app.build_bsf_preview_snapshot()
        self.assertTrue(snap.nc_allowed)
        self.assertEqual(snap.bsf_tool_designation, TOOL_C.designation)
        self.assertEqual(snap.bsf_measurement_face_to_edge_mm, 8.55)

    def test_csv_import_does_not_change_selected_tool(self):
        before = self.app.bsf_tool_profile_var.get()
        self.app.bsf_coord_rows = [BSFCoordinatePosition(10, 20)]
        self.app._refresh_bsf_coord_tree()
        self.assertEqual(self.app.bsf_tool_profile_var.get(), before)

    def test_csv_import_does_not_change_activation_speed(self):
        self.app.bsf_tool_profile_var.set("BSF-E-1350/050-16.5-14")
        self.app.on_bsf_tool_profile_change()
        self.app.bsf_coord_rows = [BSFCoordinatePosition(10, 20)]
        self.app._refresh_bsf_coord_tree()
        self.app.generate_bsf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("S1500 M3 ; Spindel einschalten", code)


if __name__ == "__main__":
    unittest.main()
