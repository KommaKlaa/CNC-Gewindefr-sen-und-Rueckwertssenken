"""PHASE BGF.COORD.2 – Parser, Safety-Gates, surface_z, Reihenfolge, Herstellerbahn."""

from __future__ import annotations

import re
import unittest

import bsf_generator_verbessert_v3 as gen
from bgf_depth import DepthGateStatus
from coordinates import (
    BGFCoordinatePosition,
    CoordinateParseError,
    emit_bgf_coordinate_program_body,
    parse_bgf_coordinate_text,
    validate_bgf_coordinate_list,
)
from coordinates.bgf_list_validation import find_duplicate_xyz, validate_safe_z_against_surfaces


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


class TestBgfListParser(unittest.TestCase):
    def test_3_columns_uses_template(self):
        rows = parse_bgf_coordinate_text("100;200;0", default_thread_depth=25.06)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].x, 100.0)
        self.assertEqual(rows[0].y, 200.0)
        self.assertEqual(rows[0].surface_z, 0.0)
        self.assertEqual(rows[0].thread_depth, 25.06)
        self.assertIsNone(rows[0].core_hole_depth)

    def test_4_columns_thread(self):
        rows = parse_bgf_coordinate_text("100;200;0;20", default_thread_depth=25.06)
        self.assertEqual(rows[0].thread_depth, 20.0)
        self.assertIsNone(rows[0].core_hole_depth)

    def test_5_columns_full(self):
        rows = parse_bgf_coordinate_text("100;200;0;20;30", default_thread_depth=25.06)
        self.assertEqual(rows[0].core_hole_depth, 30.0)

    def test_german_decimal(self):
        rows = parse_bgf_coordinate_text("100,5;200,25;0;25,06;30", default_thread_depth=25.06)
        self.assertEqual(rows[0].x, 100.5)
        self.assertEqual(rows[0].y, 200.25)
        self.assertEqual(rows[0].thread_depth, 25.06)

    def test_tab_separated(self):
        rows = parse_bgf_coordinate_text("100\t200\t0\t25.06\t30", default_thread_depth=25.06)
        self.assertEqual(rows[0].x, 100.0)
        self.assertEqual(rows[0].core_hole_depth, 30.0)

    def test_negative_xy_surface(self):
        rows = parse_bgf_coordinate_text("-10;-20;-5;25.06", default_thread_depth=25.06)
        self.assertEqual(rows[0].x, -10.0)
        self.assertEqual(rows[0].y, -20.0)
        self.assertEqual(rows[0].surface_z, -5.0)

    def test_invalid_y_with_line(self):
        with self.assertRaises(CoordinateParseError) as ctx:
            parse_bgf_coordinate_text(
                "0;0;0;25.06\n100;ABC;0;25.06\n200;50;0;25.06",
                default_thread_depth=25.06,
            )
        joined = "\n".join(ctx.exception.messages)
        self.assertIn("Zeile 2", joined)
        self.assertIn("Y", joined)
        self.assertIn("ABC", joined)

    def test_2_columns_error(self):
        with self.assertRaises(CoordinateParseError):
            parse_bgf_coordinate_text("100;200", default_thread_depth=25.06)

    def test_6_columns_error(self):
        with self.assertRaises(CoordinateParseError):
            parse_bgf_coordinate_text("1;2;3;4;5;6", default_thread_depth=25.06)


