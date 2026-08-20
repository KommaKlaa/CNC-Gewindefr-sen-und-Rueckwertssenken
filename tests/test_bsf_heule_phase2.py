from __future__ import annotations

import unittest

import bsf_generator_verbessert_v3 as gen
from bsf_workpiece_geometry import build_workpiece_geometry, parse_optional_finite_mm
from coordinates import BSFCoordinatePosition, build_bsf_document
from coordinates.bsf_list_document import FORMAT_VERSION, document_to_dict, parse_document_dict
from help_views.bsf_geometry_help import BSFGeometryHelpWindow
from help_views.bsf_geometry_model import build_bsf_geometry_help_snapshot
from manufacturer_assets import HEULE_ATTRIBUTION_TEXT, HEULE_MISSING_ASSET_TEXT, get_heule_bsf_reference_image_path
from ui import MODE_BSF
from ui.bsf_process_animation import PROCESS_STEPS


class TestBsfWorkpieceGeometry(unittest.TestCase):
    def test_parse_optional_none(self):
        self.assertIsNone(parse_optional_finite_mm(""))

    def test_parse_optional_finite(self):
        self.assertEqual(parse_optional_finite_mm("75.0"), 75.0)

    def test_parse_optional_nan_blocked(self):
        with self.assertRaises(ValueError):
            parse_optional_finite_mm("nan")

    def test_user_example_target_and_removal(self):
        geom = build_workpiece_geometry(
            entry_edge_z=101.0,
            exit_edge_z=75.0,
            target_surface_z=80.5,
            raw_surface_z=75.0,
            measurement_face_to_cutting_edge_mm=8.55,
        )
        self.assertAlmostEqual(geom.target_surface_z, 80.5, places=3)
        self.assertAlmostEqual(geom.material_removal, 5.5, places=3)

    def test_user_example_programmed_measurement_face_bsf_c(self):
        geom = build_workpiece_geometry(
            entry_edge_z=101.0,
            exit_edge_z=75.0,
            target_surface_z=80.5,
            raw_surface_z=75.0,
            measurement_face_to_cutting_edge_mm=8.55,
        )
        self.assertAlmostEqual(geom.programmed_measurement_face_z, 71.95, places=3)

    def test_user_example_programmed_measurement_face_bsf_e(self):
        geom = build_workpiece_geometry(
            entry_edge_z=101.0,
            exit_edge_z=75.0,
            target_surface_z=80.5,
            raw_surface_z=75.0,
            measurement_face_to_cutting_edge_mm=11.4,
        )
        self.assertAlmostEqual(geom.programmed_measurement_face_z, 69.1, places=3)

    def test_negative_material_removal_blocked(self):
        with self.assertRaises(ValueError):
            build_workpiece_geometry(
                entry_edge_z=101.0,
                exit_edge_z=75.0,
                target_surface_z=80.5,
                raw_surface_z=85.0,
                measurement_face_to_cutting_edge_mm=8.55,
            )

    def test_profile_domain_supports_al_and_not_equal_hs(self):
        from heule_bsf_tools import BSF_TOOL_PROFILES

        c = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]
        e = BSF_TOOL_PROFILES["BSF_E_1350_050_16_5_14"]
        self.assertAlmostEqual(c.deployment_length_al_mm, 20.250, places=3)
        self.assertAlmostEqual(e.deployment_length_al_mm, 26.750, places=3)
        self.assertNotEqual(c.deployment_length_al_mm, c.measurement_face_to_cutting_edge_mm)
        self.assertNotEqual(e.deployment_length_al_mm, e.measurement_face_to_cutting_edge_mm)

    def test_x_position_c_synthetic(self):
        from bsf_workpiece_geometry import compute_heule_process_positions

        pos = compute_heule_process_positions(
            exit_edge_z=60.0,
            entry_edge_z=0.0,
            target_surface_z=80.5,
            measurement_face_to_cutting_edge_mm=8.55,
            deployment_length_al_mm=20.250,
            x_safety_clearance_mm=2.0,
            entry_clearance_mm=1.0,
        )
        self.assertAlmostEqual(pos.x_measurement_face_z, 37.750, places=3)

    def test_x_position_e_synthetic(self):
        from bsf_workpiece_geometry import compute_heule_process_positions

        pos = compute_heule_process_positions(
            exit_edge_z=60.0,
            entry_edge_z=0.0,
            target_surface_z=80.5,
            measurement_face_to_cutting_edge_mm=11.4,
            deployment_length_al_mm=26.750,
            x_safety_clearance_mm=2.0,
            entry_clearance_mm=1.0,
        )
        self.assertAlmostEqual(pos.x_measurement_face_z, 31.250, places=3)

    def test_x_has_no_hs_double_offset(self):
        from bsf_workpiece_geometry import compute_heule_process_positions

        pos = compute_heule_process_positions(
            exit_edge_z=60.0,
            entry_edge_z=0.0,
            target_surface_z=80.5,
            measurement_face_to_cutting_edge_mm=8.55,
            deployment_length_al_mm=20.250,
            x_safety_clearance_mm=2.0,
            entry_clearance_mm=1.0,
        )
        self.assertAlmostEqual(pos.x_measurement_face_z, 60.0 - 20.250 - 2.0, places=3)

    def test_heule_golden_example_geometry(self):
        from bsf_workpiece_geometry import compute_heule_process_positions

        # Herstellerbeispiel als Formelregression (Betrag)
        # E=30, AL=22.5, safety=2.0, Hs=9.6, sink=8.0 -> X=54.5, B=40.6, C=39.35, D=31.6
        pos = compute_heule_process_positions(
            exit_edge_z=-30.0,
            entry_edge_z=0.0,
            target_surface_z=-22.0,
            measurement_face_to_cutting_edge_mm=9.6,
            deployment_length_al_mm=22.5,
            x_safety_clearance_mm=2.0,
            entry_clearance_mm=1.0,
            full_cut_overlap_mm=0.25,
        )
        self.assertAlmostEqual(abs(pos.x_measurement_face_z), 54.5, places=3)
        self.assertAlmostEqual(abs(pos.b_measurement_face_z), 40.6, places=3)
        self.assertAlmostEqual(abs(pos.c_measurement_face_z), 39.35, places=3)
        self.assertAlmostEqual(abs(pos.d_measurement_face_z), 31.6, places=3)


