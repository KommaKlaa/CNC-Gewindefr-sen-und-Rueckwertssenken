"""Tests fuer PHASE BGF.DEPTH.2/3A – Tiefenvalidierung und freigegebene Maxima."""

from __future__ import annotations

import unittest

from bgf_depth import (
    BGFDepthPolicy,
    BGFDepthRequest,
    DepthGateStatus,
    evaluate_bgf_depth,
    exceeds_approved_max,
    is_template_thread_depth,
    policy_from_tool,
    thread_end_z,
)
from bgf_depth_approvals import APPROVED_MAX_THREAD_DEPTH_BY_TOOL, approved_max_thread_depth
from bgf_depth_reference import HoleType, MANUFACTURER_DEPTH_REFERENCES, references_for_size
from bgf_variable_depth import axial_increment_from_passes
import bsf_generator_verbessert_v3 as gen


def _m10_policy(**kwargs) -> BGFDepthPolicy:
    data = gen.BGF_DATA["M10"]
    base = dict(
        thread_size="M10",
        article_no=data.article_no,
        template_thread_depth=data.thread_length,
        template_drill_depth=data.drill_depth,
        template_mill_start_depth=data.mill_start_depth,
        approved_max_thread_depth=25.06,
        axial_increment=axial_increment_from_passes(data.passes),
        variable_depth_rule_validated=False,
    )
    base.update(kwargs)
    return BGFDepthPolicy(**base)


class TestDepthBasics(unittest.TestCase):
    def test_thread_end_z(self):
        self.assertEqual(thread_end_z(0.0, 20.0), -20.0)
        self.assertEqual(thread_end_z(35.0, 20.0), 15.0)

    def test_template_detection(self):
        self.assertTrue(is_template_thread_depth(25.06, 25.06))
        self.assertTrue(is_template_thread_depth(25.0600001, 25.06))
        self.assertFalse(is_template_thread_depth(20.0, 25.06))


class TestDepthValidation(unittest.TestCase):
    def test_zero_invalid(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(0.0), _m10_policy())
        self.assertFalse(ev.ok_for_nc)
        self.assertEqual(ev.status, DepthGateStatus.INVALID)

    def test_negative_invalid(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(-10.0), _m10_policy())
        self.assertFalse(ev.ok_for_nc)
        self.assertEqual(ev.status, DepthGateStatus.INVALID)

    def test_nan_invalid(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(float("nan")), _m10_policy())
        self.assertFalse(ev.ok_for_nc)
        self.assertEqual(ev.status, DepthGateStatus.INVALID)

    def test_inf_invalid(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(float("inf")), _m10_policy())
        self.assertFalse(ev.ok_for_nc)
        self.assertEqual(ev.status, DepthGateStatus.INVALID)

    def test_thread_gt_core_blocked(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(20.0, 18.0), _m10_policy())
        self.assertFalse(ev.ok_for_nc)
        self.assertEqual(ev.status, DepthGateStatus.CORE_HOLE_EXCEEDED)
        self.assertTrue(any("20.000" in m and "18.000" in m for m in ev.messages))

    def test_thread_eq_core_axial_shift_ok(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(20.0, 20.0), _m10_policy())
        self.assertNotEqual(ev.status, DepthGateStatus.CORE_HOLE_EXCEEDED)
        self.assertTrue(ev.ok_for_nc)
        self.assertEqual(ev.status, DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK)
        self.assertTrue(ev.within_approved_max)

    def test_thread_lt_core_axial_shift_ok(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(20.0, 25.0), _m10_policy())
        self.assertTrue(ev.ok_for_nc)
        self.assertEqual(ev.status, DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK)
        self.assertEqual(ev.thread_end_z, -20.0)


class TestMaxDepth(unittest.TestCase):
    def test_max_boundaries_synthetic(self):
        policy = _m10_policy(approved_max_thread_depth=25.0, variable_depth_rule_validated=False)
        ev_ok_range = evaluate_bgf_depth(BGFDepthRequest(24.999), policy)
        self.assertNotEqual(ev_ok_range.status, DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX)
        self.assertTrue(ev_ok_range.ok_for_nc)
        self.assertEqual(ev_ok_range.status, DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK)

        ev_eq = evaluate_bgf_depth(BGFDepthRequest(25.0), policy)
        self.assertNotEqual(ev_eq.status, DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX)

        ev_over = evaluate_bgf_depth(BGFDepthRequest(25.001), policy)
        self.assertEqual(ev_over.status, DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX)
        self.assertFalse(ev_over.ok_for_nc)
        self.assertTrue(any("25.001" in m and "25.000" in m for m in ev_over.messages))

    def test_max_none_variable(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(20.0), _m10_policy(approved_max_thread_depth=None))
        self.assertEqual(ev.status, DepthGateStatus.MAX_THREAD_DEPTH_UNVALIDATED)
        self.assertFalse(ev.ok_for_nc)

    def test_priority_max_before_core(self):
        # 30 > approved 25.06 und 30 > core 20 → zuerst Freigabegrenze
        ev = evaluate_bgf_depth(BGFDepthRequest(30.0, 20.0), _m10_policy())
        self.assertEqual(ev.status, DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX)


