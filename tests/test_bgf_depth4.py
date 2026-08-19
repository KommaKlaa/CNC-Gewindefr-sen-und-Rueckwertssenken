"""PHASE BGF.DEPTH.4 – AXIAL_TEMPLATE_SHIFT_MODEL."""

from __future__ import annotations

import re
import unittest

import bsf_generator_verbessert_v3 as gen
from bgf_depth import BGFDepthRequest, DepthGateStatus, evaluate_bgf_depth, policy_from_tool
from bgf_variable_depth import (
    DEPTH_MODEL_NAME,
    axial_increment_from_passes,
    compute_axial_template_shift,
    template_drill_reserve,
)
from coordinates import BGFCoordinatePosition, validate_bgf_coordinate_list


def _policy_for(size: str):
    data = gen.BGF_DATA[size]
    approved = gen.approved_max_thread_depth(data.size, data.article_no)
    return policy_from_tool(
        data.size,
        data.thread_length,
        data.drill_depth,
        data.mill_start_depth,
        article_no=data.article_no,
        approved_max_thread_depth=approved,
        axial_increment=axial_increment_from_passes(data.passes),
    )


class TestAxialShiftMath(unittest.TestCase):
    def test_model_name(self):
        self.assertEqual(DEPTH_MODEL_NAME, "AXIAL_TEMPLATE_SHIFT_MODEL")

    def test_m10_20_numbers(self):
        data = gen.BGF_DATA["M10"]
        ax = axial_increment_from_passes(data.passes)
        self.assertAlmostEqual(ax, 1.950, places=3)
        shift = compute_axial_template_shift(
            requested_thread_depth=20.0,
            template_thread_depth=data.thread_length,
            template_mill_start_depth=data.mill_start_depth,
            template_drill_depth=data.drill_depth,
            axial_increment=ax,
        )
        self.assertTrue(shift.ok)
        self.assertAlmostEqual(shift.depth_delta, 5.060, places=3)
        self.assertAlmostEqual(shift.mill_start_depth, 19.839, places=3)
        self.assertAlmostEqual(shift.drill_depth, 22.810, places=3)
        self.assertAlmostEqual(shift.deepest_milling_depth, 21.789, places=3)
        self.assertAlmostEqual(shift.drill_reserve, 1.021, places=3)

    def test_m10_10_numbers(self):
        data = gen.BGF_DATA["M10"]
        ax = axial_increment_from_passes(data.passes)
        shift = compute_axial_template_shift(
            requested_thread_depth=10.0,
            template_thread_depth=data.thread_length,
            template_mill_start_depth=data.mill_start_depth,
            template_drill_depth=data.drill_depth,
            axial_increment=ax,
        )
        self.assertTrue(shift.ok)
        self.assertAlmostEqual(shift.mill_start_depth, 9.839, places=3)
        self.assertAlmostEqual(shift.drill_depth, 12.810, places=3)


class TestDepth4Gate(unittest.TestCase):
    def test_m10_template(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(25.06), _policy_for("M10"))
        self.assertTrue(ev.ok_for_nc)
        self.assertEqual(ev.status, DepthGateStatus.TEMPLATE_OK)
        self.assertAlmostEqual(ev.nc_drill_depth, 27.870, places=3)
        self.assertAlmostEqual(ev.nc_mill_start_depth, 24.899, places=3)

    def test_m10_20(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(20.0), _policy_for("M10"))
        self.assertTrue(ev.ok_for_nc)
        self.assertEqual(ev.status, DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK)
        self.assertAlmostEqual(ev.nc_mill_start_depth, 19.839, places=3)
        self.assertAlmostEqual(ev.nc_drill_depth, 22.810, places=3)

    def test_m10_10(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(10.0), _policy_for("M10"))
        self.assertTrue(ev.ok_for_nc)
        self.assertEqual(ev.status, DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK)

    def test_m10_26_block(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(26.0), _policy_for("M10"))
        self.assertFalse(ev.ok_for_nc)
        self.assertEqual(ev.status, DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX)

    def test_m10_20_surface_35(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(20.0), _policy_for("M10"), surface_z=35.0)
        self.assertTrue(ev.ok_for_nc)
        self.assertAlmostEqual(ev.thread_end_z, 15.0, places=4)
        self.assertAlmostEqual(ev.nc_mill_start_z, 15.161, places=3)
        self.assertAlmostEqual(ev.nc_drill_z, 12.190, places=3)


