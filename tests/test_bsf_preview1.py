"""PHASE BSF.PREVIEW.1 – Positionsvorschau auf direktes Z0-/RawRef-Modell."""

from __future__ import annotations

import unittest

import tkinter as tk

import bsf_generator_verbessert_v3 as gen
from coordinates import BSFCoordinatePosition
from heule_bsf_tools import BSF_TOOL_PROFILES
from preview.bgf_preview_window import BGFPreviewWindow
from ui import MODE_BSF

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]
HS = TOOL_C.measurement_face_to_cutting_edge_mm
AL = float(TOOL_C.deployment_length_al_mm)


def _set(app, key: str, value: str) -> None:
    app.entries[key].delete(0, "end")
    app.entries[key].insert(0, value)


def _setup_rawref_case(app) -> None:
    app.mode_var.set(MODE_BSF)
    app.on_mode_change(None)
    app.bsf_tool_profile_var.set(TOOL_C.designation)
    app.on_bsf_tool_profile_change()
    for key, val in (
        ("entry_edge_z", "105.000"),
        ("exit_edge_z", "80.000"),
        ("raw_surface_z", "75.000"),
        ("target_surface_z", "85.000"),
        ("entry_clearance", "5.000"),
        ("x_safety_clearance", "2.000"),
        ("full_cut_overlap_mm", "0.250"),
        ("safe_z", "115.000"),
        ("end_safe_z", "200.000"),
        ("dwell_time", "1.5"),
        ("spindle_speed", "800"),
        ("feed_rate", "60"),
        ("single_x", "10"),
        ("single_y", "20"),
    ):
        _set(app, key, val)
    if hasattr(app, "bsf_safe_reserve_var"):
        app.bsf_safe_reserve_var.set("5.000")


