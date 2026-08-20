"""PHASE BSF.Z0.1 – direktes Werkstueck-Z0-Modell."""
from __future__ import annotations

import unittest

import tkinter as tk
import tkinter.messagebox as mb

import bsf_generator_verbessert_v3 as gen
from bsf_workpiece_geometry import (
    Z0_EXAMPLE_BOTTOM,
    Z0_EXAMPLE_REAR,
    Z0_EXAMPLE_TOP,
    build_workpiece_geometry,
    compute_heule_process_positions,
)
from coordinates.bsf_list_document import (
    FORMAT_VERSION,
    build_bsf_document,
    document_to_dict,
    parse_document_dict,
)
from coordinates import BSFCoordinatePosition
from heule_bsf_tools import BSF_TOOL_PROFILES
from ui import MODE_BSF
from help_views.bsf_geometry_model import build_bsf_geometry_help_snapshot, format_help_info

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]
HS = TOOL_C.measurement_face_to_cutting_edge_mm
AL = TOOL_C.deployment_length_al_mm


def _silence_mb():
    orig = mb.showerror
    errors = []
    mb.showerror = lambda *a, **k: errors.append(a)
    return orig, errors


def _restore_mb(orig):
    mb.showerror = orig


def _setup_app(**zfields):
    root = tk.Tk()
    root.withdraw()
    app = gen.BSFGeneratorGUI(root)
    app.mode_var.set(MODE_BSF)
    app.on_mode_change(None)
    app.position_mode_var.set("Einzelposition")
    app.on_position_mode_change(None)
    app.bsf_tool_profile_var.set(TOOL_C.designation)
    app.on_bsf_tool_profile_change()
    params = {
        "safe_z": "100",
        "end_safe_z": "200",
        "spindle_speed": "800",
        "feed_rate": "60",
        "dwell_time": "1.5",
        "single_x": "0",
        "single_y": "0",
        "x_safety_clearance": "2.000",
        "entry_clearance": "1.000",
        "full_cut_overlap_mm": "0.250",
        "entry_edge_z": "20",
        "exit_edge_z": "-5",
        "target_surface_z": "38",
    }
    params.update(zfields)
    for k, v in params.items():
        if k in app.entries:
            app.entries[k].delete(0, "end")
            app.entries[k].insert(0, v)
    return root, app


class TestNoReferencePlane(unittest.TestCase):
    def test_no_bezugsebene_selector(self):
        root, app = _setup_app()
        self.assertFalse(hasattr(app, "z0_var"))
        self.assertNotIn("bsf_reference_z", app.entries)
        self.assertNotIn("sink_depth", app.entries)
        self.assertNotIn("bund_thickness", app.entries)
        root.destroy()

    def test_z0_always_zero(self):
        root, app = _setup_app()
        self.assertEqual(app.bsf_z0_var.get(), "Z0.000")
        root.destroy()