class TestProgramWideGate(unittest.TestCase):
    def test_all_template_allowed(self):
        policy = _m10_policy()
        positions = [
            BGFCoordinatePosition(0, 0, 0, 25.06),
            BGFCoordinatePosition(100, 50, 0, 25.06),
        ]
        result = validate_bgf_coordinate_list(
            positions, policy, safe_z=100, end_safe_z=200, approach_clearance=1.0
        )
        self.assertTrue(result.ok_for_nc)

    def test_mixed_depths_allowed(self):
        policy = _m10_policy()
        positions = [
            BGFCoordinatePosition(0, 0, 0, 25.06),
            BGFCoordinatePosition(100, 50, 0, 20.0),
        ]
        result = validate_bgf_coordinate_list(
            positions, policy, safe_z=100, end_safe_z=200, approach_clearance=1.0
        )
        self.assertTrue(result.ok_for_nc)
        self.assertEqual(result.positions[0].status_code, DepthGateStatus.TEMPLATE_OK)
        self.assertEqual(
            result.positions[1].status_code, DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK
        )

    def test_one_over_max_blocks_all(self):
        policy = _m10_policy()
        positions = [
            BGFCoordinatePosition(0, 0, 0, 25.06),
            BGFCoordinatePosition(100, 50, 0, 26.0),
        ]
        result = validate_bgf_coordinate_list(
            positions, policy, safe_z=100, end_safe_z=200, approach_clearance=1.0
        )
        self.assertFalse(result.ok_for_nc)
        self.assertTrue(any("Position 2" in e for e in result.errors))
        self.assertEqual(
            result.positions[1].status_code,
            DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX,
        )

    def test_core_hole_blocks(self):
        policy = _m10_policy()
        positions = [BGFCoordinatePosition(0, 0, 0, 20.0, 18.0)]
        result = validate_bgf_coordinate_list(
            positions, policy, safe_z=100, end_safe_z=200, approach_clearance=1.0
        )
        self.assertFalse(result.ok_for_nc)
        self.assertEqual(result.positions[0].status_code, DepthGateStatus.CORE_HOLE_EXCEEDED)

    def test_empty_list_blocks(self):
        result = validate_bgf_coordinate_list(
            [], _m10_policy(), safe_z=100, end_safe_z=200, approach_clearance=1.0
        )
        self.assertFalse(result.ok_for_nc)
        self.assertIn("Keine Bearbeitungspositionen vorhanden.", result.errors)


class TestSafeZGate(unittest.TestCase):
    def test_safe_above_approach_pass(self):
        # clearance=1: approach = surface+1; safe_z >= approach
        errs = validate_safe_z_against_surfaces(
            100, 200, [BGFCoordinatePosition(0, 0, 0, 25.06)], approach_clearance=1.0
        )
        self.assertEqual(errs, [])
        errs = validate_safe_z_against_surfaces(
            100, 200, [BGFCoordinatePosition(0, 0, 99, 25.06)], approach_clearance=1.0
        )
        self.assertEqual(errs, [])

    def test_safe_below_approach_block(self):
        # surface=100, clearance=1 → approach=101 > safe 100
        errs = validate_safe_z_against_surfaces(
            100, 200, [BGFCoordinatePosition(0, 0, 100, 25.06)], approach_clearance=1.0
        )
        self.assertTrue(errs)
        errs = validate_safe_z_against_surfaces(
            100, 200, [BGFCoordinatePosition(0, 0, 120, 25.06)], approach_clearance=1.0
        )
        self.assertTrue(errs)

    def test_end_safe_block(self):
        errs = validate_safe_z_against_surfaces(
            200, 100, [BGFCoordinatePosition(0, 0, 100, 25.06)], approach_clearance=1.0
        )
        self.assertTrue(any("End-Sicherheits-Z" in e for e in errs))


class TestDuplicates(unittest.TestCase):
    def test_duplicate_xyz_detected(self):
        positions = [
            BGFCoordinatePosition(100, 50, 0, 25.06),
            BGFCoordinatePosition(100, 50, 0, 20.0),
        ]
        dups = find_duplicate_xyz(positions)
        self.assertEqual(dups, [(100.0, 50.0, 0.0)])
        result = validate_bgf_coordinate_list(
            positions, _m10_policy(), safe_z=100, end_safe_z=200, approach_clearance=1.0
        )
        self.assertTrue(any("doppelte Positionen" in w for w in result.warnings))