class TestBsfDocumentV3(unittest.TestCase):
    def _doc(self, **kwargs):
        base = dict(
            program_name="BSF_TEST",
            tool_number=8,
            blank_size=1000.0,
            blank_height=60.0,
                tool_profile_key="BSF_C_1000_050_10_5_23",
                        spindle_speed=1500,
            feed=120.0,
            dwell_time=1.5,
            reduce_approach=True,
            approach_feed_factor=0.5,
            activate_preset="IKZ Ein (M7)",
            activate_custom="",
            deactivate_preset="Alles AUS (M9)",
            deactivate_custom="",
            safe_z=100.0,
            end_safe_z=200.0,
            positions=[BSFCoordinatePosition(0.0, 0.0)],
            entry_edge_z=20.0,
            exit_edge_z=-5.0,
            target_surface_z=38.0,
        )
        base.update(kwargs)
        return build_bsf_document(**base)

    def test_json_version_3(self):
        self.assertEqual(FORMAT_VERSION, 5)

    def test_roundtrip_raw_surface(self):
        doc = self._doc(raw_surface_z=75.0)
        payload = document_to_dict(doc)
        self.assertEqual(payload["workpiece"]["raw_surface_z"], 75.0)
        parsed = parse_document_dict(payload)
        self.assertEqual(parsed.raw_surface_z, 75.0)

    def test_v2_legacy_defaults_raw_none(self):
        doc = self._doc(raw_surface_z=75.0)
        payload = document_to_dict(doc)
        payload["version"] = 2
        payload["workpiece"] = {
            "z_reference": "BOTTOM_EDGE",
            "reference_z": 0.0,
            "bund_thickness": 18.0,
            "sink_finish": 38.0,
            "clearance": 23.0,
        }
        parsed = parse_document_dict(payload)
        self.assertIsNone(parsed.raw_surface_z)