class TestDirectFormulas(unittest.TestCase):
    def test_a_formula(self):
        pos = compute_heule_process_positions(
            entry_edge_z=0, exit_edge_z=-30, target_surface_z=-22,
            measurement_face_to_cutting_edge_mm=HS, deployment_length_al_mm=AL,
            x_safety_clearance_mm=2.0, entry_clearance_mm=1.0,
        )
        self.assertAlmostEqual(pos.a_measurement_face_z, 1.0, places=9)

    def test_x_formula(self):
        pos = compute_heule_process_positions(
            entry_edge_z=0, exit_edge_z=-30, target_surface_z=-22,
            measurement_face_to_cutting_edge_mm=8.55, deployment_length_al_mm=22.5,
            x_safety_clearance_mm=2.0, entry_clearance_mm=1.0,
        )
        self.assertAlmostEqual(pos.x_measurement_face_z, -54.5, places=9)

    def test_b_c_d_formulas(self):
        pos = compute_heule_process_positions(
            entry_edge_z=0, exit_edge_z=-30, target_surface_z=-22,
            measurement_face_to_cutting_edge_mm=HS, deployment_length_al_mm=AL,
            x_safety_clearance_mm=2.0, entry_clearance_mm=1.0, full_cut_overlap_mm=0.25,
        )
        self.assertAlmostEqual(pos.b_measurement_face_z, -30 - HS - 1.0, places=9)
        self.assertAlmostEqual(pos.c_measurement_face_z, -30 - HS + 0.25, places=9)
        self.assertAlmostEqual(pos.d_measurement_face_z, -22 - HS, places=9)

    def test_sink_depth_derived(self):
        geom = build_workpiece_geometry(
            entry_edge_z=0, exit_edge_z=-30, target_surface_z=-22,
            measurement_face_to_cutting_edge_mm=HS,
        )
        self.assertAlmostEqual(geom.sink_depth, 8.0, places=9)

    def test_raw_material_removal(self):
        geom = build_workpiece_geometry(
            entry_edge_z=101, exit_edge_z=75, target_surface_z=80.5,
            measurement_face_to_cutting_edge_mm=HS, raw_surface_z=75.0,
        )
        self.assertAlmostEqual(geom.material_removal, 5.5, places=9)

    def test_negative_removal_blocked(self):
        with self.assertRaises(ValueError):
            build_workpiece_geometry(
                entry_edge_z=0, exit_edge_z=-30, target_surface_z=-22,
                measurement_face_to_cutting_edge_mm=HS, raw_surface_z=-10.0,
            )

    def test_exit_x_al_clearance(self):
        pos = compute_heule_process_positions(
            entry_edge_z=0, exit_edge_z=-30, target_surface_z=-22,
            measurement_face_to_cutting_edge_mm=HS, deployment_length_al_mm=AL,
            x_safety_clearance_mm=2.0, entry_clearance_mm=1.0,
        )
        self.assertGreaterEqual(pos.x_clear_distance, AL + 2.0 - 1e-12)


class TestZ0ExamplesAndTranslation(unittest.TestCase):
    def _pos(self, example):
        return compute_heule_process_positions(
            entry_edge_z=example["entry_edge_z"],
            exit_edge_z=example["exit_edge_z"],
            target_surface_z=example["target_surface_z"],
            measurement_face_to_cutting_edge_mm=HS,
            deployment_length_al_mm=AL,
            x_safety_clearance_mm=2.0,
            entry_clearance_mm=1.0,
        )

    def test_top_and_rear_relative_identical(self):
        a = self._pos(Z0_EXAMPLE_TOP)
        b = self._pos(Z0_EXAMPLE_REAR)
        self.assertAlmostEqual(a.a_measurement_face_z - Z0_EXAMPLE_TOP["entry_edge_z"],
                               b.a_measurement_face_z - Z0_EXAMPLE_REAR["entry_edge_z"], places=9)
        self.assertAlmostEqual(Z0_EXAMPLE_TOP["exit_edge_z"] - a.x_measurement_face_z,
                               Z0_EXAMPLE_REAR["exit_edge_z"] - b.x_measurement_face_z, places=9)
        self.assertAlmostEqual(Z0_EXAMPLE_TOP["target_surface_z"] - Z0_EXAMPLE_TOP["exit_edge_z"],
                               Z0_EXAMPLE_REAR["target_surface_z"] - Z0_EXAMPLE_REAR["exit_edge_z"], places=9)

    def test_bottom_example(self):
        pos = self._pos(Z0_EXAMPLE_BOTTOM)
        self.assertAlmostEqual(pos.a_measurement_face_z, 91.0, places=6)
        self.assertTrue(pos.x_measurement_face_z < pos.b_measurement_face_z < pos.c_measurement_face_z < pos.d_measurement_face_z)

    def test_translation_invariance(self):
        k = 17.5
        base = dict(entry_edge_z=0.0, exit_edge_z=-30.0, target_surface_z=-22.0, raw_surface_z=-24.0)
        p0 = compute_heule_process_positions(
            entry_edge_z=base["entry_edge_z"], exit_edge_z=base["exit_edge_z"],
            target_surface_z=base["target_surface_z"], measurement_face_to_cutting_edge_mm=HS,
            deployment_length_al_mm=AL, x_safety_clearance_mm=2.0, entry_clearance_mm=1.0,
        )
        pk = compute_heule_process_positions(
            entry_edge_z=base["entry_edge_z"] + k, exit_edge_z=base["exit_edge_z"] + k,
            target_surface_z=base["target_surface_z"] + k, measurement_face_to_cutting_edge_mm=HS,
            deployment_length_al_mm=AL, x_safety_clearance_mm=2.0, entry_clearance_mm=1.0,
        )
        self.assertAlmostEqual(pk.a_measurement_face_z, p0.a_measurement_face_z + k, places=9)
        self.assertAlmostEqual(pk.x_measurement_face_z, p0.x_measurement_face_z + k, places=9)
        self.assertAlmostEqual(pk.b_measurement_face_z, p0.b_measurement_face_z + k, places=9)
        self.assertAlmostEqual(pk.c_measurement_face_z, p0.c_measurement_face_z + k, places=9)
        self.assertAlmostEqual(pk.d_measurement_face_z, p0.d_measurement_face_z + k, places=9)
        self.assertAlmostEqual(pk.a_measurement_face_z - (base["entry_edge_z"] + k), 1.0, places=9)
        self.assertAlmostEqual((base["exit_edge_z"] + k) - pk.x_measurement_face_z, AL + 2.0, places=9)


