from __future__ import annotations

import unittest

import bsf_generator_verbessert_v3 as gen
from help_views.bsf_geometry_help import BSFGeometryHelpWindow, tool_detail_canvas_layout
from help_views.bsf_geometry_model import build_bsf_geometry_help_snapshot, format_help_info
from heule_bsf_tools import (
    BSF_TOOL_PROFILES,
    MEASUREMENT_LABEL,
    MEASUREMENT_OFFSET_DIRECTION,
    cutting_edge_z_from_measurement_face_z,
    programmed_measurement_face_z_for_cutting_edge,
)
from ui import MODE_BSF

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]
TOOL_E = BSF_TOOL_PROFILES["BSF_E_1350_050_16_5_14"]


class TestBsfHelpModel(unittest.TestCase):
    def test_tool_c_snapshot(self):
        snap = build_bsf_geometry_help_snapshot(
            bund_text="18",
            sink_text="38",
            clearance_text="23",
            z0_label="Z0 ist Unterkante Bund",
            reference_z_text="0",
            tool_designation=TOOL_C.designation,
        )
        self.assertFalse(snap.nc_blocked)
        self.assertEqual(snap.tool_profile.designation, TOOL_C.designation)
        self.assertAlmostEqual(snap.programmed_measurement_face_z_sink_finish, 29.45, places=3)

    def test_tool_e_snapshot(self):
        snap = build_bsf_geometry_help_snapshot(
            bund_text="18",
            sink_text="38",
            clearance_text="23",
            z0_label="Z0 ist Unterkante Bund",
            reference_z_text="0",
            tool_designation=TOOL_E.designation,
        )
        self.assertAlmostEqual(snap.programmed_measurement_face_z_sink_finish, 26.6, places=3)

    def test_measurement_face_offset_tool_c(self):
        measurement_face_z = 29.45
        offset = TOOL_C.measurement_face_to_cutting_edge_mm
        edge = cutting_edge_z_from_measurement_face_z(measurement_face_z, TOOL_C)
        self.assertAlmostEqual(offset, 8.55, places=3)
        self.assertAlmostEqual(edge, 38.0, places=3)
        self.assertAlmostEqual(
            programmed_measurement_face_z_for_cutting_edge(38.0, TOOL_C),
            measurement_face_z,
            places=3,
        )

    def test_measurement_face_offset_tool_e(self):
        measurement_face_z = 26.6
        edge = cutting_edge_z_from_measurement_face_z(measurement_face_z, TOOL_E)
        self.assertAlmostEqual(edge, 38.0, places=3)

    def test_info_text_uses_new_measurement_model(self):
        info = format_help_info(
            build_bsf_geometry_help_snapshot(
                bund_text="18",
                sink_text="38",
                clearance_text="23",
                z0_label="Z0 ist Unterkante Bund",
                reference_z_text="20",
                tool_designation=TOOL_C.designation,
            )
        )
        self.assertIn("HEULE Werkzeug", info)
        self.assertIn("Vermessfläche -> Schneide", info)
        self.assertIn(MEASUREMENT_LABEL, info)
        self.assertIn(MEASUREMENT_OFFSET_DIRECTION, info)
        self.assertIn("Vermesspunkt-Z Finish", info)
        self.assertNotIn("Schwertdicke", info)
        self.assertNotIn("Halter -> Schneide", info)


class TestBsfHelpWindow(unittest.TestCase):
    def test_window_opens_with_new_labels(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.bsf_tool_profile_var.set(TOOL_C.designation)
        app.on_bsf_tool_profile_change()
        win = BSFGeometryHelpWindow(root, snapshot_provider=app.build_bsf_geometry_help_snapshot)
        win.win.update_idletasks()
        text = win.info_dump()
        self.assertIn("Vermessfläche -> Schneide", text)
        self.assertIn("BSF-C-1000/050-10.5-23", text)
        win.win.destroy()
        root.destroy()

    def test_measurement_face_drawn_below_cutting_edge(self):
        y_cut, y_meas = tool_detail_canvas_layout(220.0)
        self.assertGreater(y_meas, y_cut)


if __name__ == "__main__":
    unittest.main()
