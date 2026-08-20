"""PHASE BSF.UIHELP.2 – Safe-Z Live-UX (grafische Hilfe entfernt in UIHELP.REMOVE.1)."""
from __future__ import annotations

import unittest
from unittest import mock

import tkinter as tk

import bsf_generator_verbessert_v3 as gen
from bsf_workpiece_geometry import (
    compute_heule_process_positions,
    required_bsf_safe_z,
    validate_bsf_safe_z_direct,
)
from heule_bsf_tools import BSF_TOOL_PROFILES
from ui import MODE_BSF
from ui.bsf_safe_status import (
    STATUS_INCOMPLETE,
    STATUS_OK,
    STATUS_TOO_LOW,
    apply_minimum_plus_reserve,
    evaluate_bsf_safe_z_status,
)

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]
HS = TOOL_C.measurement_face_to_cutting_edge_mm
AL = TOOL_C.deployment_length_al_mm


def _user_case_pos():
    return compute_heule_process_positions(
        entry_edge_z=150.0,
        exit_edge_z=75.0,
        target_surface_z=80.5,
        measurement_face_to_cutting_edge_mm=HS,
        deployment_length_al_mm=AL,
        x_safety_clearance_mm=5.0,
        entry_clearance_mm=5.0,
        full_cut_overlap_mm=0.25,
    )


def _setup_user_case(safe_z="100", end_safe_z="200"):
    root = tk.Tk()
    root.withdraw()
    app = gen.BSFGeneratorGUI(root)
    app.mode_var.set(MODE_BSF)
    app.on_mode_change(None)
    app.position_mode_var.set("Einzelposition")
    app.on_position_mode_change(None)
    app.bsf_tool_profile_var.set(TOOL_C.designation)
    app.on_bsf_tool_profile_change()
    for k, v in {
        "entry_edge_z": "150",
        "exit_edge_z": "75",
        "target_surface_z": "80.5",
        "raw_surface_z": "75",
        "x_safety_clearance": "5.000",
        "entry_clearance": "5.000",
        "full_cut_overlap_mm": "0.250",
        "safe_z": safe_z,
        "end_safe_z": end_safe_z,
        "spindle_speed": "800",
        "feed_rate": "60",
        "dwell_time": "1.5",
        "single_x": "0",
        "single_y": "0",
    }.items():
        if k in app.entries:
            app.entries[k].delete(0, "end")
            app.entries[k].insert(0, v)
    app.refresh_bsf_geometry_summary()
    return root, app


class TestRequiredSafeZHelper(unittest.TestCase):
    def test_required_is_max_positions(self):
        pos = _user_case_pos()
        req = required_bsf_safe_z(pos)
        self.assertAlmostEqual(req, 155.0, places=3)
        self.assertAlmostEqual(req, pos.a_measurement_face_z, places=3)

    def test_validate_uses_helper(self):
        pos = _user_case_pos()
        self.assertIsNotNone(validate_bsf_safe_z_direct(100.0, 200.0, pos))
        self.assertIsNone(validate_bsf_safe_z_direct(160.0, 200.0, pos))


class TestSafeZStatus(unittest.TestCase):
    def test_too_low_and_ok(self):
        pos = _user_case_pos()
        low = evaluate_bsf_safe_z_status(heule_pos=pos, safe_z=100.0, end_safe_z=200.0)
        self.assertEqual(low.status, STATUS_TOO_LOW)
        self.assertAlmostEqual(low.deficit_mm, 55.0, places=3)
        ok = evaluate_bsf_safe_z_status(heule_pos=pos, safe_z=160.0, end_safe_z=200.0)
        self.assertEqual(ok.status, STATUS_OK)

    def test_end_safe_too_low(self):
        pos = _user_case_pos()
        st = evaluate_bsf_safe_z_status(heule_pos=pos, safe_z=200.0, end_safe_z=100.0)
        self.assertEqual(st.status, STATUS_TOO_LOW)

    def test_incomplete(self):
        st = evaluate_bsf_safe_z_status(heule_pos=None, safe_z=100.0, end_safe_z=200.0)
        self.assertEqual(st.status, STATUS_INCOMPLETE)

    def test_reserve_button_math(self):
        safe, end = apply_minimum_plus_reserve(
            required_safe_z=155.0, reserve_mm=5.0, current_end_safe_z=120.0
        )
        self.assertAlmostEqual(safe, 160.0, places=3)
        self.assertAlmostEqual(end, 160.0, places=3)


class TestSafeZLiveGui(unittest.TestCase):
    def test_live_status_user_case(self):
        root, app = _setup_user_case("100")
        self.assertIn("155", app.bsf_required_safe_z_var.get())
        self.assertIn("niedrig", app.bsf_safe_status_var.get().lower())
        app.entries["safe_z"].delete(0, "end")
        app.entries["safe_z"].insert(0, "160")
        app.refresh_bsf_geometry_summary()
        self.assertIn("ausreichend", app.bsf_safe_status_var.get().lower())
        root.destroy()

    def test_reserve_button_sets_values(self):
        root, app = _setup_user_case("100")
        app.bsf_safe_reserve_var.set("5.000")
        app.apply_bsf_safe_z_minimum_plus_reserve()
        self.assertAlmostEqual(float(app.entries["safe_z"].get()), 160.0, places=3)
        self.assertGreaterEqual(float(app.entries["end_safe_z"].get()), 160.0)
        self.assertIn("ausreichend", app.bsf_safe_status_var.get().lower())
        root.destroy()

    def test_no_popup_on_typing(self):
        root, app = _setup_user_case("100")
        calls = []
        with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror", side_effect=lambda *a, **k: calls.append(a)):
            app.entries["entry_edge_z"].delete(0, "end")
            app.entries["entry_edge_z"].insert(0, "151")
            app.refresh_bsf_geometry_summary()
        self.assertEqual(calls, [])
        root.destroy()

    def test_generate_fail_closed(self):
        root, app = _setup_user_case("100")
        errors = []
        with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror", side_effect=lambda *a, **k: errors.append(a)):
            app.generate_bsf_code()
        self.assertTrue(errors)
        blob = " ".join(str(x) for x in errors)
        self.assertIn("155", blob)
        self.assertIn("100", blob)
        root.destroy()


class TestNcRegressionUihelp(unittest.TestCase):
    def test_nc_motion_unchanged_for_valid_inputs(self):
        root, app = _setup_user_case("160", "200")
        with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror"):
            app.generate_bsf_code()
        code1 = app.output_text.get("1.0", "end")
        with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror"):
            app.generate_bsf_code()
        code2 = app.output_text.get("1.0", "end")
        self.assertEqual(code1, code2)
        self.assertIn("L Z+155.0000", code1)  # A
        self.assertIn("L Z+49.7500", code1)  # X
        self.assertIn("L Z+71.9500", code1)  # D
        root.destroy()


if __name__ == "__main__":
    unittest.main()