class TestApprovedMaxAllTools(unittest.TestCase):
    CASES = [
        ("M5", 12.58, 12.59),
        ("M6", 14.69, 14.70),
        ("M8", 20.88, 20.89),
        ("M10", 25.06, 25.07),
        ("M16", 32.96, 32.97),
        ("M16x1.5", 32.60, 32.61),
    ]

    def test_pass_and_block_per_tool(self):
        for size, approved, over in self.CASES:
            with self.subTest(size=size):
                data = gen.BGF_DATA[size]
                self.assertEqual(approved_max_thread_depth(data.size, data.article_no), approved)
                policy = policy_from_tool(
                    data.size,
                    data.thread_length,
                    data.drill_depth,
                    data.mill_start_depth,
                    article_no=data.article_no,
                    approved_max_thread_depth=approved,
                    axial_increment=axial_increment_from_passes(data.passes),
                )
                ev_pass = evaluate_bgf_depth(BGFDepthRequest(approved), policy)
                self.assertNotEqual(ev_pass.status, DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX)
                self.assertTrue(ev_pass.ok_for_nc)  # template == approved

                ev_block = evaluate_bgf_depth(BGFDepthRequest(over), policy)
                self.assertEqual(ev_block.status, DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX)
                self.assertFalse(ev_block.ok_for_nc)

    def test_m10_boundaries(self):
        policy = _m10_policy()
        self.assertFalse(exceeds_approved_max(25.059, 25.06))
        self.assertFalse(exceeds_approved_max(25.060, 25.06))
        self.assertTrue(exceeds_approved_max(25.061, 25.06))
        self.assertNotEqual(
            evaluate_bgf_depth(BGFDepthRequest(25.059), policy).status,
            DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX,
        )
        self.assertTrue(evaluate_bgf_depth(BGFDepthRequest(25.060), policy).ok_for_nc)
        self.assertEqual(
            evaluate_bgf_depth(BGFDepthRequest(25.061), policy).status,
            DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX,
        )

    def test_m10_20_max_pass_axial_shift_ok(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(20.0), _m10_policy())
        self.assertTrue(ev.within_approved_max)
        self.assertEqual(ev.status, DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK)
        self.assertTrue(ev.ok_for_nc)

    def test_m10_26_max_block(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(26.0, 40.0), _m10_policy())
        self.assertEqual(ev.status, DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX)
        self.assertFalse(ev.ok_for_nc)

    def test_approvals_keyed_by_article(self):
        self.assertEqual(len(APPROVED_MAX_THREAD_DEPTH_BY_TOOL), 6)
        self.assertIsNone(approved_max_thread_depth("M10", "WRONG"))


class TestTemplateNc(unittest.TestCase):
    def setUp(self):
        self.gui = object.__new__(gen.BSFGeneratorGUI)
        self.data = gen.BGF_DATA["M10"]

    def test_m10_template_surface_0(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(25.06), _m10_policy(), surface_z=0.0)
        self.assertTrue(ev.ok_for_nc)
        self.assertTrue(ev.is_template)
        lines = gen.BSFGeneratorGUI.get_bgf_sequence(self.gui, self.data, 8, surface_z=0.0)
        self.assertIn("L Z-27.8700 F1348 M", lines)
        self.assertIn("L Z-24.8990 R0 FMAX M", lines)
        self.assertIn("L Z+0.0000 FMAX M", lines)
        self.assertIn("L Z+1.0000 R0 FMAX M", lines)

    def test_m10_template_surface_35(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(25.06), _m10_policy(), surface_z=35.0)
        self.assertTrue(ev.ok_for_nc)
        lines = gen.BSFGeneratorGUI.get_bgf_sequence(self.gui, self.data, 8, surface_z=35.0)
        self.assertIn("L Z+7.1300 F1348 M", lines)
        self.assertIn("L Z+10.1010 R0 FMAX M", lines)
        self.assertIn("L Z+35.0000 FMAX M", lines)
        self.assertIn("L Z+36.0000 R0 FMAX M", lines)

    def test_m10_20_axial_shift_nc(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(20.0, 30.0), _m10_policy(), surface_z=0.0)
        self.assertEqual(ev.thread_end_z, -20.0)
        self.assertTrue(ev.ok_for_nc)
        self.assertFalse(ev.is_template)
        self.assertEqual(ev.status, DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK)
        self.assertAlmostEqual(ev.nc_mill_start_depth, 19.839, places=3)
        self.assertAlmostEqual(ev.nc_drill_depth, 22.810, places=3)
        lines = gen.BSFGeneratorGUI.get_bgf_sequence(
            self.gui,
            self.data,
            8,
            surface_z=0.0,
            drill_depth=ev.nc_drill_depth,
            mill_start_depth=ev.nc_mill_start_depth,
        )
        self.assertIn("L Z-22.8100 F1348 M", lines)
        self.assertIn("L Z-19.8390 R0 FMAX M", lines)


