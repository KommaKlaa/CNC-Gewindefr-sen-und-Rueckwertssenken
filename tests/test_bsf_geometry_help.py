"""PHASE UI.HELP.1 / 1A – HEULE-BSF-Senkgeometrie-Hilfsgrafik."""

from __future__ import annotations

import unittest

from bsf_blade import (
    FINISH_EDGE,
    MEASUREMENT_LABELS,
    BladeMeasurementReference,
    apply_blade_offset,
    blade_reference_offset,
    calculate_workpiece_bsf_z,
)
from help_views.bsf_geometry_layout import compute_bsf_help_layout
from help_views.bsf_geometry_model import (
    build_bsf_geometry_help_snapshot,
    format_help_info,
    status_headline,
)
import bsf_generator_verbessert_v3 as gen
from ui import MODE_BGF, MODE_BSF
from ui.visibility import is_mapped

SPINDLE_LABEL = MEASUREMENT_LABELS[BladeMeasurementReference.SPINDLE_SIDE_EDGE]
TIP_LABEL = MEASUREMENT_LABELS[BladeMeasurementReference.TOOL_TIP_SIDE_EDGE]


def _snap(**overrides):
    kwargs = dict(
        bund_text="18",
        sink_text="38",
        clearance_text="23",
        blade_text="3",
        measurement_label=SPINDLE_LABEL,
        z0_label="Z0 ist Unterkante Bund",
    )
    kwargs.update(overrides)
    return build_bsf_geometry_help_snapshot(**kwargs)


def _canvas_text(canvas) -> str:
    parts = []
    for item in canvas.find_all():
        if canvas.type(item) == "text":
            parts.append(canvas.itemcget(item, "text"))
    return "\n".join(parts)


class TestBsfHelpModel(unittest.TestCase):
    def test_z0_bottom_uses_domain_values(self):
        snap = _snap()
        wp = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=True)
        offset = blade_reference_offset(3.0, BladeMeasurementReference.SPINDLE_SIDE_EDGE)
        programmed = apply_blade_offset(wp, offset)
        self.assertTrue(snap.z0_is_flange_bottom)
        self.assertEqual(snap.workpiece_z_sink_finish, wp["z_sink_finish"])
        self.assertEqual(snap.workpiece_z_clearance, wp["z_clearance"])
        self.assertEqual(snap.programmed_z_sink_finish, programmed["z_sink_finish"])
        self.assertEqual(snap.programmed_z_clearance, programmed["z_clearance"])
        self.assertEqual(snap.workpiece_z_sink_finish, 38.0)
        self.assertEqual(snap.workpiece_z_clearance, -23.0)
        self.assertFalse(snap.nc_blocked)
        self.assertIs(snap.finish_edge, FINISH_EDGE)

    def test_z0_top_uses_domain_values(self):
        snap = _snap(z0_label="Z0 ist Oberkante Bund")
        wp = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=False)
        self.assertFalse(snap.z0_is_flange_bottom)
        self.assertEqual(snap.workpiece_z_sink_finish, wp["z_sink_finish"])
        self.assertEqual(snap.workpiece_z_clearance, wp["z_clearance"])
        self.assertEqual(snap.workpiece_z_clearance, -41.0)
        self.assertEqual(snap.workpiece_z_sink_finish, 20.0)

    def test_measurement_refs(self):
        spindle = _snap(measurement_label=SPINDLE_LABEL)
        tip = _snap(measurement_label=TIP_LABEL)
        self.assertEqual(spindle.measurement_reference, BladeMeasurementReference.SPINDLE_SIDE_EDGE)
        self.assertEqual(tip.measurement_reference, BladeMeasurementReference.TOOL_TIP_SIDE_EDGE)
        self.assertAlmostEqual(spindle.programmed_z_sink_finish - tip.programmed_z_sink_finish, 3.0)
        wp = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=True)
        off_tip = blade_reference_offset(3.0, BladeMeasurementReference.TOOL_TIP_SIDE_EDGE)
        programmed = apply_blade_offset(wp, off_tip)
        self.assertEqual(tip.programmed_z_sink_finish, programmed["z_sink_finish"])
        self.assertEqual(tip.programmed_z_clearance, programmed["z_clearance"])

    def test_missing_blade_still_builds(self):
        snap = _snap(blade_text="")
        self.assertIsNone(snap.blade_thickness)
        self.assertTrue(snap.nc_blocked)
        self.assertIsNone(snap.programmed_z_sink_finish)
        info = format_help_info(snap)
        self.assertIn("—", info)
        self.assertIn("BLOCKIERT", status_headline(snap))
        self.assertNotIn("nicht angegeben", info)
        self.assertEqual(snap.workpiece_z_sink_finish, 38.0)


