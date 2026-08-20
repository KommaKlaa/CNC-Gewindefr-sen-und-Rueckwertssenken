"""PHASE BSF.TERMS.2 – sichtbarer Abstand vor Senkflaeche (b_clearance)."""

from __future__ import annotations

import unittest
from unittest import mock

import tkinter as tk

import bsf_generator_verbessert_v3 as gen
from bsf_chain import BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE, bsf_end_mode_label
from bsf_workpiece_geometry import compute_heule_process_positions
from coordinates.bsf_list_document import (
    build_bsf_document,
    document_to_dict,
    parse_document_dict,
)
from coordinates import BSFCoordinatePosition
from heule_bsf_tools import BSF_TOOL_PROFILES
from nc_state import NC_STATE_CURRENT, NC_STATE_STALE
from preview.bgf_preview_window import BGFPreviewWindow
from ui import MODE_BSF

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]
HS = TOOL_C.measurement_face_to_cutting_edge_mm
AL = float(TOOL_C.deployment_length_al_mm)


def _set(app, key: str, value: str) -> None:
    app.entries[key].delete(0, "end")
    app.entries[key].insert(0, value)


def _setup_ref(app, *, b_clearance: str = "1.000", raw: str = "75.000") -> None:
    app.mode_var.set(MODE_BSF)
    app.on_mode_change(None)
    app.bsf_tool_profile_var.set(TOOL_C.designation)
    app.on_bsf_tool_profile_change()
    app.position_mode_var.set("Einzelposition")
    app.on_position_mode_change(None)
    for key, val in (
        ("entry_edge_z", "105.000"),
        ("exit_edge_z", "80.000"),
        ("raw_surface_z", raw),
        ("target_surface_z", "85.000"),
        ("entry_clearance", "5.000"),
        ("x_safety_clearance", "2.000"),
        ("b_clearance", b_clearance),
        ("full_cut_overlap_mm", "0.250"),
        ("safe_z", "115.000"),
        ("end_safe_z", "200.000"),
        ("dwell_time", "1.5"),
        ("spindle_speed", "800"),
        ("feed_rate", "60"),
        ("single_x", "0"),
        ("single_y", "0"),
    ):
        _set(app, key, val)