class TestReferenceData(unittest.TestCase):
    def test_m10_refs_present(self):
        refs = references_for_size("M10")
        self.assertTrue(any(r.thread_depth == 17.0 and r.core_hole_depth == 27.0 for r in refs))
        self.assertTrue(any(r.thread_depth == 25.0 and r.core_hole_depth == 30.0 for r in refs))

    def test_dulo_not_numeric(self):
        dulos = [r for r in MANUFACTURER_DEPTH_REFERENCES if r.hole_type == HoleType.THROUGH]
        self.assertTrue(len(dulos) >= 1)
        for r in dulos:
            self.assertIsNone(r.core_hole_depth)

    def test_no_interpolation_api(self):
        import bgf_depth_reference as ref

        self.assertFalse(hasattr(ref, "interpolate"))
        self.assertFalse(hasattr(ref, "linear_core_hole"))


class TestGuiDepthGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _prep_single_m10(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.bgf_size_var.set("M10")
        self.app.load_bgf_values()
        self.app.position_mode_var.set("Einzelposition")
        self.app.on_position_mode_change(None)

    def test_default_thread_depth_template(self):
        self._prep_single_m10()
        self.assertAlmostEqual(float(self.app.entries["bgf_thread_depth"].get()), 25.06, places=3)

    def test_template_generates(self):
        self._prep_single_m10()
        for k, v in (("single_x", "0"), ("single_y", "0"), ("single_surface_z", "0")):
            self.app.entries[k].delete(0, "end")
            self.app.entries[k].insert(0, v)
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("L Z-27.8700 F1348 M", code)

    def test_variable_20_axial_shift_ok(self):
        self._prep_single_m10()
        self.app.entries["bgf_thread_depth"].delete(0, "end")
        self.app.entries["bgf_thread_depth"].insert(0, "20")
        self.app.entries["bgf_core_hole_depth"].delete(0, "end")
        self.app.entries["bgf_core_hole_depth"].insert(0, "30")
        ev = self.app.evaluate_current_bgf_depth()
        self.assertTrue(ev.ok_for_nc)
        self.assertEqual(ev.thread_end_z, -20.0)
        self.assertTrue(ev.within_approved_max)
        self.assertEqual(ev.status, DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK)
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("L Z-22.8100 F1348 M", code)
        self.assertIn("L Z-19.8390 R0 FMAX M", code)

    def test_core_18_thread_20_error(self):
        self._prep_single_m10()
        self.app.entries["bgf_thread_depth"].delete(0, "end")
        self.app.entries["bgf_thread_depth"].insert(0, "20")
        self.app.entries["bgf_core_hole_depth"].delete(0, "end")
        self.app.entries["bgf_core_hole_depth"].insert(0, "18")
        ev = self.app.evaluate_current_bgf_depth()
        self.assertEqual(ev.status, DepthGateStatus.CORE_HOLE_EXCEEDED)

    def test_m10_26_exceeds_approved(self):
        self._prep_single_m10()
        self.app.entries["bgf_thread_depth"].delete(0, "end")
        self.app.entries["bgf_thread_depth"].insert(0, "26")
        ev = self.app.evaluate_current_bgf_depth()
        self.assertEqual(ev.status, DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX)
        self.app.update_bgf_depth_status()
        self.assertIn("25.060", self.app.bgf_depth_info_labels["max_depth"].cget("text"))

    def test_m8_ui_switch_updates_approved_max(self):
        self._prep_single_m10()
        self.app.bgf_size_var.set("M8")
        self.app.load_bgf_values()
        self.assertAlmostEqual(float(self.app.entries["bgf_thread_depth"].get()), 20.88, places=2)
        self.app.update_bgf_depth_status()
        self.assertIn("20.880", self.app.bgf_depth_info_labels["max_depth"].cget("text"))
        policy = self.app.get_bgf_depth_policy()
        self.assertEqual(policy.approved_max_thread_depth, 20.88)


if __name__ == "__main__":
    unittest.main()