class TestNcDirectAndStale(unittest.TestCase):
    def test_direct_fields_generate_nc(self):
        root, app = _setup_app()
        orig, errors = _silence_mb()
        try:
            app.generate_bsf_code()
        finally:
            _restore_mb(orig)
        code = app.output_text.get("1.0", "end")
        self.assertIn("BEGIN PGM", code)
        self.assertIn("WERKSTUECKNULLPUNKT: Z0 = 0.000", code)
        self.assertNotIn("Bezugsebene", code)
        self.assertNotIn("Z-Lage Bezugsebene", code)
        self.assertEqual(errors, [])
        root.destroy()

    def test_missing_target_blocks_nc(self):
        root, app = _setup_app(target_surface_z="")
        orig, errors = _silence_mb()
        try:
            app.generate_bsf_code()
        finally:
            _restore_mb(orig)
        self.assertEqual(app.output_text.get("1.0", "end").strip(), "")
        self.assertTrue(errors)
        root.destroy()

    def test_stale_each_direct_z_field(self):
        from nc_state import NC_STATE_CURRENT, NC_STATE_STALE
        root, app = _setup_app()
        orig, _ = _silence_mb()
        try:
            app.generate_bsf_code()
        finally:
            _restore_mb(orig)
        code = app.output_text.get("1.0", "end")
        self.assertEqual(app.nc_guard.nc_state(app, output_text=code), NC_STATE_CURRENT)
        for key, val in (
            ("entry_edge_z", "21"),
            ("exit_edge_z", "-4"),
            ("target_surface_z", "39"),
            ("raw_surface_z", "30"),
        ):
            app.entries[key].delete(0, "end")
            app.entries[key].insert(0, val)
            self.assertEqual(app.nc_guard.nc_state(app, output_text=code), NC_STATE_STALE, key)
            app.generate_bsf_code()
            code = app.output_text.get("1.0", "end")
        root.destroy()


