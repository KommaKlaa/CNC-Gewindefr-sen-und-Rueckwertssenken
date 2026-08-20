"""PHASE BSF.UIHELP.5 – freigegebene Referenzgrafik als primaere Hilfe."""
from __future__ import annotations

import unittest
from pathlib import Path

import tkinter as tk

import bsf_generator_verbessert_v3 as gen
from app_paths import resource_path
from help_assets import (
    BSF_GEOMETRY_REFERENCE_REL,
    BSF_HELP_MISSING_TEXT,
    get_bsf_geometry_reference_image_path,
    help_image_scaler_mode,
)
from help_views.bsf_geometry_help import BSFGeometryHelpWindow
from help_views.bsf_geometry_model import build_bsf_geometry_help_snapshot
from heule_bsf_tools import BSF_TOOL_PROFILES
from ui import MODE_BSF
from ui.bsf_help_window import bsf_geometry_reference_resource_path
from ui.bsf_process_animation import PROCESS_STEPS
from ui.bsf_reference_image import BSFReferenceImagePanel

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]


def _snap(**kwargs):
    base = dict(
        entry_text="150",
        exit_text="75",
        target_text="80.5",
        raw_surface_z_text="75",
        x_safety_text="5",
        entry_clearance_text="5",
        overlap_text="0.25",
        tool_designation=TOOL_C.designation,
        safe_z_text="160",
        end_safe_z_text="160",
    )
    base.update(kwargs)
    return build_bsf_geometry_help_snapshot(**base)


class TestReferenceAsset(unittest.TestCase):
    def test_internal_help_asset_exists(self):
        path = bsf_geometry_reference_resource_path()
        self.assertTrue(path.is_file(), path)

    def test_resource_path_resolves_help_asset(self):
        resolved = resource_path(BSF_GEOMETRY_REFERENCE_REL)
        self.assertTrue(resolved.is_file())

    def test_no_confidential_manufacturer_pdf_in_help_assets(self):
        help_dir = resource_path("assets/help")
        if not help_dir.is_dir():
            self.skipTest("assets/help fehlt")
        for path in help_dir.rglob("*"):
            if not path.is_file():
                continue
            self.assertNotIn("manufacturer", str(path).lower())
            self.assertFalse(path.suffix.lower() == ".pdf")


class TestHelpWindowTabs(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = gen.BSFGeneratorGUI(self.root)
        self.app.mode_var.set(MODE_BSF)
        self.app.on_mode_change(None)
        self.app.bsf_tool_profile_var.set(TOOL_C.designation)
        self.app.on_bsf_tool_profile_change()
        self.win = BSFGeometryHelpWindow(self.root, snapshot_provider=self.app.build_bsf_geometry_help_snapshot)
        self.win.win.update_idletasks()

    def tearDown(self):
        self.win.win.destroy()
        self.root.destroy()

    def test_tab_order_and_names(self):
        texts = [self.win.nb.tab(tab_id, "text") for tab_id in self.win.nb.tabs()]
        self.assertEqual(texts[0], "Geometriehilfe")
        self.assertEqual(texts[1], "Aktuelle Werte")
        self.assertEqual(texts[2], "Prozessablauf")
        self.assertEqual(texts[3], "HEULE Original")

    def test_reference_image_visible(self):
        self.assertTrue(self.win._ref_panel.display_size[0] > 200)
        self.assertTrue(self.win._ref_panel.display_size[1] > 200)
        self.assertTrue(self.win._ref_panel.canvas.find_withtag("reference_image"))

    def test_reference_fit_and_zoom(self):
        panel = self.win._ref_panel
        panel.fit_to_window()
        fit_w, _fit_h = panel.display_size
        self.assertGreater(fit_w, 200)
        panel.set_100_percent()
        self.assertAlmostEqual(panel.zoom, 1.0, places=2)
        native_w = panel._native_w
        self.assertEqual(panel.display_size[0], native_w)
        panel.set_zoom(1.5)
        self.assertGreater(panel.display_size[0], native_w)

    def test_aspect_ratio_preserved(self):
        panel = self.win._ref_panel
        ar = panel.aspect_ratio
        w, h = panel.display_size
        if h:
            self.assertAlmostEqual(w / h, ar, delta=0.05)

    def test_current_values_live_snapshot(self):
        for k, v in [
            ("entry_edge_z", "150"),
            ("exit_edge_z", "75"),
            ("target_surface_z", "80.5"),
            ("safe_z", "160"),
        ]:
            if k in self.app.entries:
                self.app.entries[k].delete(0, "end")
                self.app.entries[k].insert(0, v)
        snap = self.app.build_bsf_geometry_help_snapshot()
        self.win.refresh()
        self.win.win.update_idletasks()
        self.assertIsNotNone(snap.a_z)
        self.assertIsNotNone(self.win._display_snapshot)
        self.assertAlmostEqual(self.win._display_snapshot.a_z, snap.a_z, places=3)
        self.assertIsNotNone(self.win._display_snapshot.x_z)

    def test_current_values_axbcd_match_model(self):
        snap = _snap()
        self.win._display_snapshot = snap
        self.win._update_values_panel()
        self.assertAlmostEqual(snap.a_z, 155.0, places=3)
        self.assertAlmostEqual(snap.x_z, 49.75, places=3)

    def test_process_tab_still_nine_steps(self):
        self.assertEqual(len(PROCESS_STEPS), 9)

    def test_missing_internal_asset_clean_message(self):
        panel = BSFReferenceImagePanel(self.root)
        panel.pack()
        self.root.update_idletasks()
        ok = panel.load_from_path(None)
        self.assertFalse(ok)
        self.assertIn("konnte nicht geladen", panel.msg.get())


class TestNcRegression(unittest.TestCase):
    def test_formulas_unchanged(self):
        snap = _snap()
        self.assertAlmostEqual(snap.a_z, 155.0, places=3)
        self.assertAlmostEqual(snap.d_z, 71.95, places=3)


class TestPhaseGate(unittest.TestCase):
    def test_uihelp5_gate(self):
        gate = {
            "REFERENCE_IMAGE_ADDED": bsf_geometry_reference_resource_path().is_file(),
            "HELP_IMAGE_SCALER": help_image_scaler_mode() in {"PIL", "TK_ONLY"},
            "NUITKA_RESOURCE_RESOLUTION": resource_path(BSF_GEOMETRY_REFERENCE_REL).is_file(),
        }
        for key, ok in gate.items():
            with self.subTest(key=key):
                self.assertTrue(ok)
        self.assertTrue(all(gate.values()))


if __name__ == "__main__":
    unittest.main()
