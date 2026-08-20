"""PHASE_BSF_LAYOUT_1 – Zwei-Spalten-Layout (nur UI-Sichtbarkeit/Struktur)."""

from __future__ import annotations

import unittest

import bsf_generator_verbessert_v3 as gen
from ui import MODE_BSF
from ui.visibility import is_mapped


class TestBsfLayout1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_two_column_mid_frame(self):
        app = self.app
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        self.assertTrue(hasattr(app, "bsf_mid_frame"))
        self.assertTrue(is_mapped(app.bsf_mid_frame))
        self.assertEqual(str(app.bsf_processing_frame.master), str(app.bsf_mid_frame))
        self.assertEqual(str(app.bsf_right_column.master), str(app.bsf_mid_frame))
        self.assertEqual(str(app.bsf_geometry_summary_frame.master), str(app.bsf_right_column))
        self.assertEqual(str(app.bsf_safe_box_frame.master), str(app.bsf_right_column))
        self.assertEqual(str(app.bsf_machine_frame.master), str(app.bsf_right_column))

    def test_grid_weights_present(self):
        app = self.app
        mid = app.bsf_mid_frame
        self.assertEqual(int(mid.grid_columnconfigure(0)["weight"]), 3)
        self.assertEqual(int(mid.grid_columnconfigure(1)["weight"]), 2)

    def test_nc_output_still_full_width_container(self):
        app = self.app
        self.assertTrue(app.output_text.winfo_exists())
        # Output liegt im Bottom-Pane, nicht im Mid-Frame
        self.assertIsNot(app.output_text.master, app.bsf_mid_frame)


if __name__ == "__main__":
    unittest.main()