class TestJsonV5AndLegacy(unittest.TestCase):
    def _base_kwargs(self, **extra):
        data = dict(
            program_name="TEST", tool_number=8, blank_size=1000.0, blank_height=60.0,
            tool_profile_key="BSF_C_1000_050_10_5_23",
            spindle_speed=800, feed=60.0, dwell_time=1.5,
            reduce_approach=True, approach_feed_factor=0.5,
            activate_preset="IKZ Ein (M7)", activate_custom="",
            deactivate_preset="Alles AUS (M9)", deactivate_custom="",
            safe_z=100.0, end_safe_z=200.0,
            positions=[BSFCoordinatePosition(0.0, 0.0)],
            entry_edge_z=20.0, exit_edge_z=-5.0, target_surface_z=38.0,
        )
        data.update(extra)
        return data

    def test_v5_roundtrip(self):
        self.assertEqual(FORMAT_VERSION, 5)
        doc = build_bsf_document(**self._base_kwargs())
        payload = document_to_dict(doc)
        self.assertEqual(payload["version"], 5)
        self.assertNotIn("reference_z", payload["workpiece"])
        self.assertNotIn("z_reference", payload["workpiece"])
        self.assertNotIn("sink_finish", payload["workpiece"])
        loaded = parse_document_dict(payload)
        self.assertAlmostEqual(loaded.entry_edge_z, 20.0)
        self.assertAlmostEqual(loaded.exit_edge_z, -5.0)
        self.assertAlmostEqual(loaded.target_surface_z, 38.0)
        self.assertTrue(loaded.has_explicit_v5_geometry)

    def test_legacy_versions_load_but_block_nc(self):
        v5 = document_to_dict(build_bsf_document(**self._base_kwargs()))
        for version in (1, 2, 3, 4):
            payload = dict(v5)
            payload["version"] = version
            payload["workpiece"] = dict(v5["workpiece"])
            payload["workpiece"]["z_reference"] = "BOTTOM_EDGE"
            payload["workpiece"]["bund_thickness"] = 18.0
            payload["workpiece"]["sink_finish"] = 38.0
            payload["workpiece"]["clearance"] = 23.0
            payload["workpiece"]["reference_z"] = 0.0
            if version < 2:
                payload.pop("tool", None)
                payload["blade"] = {"thickness": 8.55, "measurement_reference": "spindle_side"}
            doc = parse_document_dict(payload)
            self.assertTrue(doc.legacy_geometry_needs_confirmation, f"v{version}")
            self.assertIsNone(doc.target_surface_z)
            root = tk.Tk()
            root.withdraw()
            app = gen.BSFGeneratorGUI(root)
            app.mode_var.set(MODE_BSF)
            app.on_mode_change(None)
            app.position_mode_var.set("Einzelposition")
            app.on_position_mode_change(None)
            app._apply_bsf_position_list_document(doc)
            self.assertEqual(app.entries["target_surface_z"].get().strip(), "")
            orig, _ = _silence_mb()
            try:
                app.generate_bsf_code()
            finally:
                _restore_mb(orig)
            self.assertEqual(app.output_text.get("1.0", "end").strip(), "", f"v{version} must block NC")
            root.destroy()

    def test_no_silent_rv2_reuse(self):
        # Alte RV2-Zahlen (ref=60, sink=20.5) duerfen nicht still als target=80.5 entstehen.
        v4 = document_to_dict(build_bsf_document(**self._base_kwargs(target_surface_z=None)))
        v4["version"] = 4
        v4["workpiece"]["z_reference"] = "BOTTOM_EDGE"
        v4["workpiece"]["bund_thickness"] = 18
        v4["workpiece"]["sink_finish"] = 20.5
        v4["workpiece"]["clearance"] = 23
        v4["workpiece"]["reference_z"] = 60.0
        v4["workpiece"]["deployment_edge_z"] = 75.0
        v4["workpiece"]["entry_edge_z"] = 101.0
        loaded = parse_document_dict(v4)
        self.assertIsNone(loaded.target_surface_z)
        self.assertNotAlmostEqual(loaded.exit_edge_z or 0, 80.5)


class TestHelpZ0(unittest.TestCase):
    def test_help_three_examples(self):
        snap = build_bsf_geometry_help_snapshot(
            entry_text="0", exit_text="-30", target_text="-22",
            tool_designation=TOOL_C.designation,
        )
        info = format_help_info(snap)
        self.assertIn("Z0 obere Flaeche", info)
        self.assertIn("Z0 hintere / innere Flaeche", info)
        self.assertIn("Z0 untere Flaeche", info)
        self.assertNotIn("Bezugsebene", info)


if __name__ == "__main__":
    unittest.main()
