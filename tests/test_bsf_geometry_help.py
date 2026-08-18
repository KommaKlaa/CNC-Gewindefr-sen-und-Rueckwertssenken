from __future__ import annotations

import unittest

import bsf_generator_verbessert_v3 as gen
from help_views.bsf_geometry_model import build_bsf_geometry_help_snapshot, format_help_info
from heule_bsf_tools import BSF_TOOL_PROFILES
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
        self.assertAlmostEqual(snap.programmed_holder_z_sink_finish, 29.45, places=3)

    def test_tool_e_snapshot(self):
        snap = build_bsf_geometry_help_snapshot(
            bund_text="18",
            sink_text="38",
            clearance_text="23",
            z0_label="Z0 ist Unterkante Bund",
            reference_z_text="0",
            tool_designation=TOOL_E.designation,
        )
        self.assertAlmostEqual(snap.programmed_holder_z_sink_finish, 26.6, places=3)

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
        self.assertIn("Halter -> Schneide", info)
        self.assertNotIn("Schwertdicke", info)


class TestBsfHelpWindow(unittest.TestCase):
    def test_window_opens_with_new_labels(self):
        import tkinter as tk
        from help_views.bsf_geometry_help import BSFGeometryHelpWindow

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
        self.assertIn("Halter -> Schneide", text)
        self.assertIn("BSF-C-1000/050-10.5-23", text)
        win.win.destroy()
        root.destroy()


if __name__ == "__main__":
    unittest.main()
