"""PHASE UI.1 – Sichtbarkeit Bearbeitung/Positionierung, State-Erhalt, NC-Regression."""

from __future__ import annotations

import unittest

import bsf_generator_verbessert_v3 as gen
from coordinates.model import PositionMode
from ui import MODE_BGF, MODE_BSF, POSITION_LABELS_BGF, POSITION_LABELS_BSF
from ui.visibility import is_mapped


class TestUi1Visibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_bgf_hides_bsf_fields(self):
        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        self.assertTrue(is_mapped(app.bgf_tool_frame))
        self.assertTrue(is_mapped(app.bgf_processing_frame))
        self.assertTrue(is_mapped(app.position_frame))
        self.assertTrue(is_mapped(app.common_frame))
        self.assertFalse(is_mapped(app.bsf_tool_frame))
        self.assertFalse(is_mapped(app.bsf_processing_frame))
        self.assertFalse(is_mapped(app.bsf_machine_frame))
        # BSF-spezifische Entries existieren, liegen aber in ausgeblendeten Frames
        self.assertIn("bund_thickness", app.entries)
        self.assertFalse(is_mapped(app.bsf_processing_frame))

    def test_bsf_hides_bgf_fields(self):
        app = self.app
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        self.assertTrue(is_mapped(app.bsf_tool_frame))
        self.assertTrue(is_mapped(app.bsf_processing_frame))
        self.assertTrue(is_mapped(app.bsf_machine_frame))
        self.assertTrue(is_mapped(app.position_frame))
        self.assertFalse(is_mapped(app.bgf_tool_frame))
        self.assertFalse(is_mapped(app.bgf_processing_frame))
        values = tuple(app.position_mode_combo.cget("values"))
        self.assertEqual(values, POSITION_LABELS_BSF)
        self.assertIn("Koordinatenliste", values)

    def test_circle_panel_only(self):
        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.position_mode_var.set("Teilkreis")
        app.on_position_mode_change(None)
        self.assertTrue(is_mapped(app.circle_frame))
        self.assertFalse(is_mapped(app.single_pos_frame))
        self.assertFalse(is_mapped(app.coord_list_frame))

    def test_single_panel_bgf(self):
        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        self.assertTrue(is_mapped(app.single_pos_frame))
        self.assertFalse(is_mapped(app.circle_frame))
        self.assertFalse(is_mapped(app.coord_list_frame))
        self.assertEqual(str(app.entries["single_surface_z"].winfo_manager()), "grid")

    def test_single_panel_bsf_no_surface_z(self):
        app = self.app
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        self.assertTrue(is_mapped(app.single_pos_frame))
        self.assertEqual(str(app.entries["single_surface_z"].winfo_manager()), "")

    def test_coordinate_list_panel(self):
        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        self.assertEqual(tuple(app.position_mode_combo.cget("values")), POSITION_LABELS_BGF)
        self.assertTrue(is_mapped(app.coord_list_frame))
        self.assertFalse(is_mapped(app.circle_frame))
        self.assertFalse(is_mapped(app.single_pos_frame))

    def test_coordinate_list_panel_bsf(self):
        app = self.app
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        self.assertEqual(tuple(app.position_mode_combo.cget("values")), POSITION_LABELS_BSF)
        self.assertTrue(is_mapped(app.coord_list_frame))
        self.assertTrue(is_mapped(app.bsf_coord_inner))
        self.assertFalse(is_mapped(app.bgf_coord_inner))
        self.assertFalse(is_mapped(app.circle_frame))
        self.assertFalse(is_mapped(app.single_pos_frame))


class TestUi1StatePreservation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_bgf_values_survive_bsf_roundtrip(self):
        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.bgf_size_var.set("M10")
        app.load_bgf_values()
        app.entries["bgf_thread_depth"].delete(0, "end")
        app.entries["bgf_thread_depth"].insert(0, "20")
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.entries["single_surface_z"].delete(0, "end")
        app.entries["single_surface_z"].insert(0, "35")

        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)

        self.assertEqual(app.bgf_size_var.get(), "M10")
        self.assertEqual(app.entries["bgf_thread_depth"].get(), "20")
        self.assertEqual(app.entries["single_surface_z"].get(), "35")

    def test_circle_values_survive_position_switch(self):
        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.position_mode_var.set("Teilkreis")
        app.on_position_mode_change(None)
        for key, val in (("diameter", "715"), ("count", "24"), ("start_angle", "15")):
            app.entries[key].delete(0, "end")
            app.entries[key].insert(0, val)

        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.position_mode_var.set("Teilkreis")
        app.on_position_mode_change(None)

        self.assertEqual(app.entries["diameter"].get(), "715")
        self.assertEqual(app.entries["count"].get(), "24")
        self.assertEqual(app.entries["start_angle"].get(), "15")


class TestUi1NcRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_bgf_m10_single_depth20_clearance5(self):
        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.bgf_size_var.set("M10")
        app.load_bgf_values()
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.entries["bgf_thread_depth"].delete(0, "end")
        app.entries["bgf_thread_depth"].insert(0, "20")
        app.entries["approach_clearance"].delete(0, "end")
        app.entries["approach_clearance"].insert(0, "5")
        for k, v in (("single_x", "0"), ("single_y", "0"), ("single_surface_z", "0")):
            app.entries[k].delete(0, "end")
            app.entries[k].insert(0, v)
        app.generate_bgf_code()
        code = app.output_text.get("1.0", "end")
        self.assertIn("L Z-22.8100 F1348 M", code)
        self.assertIn("L Z-19.8390 R0 FMAX M", code)
        self.assertIn("Z+5.0000", code)
        self.assertIn("CP IPA-360 IZ-1.5000 DR- RR F292 M", code)

    def test_bgf_circle_unchanged(self):
        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.position_mode_var.set("Teilkreis")
        app.on_position_mode_change(None)
        app.bgf_size_var.set("M10")
        app.load_bgf_values()
        app.generate_bgf_code()
        code = app.output_text.get("1.0", "end")
        self.assertIn("; --- TEILKREIS ---", code)
        self.assertIn("FN 12: IF +Q2 LT +24 GOTO LBL 1", code)
        self.assertIn("LP PR+357.5000 PA+Q1 R0 FMAX", code)

    def test_bsf_circle_unchanged(self):
        app = self.app
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.position_mode_var.set("Teilkreis")
        app.on_position_mode_change(None)
        app.bsf_tool_profile_var.set("BSF-C-1000/050-10.5-23")
        app.on_bsf_tool_profile_change()
        app.generate_bsf_code()
        code = app.output_text.get("1.0", "end")
        self.assertIn("; --- TEILKREIS ---", code)
        self.assertIn("LBL 100 ; Unterprogramm BSF", code)
        self.assertIn("M5 ; Spindel aus", code)

    def test_1080x900_layout_has_output(self):
        app = self.app
        self.assertEqual(app.root.winfo_reqwidth() >= 0, True)
        self.assertTrue(hasattr(app, "paned"))
        self.assertTrue(hasattr(app, "params_scroll"))
        self.assertTrue(app.output_text.winfo_exists())
        app.root.geometry("1080x900")
        app.root.update_idletasks()
        self.assertGreater(app.output_text.winfo_height(), 0)


class TestUi1PositionCombo(unittest.TestCase):
    def test_bgf_combo_has_three_modes(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        self.assertEqual(tuple(app.position_mode_combo.cget("values")), POSITION_LABELS_BGF)
        self.assertEqual(app.get_position_mode(), PositionMode.CIRCLE)
        root.destroy()


if __name__ == "__main__":
    unittest.main()