class TestBsfPreview1Snapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        _setup_rawref_case(self.app)
        self.app.position_mode_var.set("Einzelposition")
        self.app.on_position_mode_change(None)

    def test_preview_values_rawref_case(self):
        snap = self.app.build_bsf_preview_snapshot()
        self.assertTrue(snap.bsf_geometry_complete)
        self.assertAlmostEqual(snap.bsf_entry_edge_z, 105.0, places=3)
        self.assertAlmostEqual(snap.bsf_exit_edge_z, 80.0, places=3)
        self.assertAlmostEqual(snap.bsf_raw_surface_z, 75.0, places=3)
        self.assertAlmostEqual(snap.bsf_target_surface_z, 85.0, places=3)
        self.assertAlmostEqual(snap.bsf_process_surface_z, 75.0, places=3)
        self.assertEqual(snap.bsf_process_surface_source, "RAW_SURFACE")
        self.assertAlmostEqual(snap.bsf_sink_depth, 5.0, places=3)
        self.assertAlmostEqual(snap.bsf_material_removal, 10.0, places=3)
        self.assertAlmostEqual(snap.bsf_a_measurement_face_z, 110.0, places=3)
        self.assertAlmostEqual(snap.bsf_x_measurement_face_z, 52.75, places=3)
        self.assertAlmostEqual(snap.bsf_b_measurement_face_z, 65.45, places=3)
        self.assertAlmostEqual(snap.bsf_c_measurement_face_z, 66.70, places=3)
        self.assertAlmostEqual(snap.bsf_d_measurement_face_z, 76.45, places=3)
        self.assertAlmostEqual(snap.bsf_target_cutting_edge_z, 85.0, places=3)
        self.assertAlmostEqual(snap.bsf_hs_mm, HS, places=3)
        self.assertAlmostEqual(snap.bsf_al_mm, AL, places=3)
        self.assertEqual(snap.bsf_activation_speed_rpm, TOOL_C.activation_speed_rpm)
        self.assertAlmostEqual(snap.bsf_required_safe_z, 110.0, places=3)
        self.assertAlmostEqual(snap.safe_z, 115.0, places=3)
        self.assertAlmostEqual(snap.end_safe_z, 200.0, places=3)
        self.assertEqual(snap.bsf_safe_status, "NC freigegeben")
        self.assertTrue(snap.nc_allowed)

    def test_preview_raw_none_fallback(self):
        _set(self.app, "raw_surface_z", "")
        snap = self.app.build_bsf_preview_snapshot()
        self.assertIsNone(snap.bsf_raw_surface_z)
        self.assertEqual(snap.bsf_process_surface_source, "EXIT_EDGE")
        self.assertAlmostEqual(snap.bsf_process_surface_z, 80.0, places=3)
        self.assertAlmostEqual(snap.bsf_x_measurement_face_z, 57.75, places=3)
        self.assertAlmostEqual(snap.bsf_b_measurement_face_z, 70.45, places=3)
        self.assertAlmostEqual(snap.bsf_c_measurement_face_z, 71.70, places=3)

    def test_incomplete_geometry_no_crash(self):
        _set(self.app, "entry_edge_z", "")
        _set(self.app, "exit_edge_z", "")
        _set(self.app, "target_surface_z", "")
        snap = self.app.build_bsf_preview_snapshot()
        self.assertFalse(snap.bsf_geometry_complete)
        self.assertFalse(snap.nc_allowed)
        self.assertEqual(snap.bsf_safe_status, "NC nicht freigegeben")
        self.assertTrue(any("Eintrittskante" in m for m in snap.bsf_geometry_missing))
        win = BGFPreviewWindow(self.root, snapshot_provider=lambda: snap)
        text = win._format_bsf_point_detail(snap.points[0])
        self.assertIn("BSF-Z-Geometrie unvollstaendig", text)
        self.assertNotIn("Bunddicke", text)
        win.win.destroy()

    def test_no_legacy_fields_in_detail(self):
        snap = self.app.build_bsf_preview_snapshot()
        win = BGFPreviewWindow(self.root, snapshot_provider=lambda: snap)
        text = win._format_bsf_point_detail(snap.points[0])
        for legacy in ("Bunddicke", "Senk-Fertigmaß", "Senk-Fertigmass", "Freifahrtiefe", "Bezug Z"):
            self.assertNotIn(legacy, text)
        self.assertIn("Bohrungs-Eintrittskante", text)
        self.assertIn("Z+105.000", text)
        self.assertIn("Z+80.000", text)
        self.assertIn("Z+75.000", text)
        self.assertIn("Z+85.000", text)
        self.assertIn("Rohflaeche / Ist-Z Z+75.000", text)
        self.assertIn("Z+110.000", text)
        self.assertIn("Z+52.750", text)
        self.assertIn("Z+65.450", text)
        self.assertIn("Z+66.700", text)
        self.assertIn("Z+76.450", text)
        self.assertIn(f"{HS:.3f} mm", text)
        self.assertIn(f"{AL:.3f} mm", text)
        self.assertIn("Mindest-Sicherheits-Z: Z+110.000", text)
        self.assertIn("Sicherheits-Z: Z+115.000", text)
        self.assertIn("End-Sicherheits-Z: Z+200.000", text)
        self.assertIn("Status: NC freigegeben", text)
        win.win.destroy()

    def test_part_circle_preview(self):
        self.app.position_mode_var.set("Teilkreis")
        self.app.on_position_mode_change(None)
        snap = self.app.build_bsf_preview_snapshot()
        self.assertEqual(snap.mode_label, "Teilkreis")
        self.assertGreater(len(snap.points), 1)
        self.assertTrue(snap.bsf_geometry_complete)
        self.assertAlmostEqual(snap.bsf_a_measurement_face_z, 110.0, places=3)

    def test_single_preview(self):
        snap = self.app.build_bsf_preview_snapshot()
        self.assertEqual(snap.mode_label, "Einzelposition")
        self.assertEqual(len(snap.points), 1)
        self.assertAlmostEqual(snap.points[0].x, 10.0, places=3)
        self.assertAlmostEqual(snap.points[0].y, 20.0, places=3)

    def test_coord_list_preview(self):
        self.app.position_mode_var.set("Koordinatenliste")
        self.app.on_position_mode_change(None)
        self.app.bsf_coord_rows = [
            BSFCoordinatePosition(1, 2),
            BSFCoordinatePosition(3, 4),
        ]
        self.app._refresh_bsf_coord_tree()
        snap = self.app.build_bsf_preview_snapshot()
        self.assertEqual(snap.mode_label, "Koordinatenliste")
        self.assertEqual(len(snap.points), 2)
        self.assertTrue(snap.bsf_geometry_complete)
        self.assertAlmostEqual(snap.points[0].x, 1.0, places=3)
        self.assertAlmostEqual(snap.points[1].y, 4.0, places=3)

    def test_nc_output_identical(self):
        before = []
        self.app.generate_bsf_code()
        before.append(self.app.output_text.get("1.0", "end"))
        _ = self.app.build_bsf_preview_snapshot()
        self.app.generate_bsf_code()
        after = self.app.output_text.get("1.0", "end")
        self.assertEqual(before[0], after)

    def test_header_nc_status_from_snapshot(self):
        snap = self.app.build_bsf_preview_snapshot()
        win = BGFPreviewWindow(self.root, snapshot_provider=lambda: snap)
        win.refresh()
        self.assertIn("FREIGEGEBEN", win.header_nc.cget("text"))
        win.win.destroy()

        _set(self.app, "safe_z", "100.000")
        snap2 = self.app.build_bsf_preview_snapshot()
        self.assertFalse(snap2.nc_allowed)
        win2 = BGFPreviewWindow(self.root, snapshot_provider=lambda: snap2)
        win2.refresh()
        self.assertIn("NICHT FREIGEGEBEN", win2.header_nc.cget("text"))
        win2.win.destroy()


class TestBsfPreview1RawDetail(unittest.TestCase):
    def test_raw_none_detail_text(self):
        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        _setup_rawref_case(app)
        _set(app, "raw_surface_z", "")
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        snap = app.build_bsf_preview_snapshot()
        text = BGFPreviewWindow(root, snapshot_provider=lambda: snap)._format_bsf_point_detail(
            snap.points[0]
        )
        self.assertIn("Rohflaeche / Ist-Z:\nnicht angegeben", text)
        self.assertIn("Austrittskante Z+80.000", text)
        root.destroy()


if __name__ == "__main__":
    unittest.main()