class TestReserveInvariantAllTools(unittest.TestCase):
    def test_all_tools_reserve_invariant(self):
        for size in gen.BGF_DATA:
            with self.subTest(size=size):
                data = gen.BGF_DATA[size]
                ax = axial_increment_from_passes(data.passes)
                tpl_res = template_drill_reserve(
                    data.mill_start_depth, data.drill_depth, ax
                )
                shorter = round(data.thread_length * 0.8, 3)
                if shorter <= 0:
                    continue
                shift = compute_axial_template_shift(
                    requested_thread_depth=shorter,
                    template_thread_depth=data.thread_length,
                    template_mill_start_depth=data.mill_start_depth,
                    template_drill_depth=data.drill_depth,
                    axial_increment=ax,
                )
                self.assertTrue(shift.ok, msg=shift.error)
                self.assertAlmostEqual(shift.drill_reserve, tpl_res, places=6)
                self.assertAlmostEqual(shift.template_drill_reserve, tpl_res, places=6)


class TestIncrementalPathUnchanged(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_m10_template_vs_20(self):
        data = gen.BGF_DATA["M10"]
        tpl = "\n".join(self.app.get_bgf_sequence(data, 8, surface_z=0.0))
        var = "\n".join(
            self.app.get_bgf_sequence(
                data, 8, surface_z=0.0, drill_depth=22.810, mill_start_depth=19.839
            )
        )
        incr = re.compile(r"\b(CC|CP|IPA|IX|IY|IZ|DR-|RR|F\d+)\b")
        self.assertEqual(incr.findall(tpl), incr.findall(var))
        self.assertIn("L Z-27.8700", tpl)
        self.assertIn("L Z-22.8100", var)
        self.assertNotIn("L Z-27.8700", var)

    def test_predrill_not_shifted_m16(self):
        data = gen.BGF_DATA["M16"]
        # template thread 32.96; shorter 25
        shift = compute_axial_template_shift(
            requested_thread_depth=25.0,
            template_thread_depth=data.thread_length,
            template_mill_start_depth=data.mill_start_depth,
            template_drill_depth=data.drill_depth,
            axial_increment=axial_increment_from_passes(data.passes),
        )
        self.assertTrue(shift.ok)
        lines = self.app.get_bgf_sequence(
            data,
            8,
            surface_z=0.0,
            drill_depth=shift.drill_depth,
            mill_start_depth=shift.mill_start_depth,
        )
        text = "\n".join(lines)
        self.assertIn("L Z-2.1000", text)  # predrill unchanged
        self.assertNotIn(f"L Z-{data.drill_depth:.4f}", text)


class TestGuiDepth4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_single_m10_20_clearance_5(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Einzelposition")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set("M10")
        self.app.load_bgf_values()
        self.app.entries["bgf_thread_depth"].delete(0, "end")
        self.app.entries["bgf_thread_depth"].insert(0, "20")
        self.app.entries["approach_clearance"].delete(0, "end")
        self.app.entries["approach_clearance"].insert(0, "5")
        for k, v in (("single_x", "0"), ("single_y", "0"), ("single_surface_z", "0")):
            self.app.entries[k].delete(0, "end")
            self.app.entries[k].insert(0, v)
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("Z+5.0000", code)
        self.assertIn("L Z-22.8100 F1348 M", code)
        self.assertIn("L Z-19.8390 R0 FMAX M", code)
        self.assertIn("CP IPA-360 IZ-1.5000 DR- RR F292 M", code)

    def test_coord_list_mixed_depths(self):
        self.app.mode_var.set("Bohrgewindefraesen (BGF)")
        self.app.on_mode_change(None)
        self.app.position_mode_var.set("Koordinatenliste")
        self.app.on_position_mode_change(None)
        self.app.bgf_size_var.set("M10")
        self.app.load_bgf_values()
        self.app.coord_rows = [
            BGFCoordinatePosition(0, 0, 0, 25.06),
            BGFCoordinatePosition(100, 50, 0, 20.0),
            BGFCoordinatePosition(200, 100, 35, 15.0),
        ]
        self.app.entries["raw_stock_top_z"].delete(0, "end")
        self.app.entries["raw_stock_top_z"].insert(0, "35")
        result = validate_bgf_coordinate_list(
            self.app.coord_rows,
            self.app.get_bgf_depth_policy(),
            safe_z=100,
            end_safe_z=200,
            approach_clearance=1.0,
        )
        self.assertTrue(result.ok_for_nc)
        self.app.generate_bgf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertIn("L Z-27.8700 F1348 M", code)
        self.assertIn("L Z-22.8100 F1348 M", code)
        # depth 15: delta=10.06 → drill=17.810, mill=14.839; surface 35 → Z+17.190 / Z+20.161
        self.assertIn("L Z+17.1900 F1348 M", code)
        self.assertIn("L Z+20.1610 R0 FMAX M", code)


if __name__ == "__main__":
    unittest.main()