class TestBsfTerms2VisibleClearance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_default_visible(self):
        self.assertIn("b_clearance", self.app.entries)
        self.assertEqual(self.app.entries["b_clearance"].get(), "1.000")

    def test_default_geometry_b(self):
        _setup_ref(self.app, b_clearance="1.000")
        self.app.refresh_bsf_geometry_summary()
        self.assertEqual(self.app.bsf_position_a_var.get(), "Z+110.000")
        self.assertEqual(self.app.bsf_position_x_var.get(), "Z+52.750")
        self.assertEqual(self.app.bsf_position_b_var.get(), "Z+65.450")
        self.assertEqual(self.app.bsf_position_c_var.get(), "Z+66.700")
        self.assertEqual(self.app.bsf_position_d_var.get(), "Z+76.450")

    def test_custom_2mm_only_changes_b(self):
        _setup_ref(self.app, b_clearance="2.000")
        self.app.refresh_bsf_geometry_summary()
        self.assertEqual(self.app.bsf_position_a_var.get(), "Z+110.000")
        self.assertEqual(self.app.bsf_position_x_var.get(), "Z+52.750")
        self.assertEqual(self.app.bsf_position_b_var.get(), "Z+64.450")
        self.assertEqual(self.app.bsf_position_c_var.get(), "Z+66.700")
        self.assertEqual(self.app.bsf_position_d_var.get(), "Z+76.450")

    def test_zero_allowed(self):
        pos = compute_heule_process_positions(
            entry_edge_z=105.0,
            exit_edge_z=80.0,
            target_surface_z=85.0,
            raw_surface_z=75.0,
            measurement_face_to_cutting_edge_mm=HS,
            deployment_length_al_mm=AL,
            x_safety_clearance_mm=2.0,
            entry_clearance_mm=5.0,
            b_clearance_mm=0.0,
            full_cut_overlap_mm=0.25,
        )
        self.assertAlmostEqual(pos.b_measurement_face_z, 66.45, places=3)

    def test_negative_blocked_model(self):
        with self.assertRaises(ValueError):
            compute_heule_process_positions(
                entry_edge_z=105.0,
                exit_edge_z=80.0,
                target_surface_z=85.0,
                raw_surface_z=75.0,
                measurement_face_to_cutting_edge_mm=HS,
                deployment_length_al_mm=AL,
                x_safety_clearance_mm=2.0,
                entry_clearance_mm=5.0,
                b_clearance_mm=-1.0,
                full_cut_overlap_mm=0.25,
            )

    def test_nan_inf_blocked_nc(self):
        _setup_ref(self.app)
        with mock.patch("tkinter.messagebox.showerror"):
            for bad in ("NaN", "Inf", "-Inf", "abc"):
                _setup_ref(self.app, b_clearance="1.000")
                self.app.generate_bsf_code()
                self.assertTrue(self.app.output_text.get("1.0", "end").strip().startswith("BEGIN PGM"))
                _set(self.app, "b_clearance", bad)
                self.app.generate_bsf_code()
                # fail-closed: nach ungueltigem Wert keine erfolgreiche Neu-Generierung
                # (STALE bleibt / Code nicht neu mit BEGIN aus dem Fehlversuch)
                snap = self.app.build_bsf_preview_snapshot()
                self.assertFalse(snap.bsf_geometry_complete)

    def test_negative_blocked_nc(self):
        _setup_ref(self.app, b_clearance="-0.1")
        with mock.patch("tkinter.messagebox.showerror") as err:
            self.app.generate_bsf_code()
            err.assert_called()
        code = self.app.output_text.get("1.0", "end")
        # vorheriger Code darf nicht durch negativen Wert neu geschrieben werden
        self.assertNotIn("L Z+64.4500", code)

    def test_stale_on_change(self):
        _setup_ref(self.app, b_clearance="1.000")
        self.app.generate_bsf_code()
        code = self.app.output_text.get("1.0", "end")
        self.assertEqual(self.app.nc_guard.nc_state(self.app, output_text=code), NC_STATE_CURRENT)
        _set(self.app, "b_clearance", "2.000")
        self.assertEqual(self.app.nc_guard.nc_state(self.app, output_text=code), NC_STATE_STALE)

    def test_preview_custom(self):
        _setup_ref(self.app, b_clearance="2.000")
        snap = self.app.build_bsf_preview_snapshot()
        self.assertAlmostEqual(snap.bsf_b_measurement_face_z, 64.45, places=3)
        self.assertAlmostEqual(snap.bsf_a_measurement_face_z, 110.0, places=3)
        win = BGFPreviewWindow(self.root, snapshot_provider=lambda: snap)
        text = win._format_bsf_point_detail(snap.points[0])
        self.assertIn("Z+64.450", text)
        self.assertIn("Anfahrposition vor Senkflaeche", text)
        win.win.destroy()

    def test_raw_none_b(self):
        _setup_ref(self.app, b_clearance="1.000", raw="")
        self.app.refresh_bsf_geometry_summary()
        self.assertEqual(self.app.bsf_position_b_var.get(), "Z+70.450")

    def test_snapshot_roundtrip(self):
        _setup_ref(self.app, b_clearance="1.234")
        snap = self.app._snapshot_bsf_project()
        _set(self.app, "b_clearance", "9.999")
        self.app._restore_bsf_project(snap)
        self.assertEqual(self.app.entries["b_clearance"].get(), "1.234")

    def test_json_roundtrip(self):
        doc = build_bsf_document(
            program_name="BSF_T2",
            tool_number=8,
            blank_size=1000.0,
            blank_height=60.0,
            spindle_speed=800,
            feed=60.0,
            dwell_time=1.5,
            reduce_approach=True,
            approach_feed_factor=0.5,
            activate_preset="IKZ Ein (M7)",
            activate_custom="",
            deactivate_preset="Alles AUS (M9)",
            deactivate_custom="",
            safe_z=115.0,
            end_safe_z=200.0,
            positions=[BSFCoordinatePosition(0, 0)],
            tool_profile_key=TOOL_C.key,
            entry_edge_z=105.0,
            exit_edge_z=80.0,
            target_surface_z=85.0,
            raw_surface_z=75.0,
            x_safety_clearance=2.0,
            entry_clearance=5.0,
            full_cut_overlap_mm=0.25,
            b_clearance=1.234,
        )
        payload = document_to_dict(doc)
        self.assertAlmostEqual(payload["workpiece"]["b_clearance"], 1.234, places=6)
        loaded = parse_document_dict(payload)
        self.assertAlmostEqual(loaded.b_clearance, 1.234, places=6)

    def test_legacy_without_field_defaults(self):
        doc = build_bsf_document(
            program_name="BSF_LEG",
            tool_number=8,
            blank_size=1000.0,
            blank_height=60.0,
            spindle_speed=800,
            feed=60.0,
            dwell_time=1.5,
            reduce_approach=True,
            approach_feed_factor=0.5,
            activate_preset="IKZ Ein (M7)",
            activate_custom="",
            deactivate_preset="Alles AUS (M9)",
            deactivate_custom="",
            safe_z=115.0,
            end_safe_z=200.0,
            positions=[BSFCoordinatePosition(0, 0)],
            tool_profile_key=TOOL_C.key,
            entry_edge_z=105.0,
            exit_edge_z=80.0,
            target_surface_z=85.0,
        )
        payload = document_to_dict(doc)
        del payload["workpiece"]["b_clearance"]
        loaded = parse_document_dict(payload)
        self.assertAlmostEqual(loaded.b_clearance, 1.0, places=6)

    def test_chain_standalone_same_b_motion(self):
        _setup_ref(self.app, b_clearance="2.000")
        self.app.bsf_end_mode_var.set(bsf_end_mode_label(BSF_END_MODE_CHAIN))
        self.app.generate_bsf_code()
        chain = self.app.output_text.get("1.0", "end")
        self.app.bsf_end_mode_var.set(bsf_end_mode_label(BSF_END_MODE_STANDALONE))
        self.app.generate_bsf_code()
        standalone = self.app.output_text.get("1.0", "end")
        self.assertIn("Z+64.4500", chain)
        self.assertIn("Z+64.4500", standalone)
        self.assertIn("Z+110.0000", chain)
        self.assertIn("Z+52.7500", chain)
        # Endmodus-Unterschied bleibt
        self.assertNotEqual(chain, standalone)

    def test_nc_default_output_identical(self):
        _setup_ref(self.app, b_clearance="1.000")
        self.app.generate_bsf_code()
        with_default = self.app.output_text.get("1.0", "end")
        # explizit Default gesetzt vs. Domain-Default: gleiche B-Lage
        self.assertIn("Z+65.4500", with_default)
        self.assertIn("Z+110.0000", with_default)
        self.assertIn("Z+52.7500", with_default)
        self.assertIn("Z+66.7000", with_default)
        self.assertIn("Z+76.4500", with_default)


if __name__ == "__main__":
    unittest.main()