class TestBsfHelpLayout(unittest.TestCase):
    def test_regions_positive_no_overlap(self):
        layout = compute_bsf_help_layout(1100, 720)
        main, blade, info = layout.main_cross_section, layout.blade_detail, layout.info_panel
        for rect in (main, blade, info, layout.header, layout.status):
            self.assertGreater(rect.w, 40)
            self.assertGreater(rect.h, 20)
        self.assertFalse(main.overlaps(blade, gap=4))
        self.assertFalse(main.overlaps(info, gap=4))
        self.assertFalse(blade.overlaps(info, gap=4))
        share = main.w / (main.w + blade.w)
        self.assertGreater(share, 0.62)
        self.assertLess(share, 0.75)

    def test_scales_with_window(self):
        small = compute_bsf_help_layout(1000, 650)
        large = compute_bsf_help_layout(1920, 1080)
        self.assertGreater(large.main_cross_section.h, small.main_cross_section.h)
        self.assertGreater(large.main_cross_section.w, small.main_cross_section.w)


class TestBsfHelpWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        app = self.app
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.z0_var.set("Z0 ist Unterkante Bund")
        for key, val in (("bund_thickness", "18"), ("sink_depth", "38"), ("clearance", "23")):
            app.entries[key].delete(0, "end")
            app.entries[key].insert(0, val)
        app.entries["blade_thickness"].delete(0, "end")
        app.entries["blade_thickness"].insert(0, "3")
        app.blade_measurement_var.set(SPINDLE_LABEL)

    def _open(self):
        from help_views.bsf_geometry_help import BSFGeometryHelpWindow

        win = BSFGeometryHelpWindow(self.root, snapshot_provider=self.app.build_bsf_geometry_help_snapshot)
        win.win.update_idletasks()
        win.canvas.config(width=720, height=560)
        win.detail_canvas.config(width=320, height=240)
        win.win.update_idletasks()
        win._redraw_main()
        win._redraw_detail()
        return win

    def test_help_button_visible_in_bsf(self):
        self.assertTrue(is_mapped(self.app.bsf_processing_frame))
        self.assertTrue(hasattr(self.app, "open_bsf_geometry_help"))

    def test_help_button_hidden_with_bsf_panel_in_bgf(self):
        self.app.mode_var.set(MODE_BGF)
        self.app.on_mode_change(None)
        self.assertFalse(is_mapped(self.app.bsf_processing_frame))

    def test_window_draws_geometry(self):
        win = self._open()
        self.assertEqual(win.win.title(), "HEULE BSF – Senkgeometrie")
        main = _canvas_text(win.canvas)
        detail = _canvas_text(win.detail_canvas)
        info = win.info_dump()
        self.assertTrue(win.canvas.find_withtag("flange"))
        self.assertTrue(win.canvas.find_withtag("hole"))
        self.assertTrue(win.canvas.find_withtag("blade"))
        self.assertTrue(win.canvas.find_withtag("tool"))
        self.assertTrue(win.canvas.find_withtag("z0"))
        self.assertTrue(win.canvas.find_withtag("sink_arrow"))
        self.assertTrue(win.canvas.find_withtag("sink_finish"))
        self.assertFalse(win.canvas.find_withtag("z_axis"))
        self.assertTrue(win.detail_canvas.find_withtag("finish_edge"))
        self.assertTrue(win.detail_canvas.find_withtag("measurement_edge"))
        self.assertIn("Oberkante Bund", main)
        self.assertIn("Unterkante Bund", main)
        self.assertIn("Bohrung", main)
        self.assertIn("Senk-Fertigfläche", main)
        self.assertIn("SENKEN", main)
        self.assertIn("Z0", main)
        self.assertIn("SCHEMATISCH", main)
        self.assertNotIn("FERTIGKANTE", main)
        self.assertNotIn("Spindelseitige Schwertkante", main)
        self.assertIn("FERTIGKANTE", detail)
        self.assertIn("Spindelseitige Schwertkante", detail)
        self.assertIn("Werkzeugspitzenseitige Schwertkante", detail)
        self.assertIn("WERKZEUG HIER VERMESSEN", detail)
        self.assertIn("3.000 mm", detail)
        self.assertIn("18.000 mm", info)
        self.assertIn("+38.0000", info)
        self.assertIn("-23.0000", info)
        self.assertIn("NC-STATUS: FREIGEGEBEN", win.status_head.cget("text"))
        flange = win.canvas.bbox("flange")
        blade = win.canvas.bbox("blade")
        self.assertIsNotNone(flange)
        self.assertIsNotNone(blade)
        flange_h = flange[3] - flange[1]
        self.assertGreater(flange_h, 0.55 * 560)
        self.assertLess(flange_h, 0.80 * 560)
        self.assertGreaterEqual(blade[1], flange[3] - 8)
        self.assertLess(blade[1], flange[3] + 8)
        win.win.destroy()

    def test_z0_switch_and_refresh(self):
        win = self._open()
        self.assertIn("Unterkante Bund", win.info_dump())
        self.app.z0_var.set("Z0 ist Oberkante Bund")
        win.refresh()
        info = win.info_dump()
        self.assertIn("Oberkante Bund", info)
        self.assertIn("+20.0000", info)
        self.assertIn("-41.0000", info)
        main = _canvas_text(win.canvas)
        self.assertIn("Z0 · Oberkante Bund", main)
        self.app.blade_measurement_var.set(TIP_LABEL)
        win.refresh()
        info = win.info_dump()
        self.assertIn("Werkzeugspitzenseitige Schwertkante", info)
        self.assertIn("+17.0000", info)
        detail = _canvas_text(win.detail_canvas)
        self.assertIn("WERKZEUG HIER VERMESSEN", detail)
        win.win.destroy()

    def test_missing_blade_window_opens(self):
        self.app.entries["blade_thickness"].delete(0, "end")
        self.app.blade_measurement_var.set("--- bitte waehlen ---")
        win = self._open()
        info = win.info_dump()
        self.assertIn("—", info)
        self.assertIn("BLOCKIERT", win.status_head.cget("text"))
        self.assertIn("Schwertdicke fehlt", win.status_sub.cget("text"))
        self.assertTrue(win.win.winfo_exists())
        self.assertTrue(win.canvas.find_withtag("flange"))
        win.win.destroy()

    def test_nc_unchanged_after_help(self):
        import tkinter.messagebox as mb

        orig = mb.showerror
        mb.showerror = lambda *a, **k: None
        try:
            self.app.generate_bsf_code()
            before = self.app.output_text.get("1.0", "end")
            win = self._open()
            win.refresh()
            win.win.geometry("1200x800")
            win.win.update_idletasks()
            win._redraw_main()
            win.win.destroy()
            self.app.generate_bsf_code()
            after = self.app.output_text.get("1.0", "end")
        finally:
            mb.showerror = orig
        self.assertEqual(before, after)
        self.assertIn("BEGIN PGM", before)


if __name__ == "__main__":
    unittest.main()
