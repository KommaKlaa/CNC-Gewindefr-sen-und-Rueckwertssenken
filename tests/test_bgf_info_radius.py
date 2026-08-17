"""PHASE BGF.INFO.1 – Werkzeugradius-Info im NC-Programmkopf."""

from __future__ import annotations

import unittest

import bsf_generator_verbessert_v3 as gen


class TestBgfRadiusInfoComments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _generate_for(self, size: str, tool_def: bool = False) -> str:
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Einzelposition")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set(size)
        self.app.load_bgf_values()
        self.app.output_tool_def_var.set(tool_def)
        for key, val in (("single_x", "0"), ("single_y", "0"), ("single_surface_z", "0")):
            self.app.entries[key].delete(0, "end")
            self.app.entries[key].insert(0, val)
        self.app.generate_bgf_code()
        return self.app.output_text.get("1.0", "end")

    def test_all_sizes_radius_from_bgf_data(self):
        for size, data in gen.BGF_DATA.items():
            with self.subTest(size=size):
                code = self._generate_for(size, tool_def=False)
                expected = f"; WERKZEUGRADIUS: R+{data.radius:.4f} MM"
                self.assertIn(expected, code)
                self.assertIn(f"; CERATIZIT BGF {size}", code)
                self.assertIn(f"; ARTIKEL: {data.article_no}", code)
                self.assertIn("; TOOL DEF: AUS - RADIUS IN WERKZEUGTABELLE PRUEFEN", code)
                self.assertNotIn("\nTOOL DEF ", "\n" + "\n".join(code.splitlines()[:12]))

    def test_m10_m8_m16_exact(self):
        code = self._generate_for("M10")
        self.assertIn("; WERKZEUGRADIUS: R+3.9790 MM", code)
        code = self._generate_for("M8")
        self.assertIn("; WERKZEUGRADIUS: R+3.1720 MM", code)
        code = self._generate_for("M16")
        self.assertIn("; WERKZEUGRADIUS: R+6.5590 MM", code)

    def test_tool_def_on(self):
        code = self._generate_for("M10", tool_def=True)
        self.assertIn("; TOOL DEF: AKTIV", code)
        self.assertIn("; WERKZEUGRADIUS: R+3.9790 MM", code)
        self.assertIn("TOOL DEF 8 L+0.0000 R+3.9790", code)
        self.assertNotIn("; TOOL DEF: AUS", code)

    def test_radius_once_in_header_not_per_coord(self):
        from coordinates import BGFCoordinatePosition

        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Koordinatenliste")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set("M10")
        self.app.load_bgf_values()
        self.app.output_tool_def_var.set(False)
        tpl = gen.BGF_DATA["M10"].thread_length
        self.app.coord_rows = [
            BGFCoordinatePosition(0, 0, 0, tpl),
            BGFCoordinatePosition(100, 0, 0, tpl),
        ]
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertEqual(code.count("; WERKZEUGRADIUS: R+3.9790 MM"), 1)
        self.assertIn("; TOOL DEF: AUS", code)

    def test_motion_unchanged_m10_template(self):
        code = self._generate_for("M10", tool_def=False)
        self.assertIn("L Z-27.8700 F1348 M", code)
        self.assertIn("CP IPA-360 IZ-1.5000 DR- RR F292 M", code)


if __name__ == "__main__":
    unittest.main()
