"""PHASE BGF.CHAIN.1 – CALL-PGM-kompatibler BGF-Programabschluss."""

from __future__ import annotations

import re
import unittest
from typing import Optional

import tkinter as tk

import bsf_generator_verbessert_v3 as gen
from bgf_chain import (
    BGF_CHAIN_END_LABEL,
    analyze_bgf_part_circle_nc,
    has_program_end_m_code,
    require_bgf_part_circle_chain_safe,
)
from ui import MODE_BGF


def _set(app, key: str, value) -> None:
    app.entries[key].delete(0, tk.END)
    app.entries[key].insert(0, str(value))


def _prepare_bgf_circle(
    app,
    *,
    size: str = "M16",
    diameter: str = "430",
    count: str = "6",
    start_angle: str = "0",
    center_x: str = "0",
    center_y: str = "0",
    surface_z: str = "-10",
    thread_depth: Optional[str] = None,
    approach_clearance: str = "10",
    blank_size: str = "1000",
    blank_height: str = "60",
    raw_stock_top_z: str = "0",
    program_name: str = "HPR5000M16",
    end_safe_z: str = "200",
    safe_z: str = "100",
) -> str:
    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    app.position_mode_var.set("Teilkreis")
    app.on_position_mode_change(None)
    app.bgf_size_var.set(size)
    app.load_bgf_values()
    _set(app, "diameter", diameter)
    _set(app, "count", count)
    _set(app, "start_angle", start_angle)
    _set(app, "center_x", center_x)
    _set(app, "center_y", center_y)
    _set(app, "circle_surface_z", surface_z)
    if thread_depth is not None:
        _set(app, "bgf_thread_depth", thread_depth)
    _set(app, "approach_clearance", approach_clearance)
    _set(app, "blank_size", blank_size)
    _set(app, "blank_height", blank_height)
    _set(app, "raw_stock_top_z", raw_stock_top_z)
    _set(app, "end_safe_z", end_safe_z)
    _set(app, "safe_z", safe_z)
    _set(app, "program_name", program_name)
    app.generate_bgf_code()
    return app.output_text.get("1.0", tk.END)


class TestBgfChainAnalyzer(unittest.TestCase):
    def test_end_label_999_is_reserved(self):
        self.assertEqual(BGF_CHAIN_END_LABEL, 999)

    def test_fallthrough_counts_as_plus_one(self):
        nc = "\n".join(
            [
                "BEGIN PGM TEST MM",
                "Q2 = +0",
                "LBL 1",
                "CALL LBL 100",
                "Q2 = Q2 + 1",
                "FN 12: IF +Q2 LT +6 GOTO LBL 1",
                "L Z+200.0000 R0 FMAX",
                "LBL 100",
                "LBL 0",
                "LBL 999",
                "END PGM TEST MM",
            ]
        )
        flow = analyze_bgf_part_circle_nc(nc)
        self.assertTrue(flow.linear_fallthrough)
        self.assertEqual(flow.simulated_machining_count, 7)
        self.assertTrue(flow.extra_final_machining)
        self.assertFalse(flow.ok)


class TestBgfPartCircleChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_counts_never_plus_one(self):
        for count in (1, 2, 6, 8, 24):
            with self.subTest(count=count):
                diameter = "580" if count == 8 else "430"
                blank = "1500" if count == 8 else "1000"
                code = _prepare_bgf_circle(
                    self.app,
                    count=str(count),
                    diameter=diameter,
                    blank_size=blank,
                    program_name="TEST_BGF",
                )
                flow = require_bgf_part_circle_chain_safe(code, count)
                self.assertEqual(flow.simulated_machining_count, count)
                self.assertNotEqual(flow.simulated_machining_count, count + 1)
                self.assertFalse(flow.extra_final_machining)
                self.assertFalse(flow.linear_fallthrough)
                self.assertFalse(flow.has_m30)
                self.assertFalse(flow.has_m2)

    def test_no_m30_m2_in_part_circle(self):
        code = _prepare_bgf_circle(self.app)
        has_m30, has_m2 = has_program_end_m_code(code)
        self.assertFalse(has_m30)
        self.assertFalse(has_m2)
        self.assertNotIn("M30", code)
        self.assertIsNone(re.search(r"\bM2\b", code))

    def test_end_label_after_lbl0_then_end_pgm(self):
        code = _prepare_bgf_circle(self.app, program_name="HPR5000M16")
        lines = [ln.rstrip() for ln in code.splitlines() if ln.strip()]
        i100 = next(i for i, ln in enumerate(lines) if ln.startswith("LBL 100"))
        i0 = next(i for i, ln in enumerate(lines) if ln == "LBL 0")
        i999 = next(i for i, ln in enumerate(lines) if ln == "LBL 999")
        iend = next(i for i, ln in enumerate(lines) if ln.startswith("END PGM "))
        self.assertLess(i100, i0)
        self.assertLess(i0, i999)
        self.assertEqual(i999 + 1, iend)
        self.assertEqual(lines[iend], "END PGM HPR5000M16 MM")
        self.assertIn("FN 9: IF +0 EQU +0 GOTO LBL 999", code)

    def test_control_flow_structure(self):
        code = _prepare_bgf_circle(self.app, count="6")
        flow = analyze_bgf_part_circle_nc(code)
        self.assertTrue(flow.q2_starts_at_zero)
        self.assertTrue(flow.call_before_q2_increment)
        self.assertTrue(flow.q2_increment_once_per_iteration)
        self.assertEqual(flow.fn12_lt_count, 6)
        self.assertTrue(flow.skip_after_loop)
        self.assertTrue(flow.lbl100_only_via_call)
        self.assertTrue(flow.end_pgm_reachable)
        self.assertTrue(flow.call_pgm_safe_return)

    def test_hpr5000_m16_chain_safe(self):
        code = _prepare_bgf_circle(self.app)
        self.assertIn("LP PR+215.0000 PA+Q1 R0 FMAX ; Teilkreisposition", code)
        self.assertIn("CC X+0.0000 Y+0.0000 ; Teilkreis-Mitte / Pol", code)
        flow = require_bgf_part_circle_chain_safe(code, 6)
        self.assertEqual(flow.simulated_machining_count, 6)
        self.assertFalse(flow.extra_final_machining)
        self.assertTrue(flow.call_pgm_safe_return)
        self.assertIn("L Z-12.1000 F682 M", code)
        self.assertIn("L Z-47.1160 F2046 M", code)

    def test_eight_hole_diameter_580(self):
        code = _prepare_bgf_circle(
            self.app,
            diameter="580",
            count="8",
            blank_size="1500",
            surface_z="30",
            raw_stock_top_z="30",
            program_name="LPR_5_AUF_M16",
        )
        flow = require_bgf_part_circle_chain_safe(code, 8)
        self.assertEqual(flow.simulated_machining_count, 8)
        self.assertIn("LP PR+290.0000 PA+Q1 R0 FMAX ; Teilkreisposition", code)

    def test_call_pgm_regression(self):
        child = _prepare_bgf_circle(self.app, program_name="TEST_BGF")
        caller = "CALL PGM TEST_BGF.H\nSTOP\n"
        self.assertIn("CALL PGM TEST_BGF.H", caller)
        self.assertIn("BEGIN PGM TEST_BGF MM", child)
        self.assertIn("END PGM TEST_BGF MM", child)
        flow = require_bgf_part_circle_chain_safe(child, 6)
        self.assertFalse(flow.has_m30)
        self.assertFalse(flow.has_m2)
        self.assertFalse(flow.linear_fallthrough)
        self.assertTrue(flow.end_pgm_reachable)
        self.assertTrue(flow.call_pgm_safe_return)

    def test_manufacturer_motion_needles_unchanged(self):
        code = _prepare_bgf_circle(self.app)
        for needle in (
            "CC IX",
            "CP IPA",
            "IZ",
            "DR-",
            "RR",
            "L Z-12.1000 F682 M",
            "L Z-47.1160 F2046 M",
        ):
            self.assertIn(needle, code)

    def test_single_and_list_reach_end_pgm_without_m30(self):
        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.bgf_size_var.set("M16")
        app.load_bgf_values()
        _set(app, "single_x", "0")
        _set(app, "single_y", "0")
        _set(app, "single_surface_z", "-10")
        _set(app, "raw_stock_top_z", "0")
        _set(app, "blank_height", "60")
        _set(app, "blank_size", "1000")
        _set(app, "approach_clearance", "10")
        _set(app, "end_safe_z", "200")
        _set(app, "program_name", "TEST_BGF_SINGLE")
        app.generate_bgf_code()
        single = app.output_text.get("1.0", tk.END)
        self.assertIn("END PGM TEST_BGF_SINGLE MM", single)
        self.assertNotIn("M30", single)
        self.assertIsNone(re.search(r"\bM2\b", single))

        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        from coordinates import BGFCoordinatePosition

        tpl = gen.BGF_DATA["M16"].thread_length
        app.coord_rows = [
            BGFCoordinatePosition(0, 0, -10.0, tpl),
            BGFCoordinatePosition(100, 0, -10.0, tpl),
        ]
        _set(app, "program_name", "TEST_BGF_LIST")
        app.generate_bgf_code()
        listed = app.output_text.get("1.0", tk.END)
        self.assertIn("END PGM TEST_BGF_LIST MM", listed)
        self.assertNotIn("M30", listed)
        self.assertIsNone(re.search(r"\bM2\b", listed))
        self.assertTrue(listed.rstrip().endswith("END PGM TEST_BGF_LIST MM"))
