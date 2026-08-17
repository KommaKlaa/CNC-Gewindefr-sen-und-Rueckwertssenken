"""Tests fuer PHASE BGF.ZPOS.1 – surface_z Offset bei fester Hersteller-Tiefe."""

from __future__ import annotations

import unittest

import bsf_generator_verbessert_v3 as gen
from bgf_surface import absolute_from_surface, above_surface, at_surface


def _incremental_lines(lines):
    keys = ("CC ", "CP ", " IX", " IY", " IZ", "IPA", "DR-", " RR")
    out = []
    for line in lines:
        if any(k in line for k in ("CC ", "CP ", "IX+", "IX-", "IY+", "IY-")):
            out.append(line)
        elif "DR-" in line or " RR " in line:
            out.append(line)
    return out


class TestBgfSurfaceHelpers(unittest.TestCase):
    def test_absolute_from_surface(self):
        self.assertAlmostEqual(absolute_from_surface(0.0, 27.87), -27.87)
        self.assertAlmostEqual(absolute_from_surface(35.0, 27.87), 7.13)
        self.assertAlmostEqual(absolute_from_surface(-10.0, 27.87), -37.87)

    def test_above_and_at_surface(self):
        self.assertEqual(above_surface(35.0, 1.0), 36.0)
        self.assertEqual(at_surface(35.0), 35.0)
        self.assertEqual(above_surface(-10.0, 1.0), -9.0)


class TestBgfSurfaceZOffset(unittest.TestCase):
    def setUp(self):
        self.gui = object.__new__(gen.BSFGeneratorGUI)
        self.data = gen.BGF_DATA["M10"]

    def test_m10_surface_zero_regression(self):
        lines = gen.BSFGeneratorGUI.get_bgf_sequence(self.gui, self.data, 8, surface_z=0.0)
        self.assertIn("L Z-27.8700 F1348 M", lines)
        self.assertIn("L Z-24.8990 R0 FMAX M", lines)
        self.assertIn("L Z+0.0000 FMAX M", lines)
        self.assertIn("L Z+1.0000 R0 FMAX M", lines)

    def test_m10_surface_plus_35(self):
        lines = gen.BSFGeneratorGUI.get_bgf_sequence(self.gui, self.data, 8, surface_z=35.0)
        self.assertIn("L Z+7.1300 F1348 M", lines)
        self.assertIn("L Z+10.1010 R0 FMAX M", lines)
        self.assertIn("L Z+35.0000 FMAX M", lines)
        self.assertIn("L Z+36.0000 R0 FMAX M", lines)

    def test_m10_surface_minus_10(self):
        lines = gen.BSFGeneratorGUI.get_bgf_sequence(self.gui, self.data, 8, surface_z=-10.0)
        self.assertIn("L Z-37.8700 F1348 M", lines)
        self.assertIn("L Z-34.8990 R0 FMAX M", lines)
        self.assertIn("L Z-10.0000 FMAX M", lines)
        self.assertIn("L Z-9.0000 R0 FMAX M", lines)

    def test_incremental_path_unchanged_across_surfaces(self):
        base = _incremental_lines(
            gen.BSFGeneratorGUI.get_bgf_sequence(self.gui, self.data, 8, surface_z=0.0)
        )
        for sz in (35.0, -10.0, 12.5):
            other = _incremental_lines(
                gen.BSFGeneratorGUI.get_bgf_sequence(self.gui, self.data, 8, surface_z=sz)
            )
            self.assertEqual(base, other)

    def test_all_sizes_surface_zero_matches_legacy_absolute_z(self):
        for size, data in gen.BGF_DATA.items():
            with self.subTest(size=size):
                lines = gen.BSFGeneratorGUI.get_bgf_sequence(self.gui, data, 8, surface_z=0.0)
                joined = "\n".join(lines)
                self.assertIn(f"L Z-{data.drill_depth:.4f} F{data.feed_drill} M", joined)
                self.assertIn(f"L Z-{data.mill_start_depth:.4f} R0 FMAX M", joined)
                self.assertIn("L Z+1.0000 R0 FMAX M", joined)
                if data.predrill_depth is not None:
                    self.assertIn(f"L Z-{data.predrill_depth:.4f} F{data.feed_predrill} M", joined)
                if len(data.passes) > 1:
                    self.assertIn("L Z+0.0000 FMAX M", joined)
                # Inkremente / Herstellerbahn-Marker
                self.assertIn("DR- RR", joined)
                self.assertIn("CP IPA-360", joined)
                self.assertIn("TOOL CALL 8 Z DR0", joined)


class TestBgfSinglePositionGuiZ(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_single_surface_35_xy(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Einzelposition")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set("M10")
        self.app.load_bgf_values()
        for key, val in (("single_x", "100"), ("single_y", "50"), ("single_surface_z", "35")):
            self.app.entries[key].configure(state="normal")
            self.app.entries[key].delete(0, "end")
            self.app.entries[key].insert(0, val)
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("L X+100.0000 Y+50.0000 Z+36.0000 R0 FMAX M13", code)
        self.assertIn("L Z+7.1300 F1348 M", code)
        self.assertIn("L Z+10.1010 R0 FMAX M", code)
        self.assertIn("L Z+35.0000 FMAX M", code)
        self.assertIn("CP IPA-360 IZ-1.5000 DR- RR F292 M", code)


if __name__ == "__main__":
    unittest.main()