class TestSurfaceZNc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_m10_z0_and_z35_absolute_and_incremental(self):
        data = gen.BGF_DATA["M10"]
        seq0 = self.app.get_bgf_sequence(data, 8, surface_z=0.0)
        seq35 = self.app.get_bgf_sequence(data, 8, surface_z=35.0)
        text0 = "\n".join(seq0)
        text35 = "\n".join(seq35)

        self.assertIn("L Z-27.8700 F1348 M", text0)
        self.assertIn("L Z-24.8990 R0 FMAX M", text0)
        self.assertIn("L Z+0.0000 FMAX M", text0)
        self.assertIn("L Z+1.0000 R0 FMAX M", text0)

        self.assertIn("L Z+7.1300 F1348 M", text35)
        self.assertIn("L Z+10.1010 R0 FMAX M", text35)
        self.assertIn("L Z+35.0000 FMAX M", text35)
        self.assertIn("L Z+36.0000 R0 FMAX M", text35)

        incr = re.compile(r"\b(CC|CP|IPA|IX|IY|IZ|DR-|RR|F\d+)\b")
        self.assertEqual(incr.findall(text0), incr.findall(text35))

    def test_order_preserved_in_emit(self):
        positions = [
            BGFCoordinatePosition(100, 0, 0, 25.06),
            BGFCoordinatePosition(0, 100, 0, 25.06),
            BGFCoordinatePosition(50, 50, 0, 25.06),
        ]
        data = gen.BGF_DATA["M10"]

        def seq(pos):
            return self.app.get_bgf_sequence(data, 8, surface_z=pos.surface_z)

        lines = emit_bgf_coordinate_program_body(
            positions, safe_z=100, end_safe_z=200, sequence_for_position=seq
        )
        text = "\n".join(lines)
        i1 = text.index("L X+100.0000 Y+0.0000 R0 FMAX")
        i2 = text.index("L X+0.0000 Y+100.0000 R0 FMAX")
        i3 = text.index("L X+50.0000 Y+50.0000 R0 FMAX")
        self.assertLess(i1, i2)
        self.assertLess(i2, i3)

    def test_gui_generates_multi_surface(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Koordinatenliste")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set("M10")
        self.app.load_bgf_values()
        tpl = gen.BGF_DATA["M10"].thread_length
        self.app.coord_rows = [
            BGFCoordinatePosition(0, 0, 0.0, tpl),
            BGFCoordinatePosition(100, 50, 35.0, tpl),
        ]
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("L Z-27.8700 F1348 M", code)
        self.assertIn("L Z+7.1300 F1348 M", code)
        self.assertIn("L Z+10.1010 R0 FMAX M", code)
        self.assertIn("L Z+35.0000 FMAX M", code)
        self.assertIn("L Z+36.0000 R0 FMAX M", code)
        # Vor XY-Wechsel Rueckzug auf safe_z
        self.assertIn("Rueckzug vor naechster XY-Fahrt", code)

    def test_gui_blocks_over_max_no_partial(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Koordinatenliste")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set("M10")
        self.app.load_bgf_values()
        self.app.output_text.delete("1.0", "end")
        self.app.coord_rows = [
            BGFCoordinatePosition(0, 0, 0.0, 25.06),
            BGFCoordinatePosition(100, 50, 0.0, 26.0),
        ]
        # messagebox.showerror wird in Headless-Umgebung trotzdem aufgerufen – abfangen
        blocked = {"called": False}
        original = gen.messagebox.showerror

        def fake_error(*args, **kwargs):
            blocked["called"] = True

        gen.messagebox.showerror = fake_error
        try:
            self.app.generate_bgf_code()
        finally:
            gen.messagebox.showerror = original
        self.assertTrue(blocked["called"])
        code = self.app.output_text.get("1.0", "end").strip()
        self.assertEqual(code, "")

    def test_combo_shows_coordinates_and_tree(self):
        values = tuple(self.app.position_mode_combo.cget("values"))
        self.assertEqual(values, ("Teilkreis", "Einzelposition", "Koordinatenliste"))
        self.app.position_mode_var.set("Koordinatenliste")
        self.app.on_position_mode_change(None)
        self.assertEqual(self.app.coord_list_frame.winfo_manager(), "grid")
        cols = self.app.coord_tree.cget("columns")
        self.assertEqual(cols, ("nr", "x", "y", "sz", "td", "ch", "status"))


if __name__ == "__main__":
    unittest.main()