class TestBsfHelpWindowPhase2(unittest.TestCase):
    def test_asset_missing_no_crash_and_attribution_available(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        win = BSFGeometryHelpWindow(root, snapshot_provider=app.build_bsf_geometry_help_snapshot)
        win.win.update_idletasks()
        self.assertIn("HEULE", HEULE_ATTRIBUTION_TEXT)
        self.assertIsNotNone(win.nb)
        if get_heule_bsf_reference_image_path() is None:
            self.assertIn("nicht installiert", win.orig_msg.get())
            self.assertEqual(HEULE_MISSING_ASSET_TEXT, "Originale HEULE-Herstellerabbildung ist lokal nicht installiert.")
        win.win.destroy()
        root.destroy()

    def test_three_tabs_exist(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        win = BSFGeometryHelpWindow(root, snapshot_provider=app.build_bsf_geometry_help_snapshot)
        win.win.update_idletasks()
        texts = [win.nb.tab(tab_id, "text") for tab_id in win.nb.tabs()]
        self.assertIn("HEULE Original", texts)
        self.assertIn("Eigene Geometrie", texts)
        self.assertIn("Prozessablauf", texts)
        self.assertEqual(len(PROCESS_STEPS), 9)
        win.win.destroy()
        root.destroy()

    def test_snapshot_contains_target_values(self):
        snap = build_bsf_geometry_help_snapshot(
            entry_text="101",
            exit_text="75",
            target_text="80.5",
            raw_surface_z_text="75.0",
            tool_designation="BSF-C-1000/050-10.5-23",
        )
        self.assertAlmostEqual(snap.target_cutting_edge_z, 80.5, places=3)
        self.assertAlmostEqual(snap.material_removal, 5.5, places=3)

    def test_animation_stops_on_close(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        win = BSFGeometryHelpWindow(root, snapshot_provider=app.build_bsf_geometry_help_snapshot)
        win.win.update_idletasks()
        win._animator.toggle_play()
        self.assertTrue(win._animator.playing)
        win._on_close()
        root.destroy()


class TestBsfRawSurfaceStale(unittest.TestCase):
    def test_nc_stale_after_raw_surface_change(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.bsf_tool_profile_var.set("BSF-C-1000/050-10.5-23")
        app.on_bsf_tool_profile_change()
        for key, val in (
            ("single_x", "0"),
            ("single_y", "0"),
            ("safe_z", "100"),
            ("end_safe_z", "200"),
            ("raw_surface_z", "75"),
            ("spindle_speed", "800"),
            ("feed_rate", "60"),
            ("dwell_time", "1.0"),
            ("exit_edge_z", "55"),
            ("entry_edge_z", "80"),
            ("target_surface_z", "98"),
            ("x_safety_clearance", "2.000"),
            ("entry_clearance", "1.000"),
            ("full_cut_overlap_mm", "0.250"),
        ):
            app.entries[key].delete(0, "end")
            app.entries[key].insert(0, val)
        app.generate_bsf_code()
        code = app.output_text.get("1.0", "end").strip()
        self.assertTrue(app.nc_guard.is_current(app, output_text=code))
        app.entries["raw_surface_z"].delete(0, "end")
        app.entries["raw_surface_z"].insert(0, "76")
        self.assertFalse(app.nc_guard.is_current(app, output_text=code))
        root.destroy()


class TestBsfHeuleSequence(unittest.TestCase):
    def test_sequence_order_activation_at_x(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.bsf_tool_profile_var.set("BSF-C-1000/050-10.5-23")
        app.on_bsf_tool_profile_change()
        for key, val in (
            ("bund_thickness", "18"),
            ("sink_depth", "20.5"),
            ("clearance", "23"),
            ("single_x", "0"),
            ("single_y", "0"),
            ("safe_z", "100"),
            ("end_safe_z", "200"),
            
            ("raw_surface_z", "75"),
            ("exit_edge_z", "60"), ("target_surface_z", "80.5"),
            ("x_safety_clearance", "2.0"),
            ("entry_edge_z", "0"),
            ("entry_clearance", "1.0"),
            ("spindle_speed", "800"),
            ("feed_rate", "60"),
            ("dwell_time", "1.0"),
        ):
            if key not in app.entries:
                continue
            app.entries[key].delete(0, "end")
            app.entries[key].insert(0, val)
        app.generate_bsf_code()
        code = app.output_text.get("1.0", "end")
        self.assertIn("X hinter Bohrung (AL+Sicherheit)", code)
        self.assertNotIn("Z+61.0000", code)  # reference_z+1 Aktivierung entfernt
        self.assertIn("Spindel einschalten an X", code)
        self.assertIn("M5 ; Spindel aus", code)
        self.assertIn("Druck/IK ein - Messer eingefahren", code)
        self.assertIn("Druck/IK aus - Messer zum Ausklappen freigegeben", code)
        self.assertIn("Zurueck nach X", code)
        root.destroy()

