"""PHASE BSF.RAWREF.1 – Rohflaeche als Prozesskontur fuer X/B/C."""
from __future__ import annotations

import unittest
from unittest import mock

import tkinter as tk

import bsf_generator_verbessert_v3 as gen
from bsf_chain import BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE, bsf_end_mode_label
from bsf_workpiece_geometry import (
    PROCESS_SURFACE_EXIT,
    PROCESS_SURFACE_RAW,
    build_workpiece_geometry,
    compute_heule_process_positions,
    resolve_process_surface_z,
)
from heule_bsf_tools import BSF_TOOL_PROFILES
from ui import MODE_BSF

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]
HS = TOOL_C.measurement_face_to_cutting_edge_mm
AL = float(TOOL_C.deployment_length_al_mm)


class TestProcessSurfaceResolution(unittest.TestCase):
    def test_raw_none_uses_exit(self):
        z, src = resolve_process_surface_z(exit_edge_z=80.0, raw_surface_z=None)
        self.assertAlmostEqual(z, 80.0, places=3)
        self.assertEqual(src, PROCESS_SURFACE_EXIT)

    def test_raw_present_uses_raw(self):
        z, src = resolve_process_surface_z(exit_edge_z=80.0, raw_surface_z=75.0)
        self.assertAlmostEqual(z, 75.0, places=3)
        self.assertEqual(src, PROCESS_SURFACE_RAW)


class TestUserCaseRawref(unittest.TestCase):
    def test_positions_with_raw(self):
        geom = build_workpiece_geometry(
            entry_edge_z=105.0,
            exit_edge_z=80.0,
            target_surface_z=85.0,
            raw_surface_z=75.0,
            measurement_face_to_cutting_edge_mm=HS,
        )
        pos = compute_heule_process_positions(
            entry_edge_z=105.0,
            exit_edge_z=80.0,
            target_surface_z=85.0,
            raw_surface_z=75.0,
            measurement_face_to_cutting_edge_mm=HS,
            deployment_length_al_mm=AL,
            x_safety_clearance_mm=2.0,
            entry_clearance_mm=5.0,
            b_clearance_mm=1.0,
            full_cut_overlap_mm=0.25,
        )
        self.assertAlmostEqual(pos.a_measurement_face_z, 110.0, places=3)
        self.assertAlmostEqual(pos.x_measurement_face_z, 52.75, places=3)
        self.assertAlmostEqual(pos.b_measurement_face_z, 65.45, places=3)
        self.assertAlmostEqual(pos.c_measurement_face_z, 66.70, places=3)
        self.assertAlmostEqual(pos.d_measurement_face_z, 76.45, places=3)
        self.assertAlmostEqual(pos.x_clear_distance, 22.25, places=3)
        self.assertAlmostEqual(pos.process_surface_z, 75.0, places=3)
        self.assertEqual(pos.process_surface_source, PROCESS_SURFACE_RAW)
        self.assertAlmostEqual(geom.material_removal, 10.0, places=3)
        self.assertAlmostEqual(geom.sink_depth, 5.0, places=3)
        self.assertTrue(
            pos.x_measurement_face_z
            < pos.b_measurement_face_z
            < pos.c_measurement_face_z
            < pos.d_measurement_face_z
            < pos.a_measurement_face_z
        )

    def test_positions_without_raw(self):
        pos = compute_heule_process_positions(
            entry_edge_z=105.0,
            exit_edge_z=80.0,
            target_surface_z=85.0,
            raw_surface_z=None,
            measurement_face_to_cutting_edge_mm=HS,
            deployment_length_al_mm=AL,
            x_safety_clearance_mm=2.0,
            entry_clearance_mm=5.0,
            b_clearance_mm=1.0,
            full_cut_overlap_mm=0.25,
        )
        self.assertAlmostEqual(pos.x_measurement_face_z, 57.75, places=3)
        self.assertAlmostEqual(pos.b_measurement_face_z, 70.45, places=3)
        self.assertAlmostEqual(pos.c_measurement_face_z, 71.70, places=3)
        self.assertAlmostEqual(pos.d_measurement_face_z, 76.45, places=3)
        self.assertAlmostEqual(pos.a_measurement_face_z, 110.0, places=3)
        self.assertEqual(pos.process_surface_source, PROCESS_SURFACE_EXIT)


class TestNoRawRegression(unittest.TestCase):
    def test_legacy_exit_based_values_unchanged(self):
        # Vorheriger Standardfall: exit=75, kein raw → X=49.75 bei safety=5
        pos = compute_heule_process_positions(
            entry_edge_z=150.0,
            exit_edge_z=75.0,
            target_surface_z=80.5,
            measurement_face_to_cutting_edge_mm=HS,
            deployment_length_al_mm=AL,
            x_safety_clearance_mm=5.0,
            entry_clearance_mm=5.0,
            full_cut_overlap_mm=0.25,
        )
        self.assertAlmostEqual(pos.a_measurement_face_z, 155.0, places=3)
        self.assertAlmostEqual(pos.x_measurement_face_z, 49.75, places=3)
        self.assertAlmostEqual(pos.b_measurement_face_z, 65.45, places=3)
        self.assertAlmostEqual(pos.c_measurement_face_z, 66.70, places=3)
        self.assertAlmostEqual(pos.d_measurement_face_z, 71.95, places=3)


def _setup_app(**fields):
    root = tk.Tk()
    root.withdraw()
    app = gen.BSFGeneratorGUI(root)
    app.mode_var.set(MODE_BSF)
    app.on_mode_change(None)
    app.position_mode_var.set("Einzelposition")
    app.on_position_mode_change(None)
    app.bsf_tool_profile_var.set(TOOL_C.designation)
    app.on_bsf_tool_profile_change()
    defaults = {
        "entry_edge_z": "105",
        "exit_edge_z": "80",
        "target_surface_z": "85",
        "raw_surface_z": "75",
        "x_safety_clearance": "2.000",
        "entry_clearance": "5.000",
        "full_cut_overlap_mm": "0.250",
        "safe_z": "160",
        "end_safe_z": "200",
        "spindle_speed": "800",
        "feed_rate": "60",
        "dwell_time": "1.0",
        "single_x": "0",
        "single_y": "0",
    }
    defaults.update(fields)
    for k, v in defaults.items():
        if k in app.entries:
            app.entries[k].delete(0, "end")
            app.entries[k].insert(0, v)
    return root, app


class TestRawrefGuiAndNc(unittest.TestCase):
    def test_ui_shows_raw_reference(self):
        root, app = _setup_app()
        app.refresh_bsf_geometry_summary()
        text = app.bsf_process_surface_var.get()
        self.assertIn("Rohflaeche", text)
        self.assertIn("75.000", text)
        self.assertIn("52.750", app.bsf_position_x_var.get())
        root.destroy()

    def test_ui_shows_exit_when_raw_empty(self):
        root, app = _setup_app(raw_surface_z="")
        app.refresh_bsf_geometry_summary()
        text = app.bsf_process_surface_var.get()
        self.assertIn("Austrittskante", text)
        self.assertIn("80.000", text)
        self.assertIn("57.750", app.bsf_position_x_var.get())
        root.destroy()

    def test_raw_change_stale(self):
        root, app = _setup_app()
        with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror"):
            app.generate_bsf_code()
        code = app.output_text.get("1.0", "end")
        self.assertIn("L Z+52.7500", code)
        self.assertTrue(app.nc_guard.is_current(app, output_text=code))
        app.entries["raw_surface_z"].delete(0, "end")
        app.entries["raw_surface_z"].insert(0, "76")
        self.assertFalse(app.nc_guard.is_current(app, output_text=code))
        root.destroy()

    def test_chain_and_standalone_contain_raw_x(self):
        for mode in (BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE):
            root, app = _setup_app()
            app.bsf_end_mode_var.set(bsf_end_mode_label(mode))
            with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror"):
                app.generate_bsf_code()
            code = app.output_text.get("1.0", "end")
            self.assertIn("L Z+52.7500", code)
            self.assertIn("L Z+65.4500", code)
            self.assertIn("L Z+66.7000", code)
            self.assertIn("L Z+76.4500", code)
            self.assertIn("L Z+110.0000", code)
            root.destroy()


if __name__ == "__main__":
    unittest.main()
