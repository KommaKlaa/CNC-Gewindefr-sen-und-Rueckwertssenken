"""PHASE UI.HELP.2 – CERATIZIT-BGF Gewinde- und Tiefengeometrie-Hilfsgrafik."""

from __future__ import annotations

import inspect
import unittest

import bsf_generator_verbessert_v3 as gen
from bgf_depth import BGFDepthRequest, DepthGateStatus, evaluate_bgf_depth, policy_from_tool
from bgf_surface import above_surface, absolute_from_surface
from bgf_variable_depth import axial_increment_from_passes
from coordinates import BGFCoordinatePosition
from help_views.bgf_geometry_help import BGFGeometryHelpWindow
from help_views.bgf_geometry_layout import compute_bgf_help_layout
from help_views.bgf_geometry_model import (
    build_bgf_geometry_help_snapshot,
    format_help_info,
    status_detail,
    status_headline,
)
from help_views import bgf_geometry_model as bgf_help_model
from ui import MODE_BGF, MODE_BSF
from ui.visibility import is_mapped


def _policy_for(size: str):
    data = gen.BGF_DATA[size]
    approved = gen.approved_max_thread_depth(data.size, data.article_no)
    return policy_from_tool(
        data.size,
        data.thread_length,
        data.drill_depth,
        data.mill_start_depth,
        article_no=data.article_no,
        approved_max_thread_depth=approved,
        axial_increment=axial_increment_from_passes(data.passes),
    )


def _snap(size: str = "M10", **overrides):
    data = gen.BGF_DATA[size]
    kwargs = dict(
        tool_size=data.size,
        article_no=data.article_no,
        radius=data.radius,
        pitch=data.pitch,
        predrill_depth=data.predrill_depth,
        policy=_policy_for(size),
        surface_z=0.0,
        thread_depth=data.thread_length,
        core_hole_depth=None,
        approach_clearance=1.0,
    )
    kwargs.update(overrides)
    return build_bgf_geometry_help_snapshot(**kwargs)


def _canvas_text(canvas) -> str:
    parts = []
    for item in canvas.find_all():
        if canvas.type(item) == "text":
            parts.append(canvas.itemcget(item, "text"))
    return "\n".join(parts)


class TestBgfHelpModel(unittest.TestCase):
    def test_m10_template(self):
        snap = _snap(thread_depth=25.060, surface_z=0.0)
        self.assertTrue(snap.is_template)
        self.assertTrue(snap.ok_for_nc)
        self.assertEqual(snap.status, DepthGateStatus.TEMPLATE_OK)
        self.assertAlmostEqual(snap.mill_start_z, -24.8990, places=4)
        self.assertAlmostEqual(snap.drill_z, -27.8700, places=4)
        self.assertAlmostEqual(snap.depth_delta, 0.0, places=3)
        self.assertFalse(snap.show_template_overlay)
        self.assertIn("CERATIZIT HERSTELLER-TEMPLATE", status_detail(snap))
        self.assertIn("FREIGEGEBEN", status_headline(snap))

    def test_m10_depth20(self):
        snap = _snap(thread_depth=20.0)
        self.assertFalse(snap.is_template)
        self.assertEqual(snap.status, DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK)
        self.assertAlmostEqual(snap.mill_start_depth, 19.839, places=3)
        self.assertAlmostEqual(snap.deepest_milling_depth, 21.789, places=3)
        self.assertAlmostEqual(snap.drill_depth, 22.810, places=3)
        self.assertAlmostEqual(snap.drill_reserve, 1.021, places=3)
        self.assertAlmostEqual(snap.depth_delta, 5.060, places=3)
        self.assertTrue(snap.show_template_overlay)
        self.assertIn("AXIALE TEMPLATE-VERSCHIEBUNG", status_detail(snap))

    def test_m10_depth10(self):
        snap = _snap(thread_depth=10.0)
        self.assertAlmostEqual(snap.mill_start_depth, 9.839, places=3)
        self.assertAlmostEqual(snap.drill_depth, 12.810, places=3)
        self.assertTrue(snap.ok_for_nc)

    def test_m10_depth26_blocked(self):
        snap = _snap(thread_depth=26.0)
        self.assertFalse(snap.ok_for_nc)
        self.assertEqual(snap.status, DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX)
        self.assertIsNone(snap.mill_start_depth)
        self.assertIsNone(snap.drill_depth)
        self.assertIsNone(snap.depth_delta)
        self.assertFalse(snap.show_template_overlay)
        self.assertIn("BLOCKIERT", status_headline(snap))
        self.assertIn("THREAD_DEPTH_EXCEEDS_APPROVED_MAX", status_detail(snap))

    def test_surface_35_clearance_5(self):
        snap = _snap(surface_z=35.0, thread_depth=20.0, approach_clearance=5.0)
        self.assertAlmostEqual(snap.approach_z, 40.0000, places=4)
        self.assertAlmostEqual(snap.thread_end_z, 15.0000, places=4)
        self.assertAlmostEqual(snap.mill_start_z, 15.1610, places=4)
        self.assertAlmostEqual(snap.deepest_milling_z, 13.2110, places=4)
        self.assertAlmostEqual(snap.drill_z, 12.1900, places=4)

    def test_core_hole_30_separated(self):
        snap = _snap(thread_depth=20.0, core_hole_depth=30.0, surface_z=35.0)
        self.assertAlmostEqual(snap.core_hole_depth, 30.0)
        self.assertAlmostEqual(snap.core_hole_z, 5.0, places=4)
        self.assertNotAlmostEqual(snap.core_hole_z, snap.drill_z)
        info = format_help_info(snap)
        self.assertIn("Kernlochtiefe Soll", info)
        self.assertIn("30.000 mm", info)
        self.assertIn("NC-Bohrtiefe", info)
        self.assertNotIn("Kernlochtiefe Soll       22.810", info)

    def test_core_hole_none(self):
        snap = _snap(thread_depth=20.0, core_hole_depth=None)
        self.assertIsNone(snap.core_hole_depth)
        self.assertIsNone(snap.core_hole_z)
        self.assertIn("Kernlochtiefe Soll       —", format_help_info(snap))

    def test_m16_predrill_not_shifted(self):
        snap = _snap("M16", thread_depth=20.0, surface_z=35.0)
        self.assertAlmostEqual(snap.predrill_depth, 2.100, places=3)
        self.assertFalse(snap.predrill_shifted)
        self.assertAlmostEqual(snap.predrill_z, 32.9000, places=4)
        self.assertAlmostEqual(snap.predrill_z, absolute_from_surface(35.0, 2.100), places=4)

    def test_m16x15_predrill(self):
        snap = _snap("M16x1.5", thread_depth=20.0, surface_z=0.0)
        self.assertAlmostEqual(snap.predrill_depth, 2.200, places=3)
        self.assertFalse(snap.predrill_shifted)
        self.assertAlmostEqual(snap.predrill_z, -2.2000, places=4)

    def test_no_new_depth_formula(self):
        src = inspect.getsource(bgf_help_model)
        self.assertNotIn("compute_axial_template_shift", src)
        self.assertIn("evaluate_bgf_depth", src)
        self.assertIn("above_surface", src)
        self.assertIn("absolute_from_surface", src)

        surface_z = 35.0
        clearance = 5.0
        thread_depth = 20.0
        snap = _snap(surface_z=surface_z, thread_depth=thread_depth, approach_clearance=clearance)
        ev = evaluate_bgf_depth(BGFDepthRequest(thread_depth), _policy_for("M10"), surface_z=surface_z)
        self.assertEqual(snap.approach_z, above_surface(surface_z, clearance))
        self.assertEqual(snap.thread_end_z, ev.thread_end_z)
        self.assertEqual(snap.mill_start_depth, ev.nc_mill_start_depth)
        self.assertEqual(snap.mill_start_z, ev.nc_mill_start_z)
        self.assertEqual(snap.drill_depth, ev.nc_drill_depth)
        self.assertEqual(snap.drill_z, ev.nc_drill_z)
        self.assertEqual(snap.deepest_milling_depth, ev.deepest_milling_depth)
        self.assertEqual(snap.drill_reserve, ev.drill_reserve)
        self.assertEqual(snap.depth_delta, ev.depth_delta)
        self.assertEqual(snap.deepest_milling_z, absolute_from_surface(surface_z, ev.deepest_milling_depth))

    def test_empty_list_snapshot(self):
        snap = _snap(empty_list=True, thread_depth=None, surface_z=None)
        self.assertTrue(snap.empty_list)
        self.assertIn("Keine Position vorhanden", status_detail(snap))


class TestBgfHelpLayout(unittest.TestCase):
    def test_regions_positive_no_overlap(self):
        layout = compute_bgf_help_layout(1100, 720)
        main, detail, info = layout.main_cross_section, layout.depth_detail, layout.info_panel
        for rect in (main, detail, info, layout.header, layout.status):
            self.assertGreater(rect.w, 40)
            self.assertGreater(rect.h, 20)
        self.assertFalse(main.overlaps(detail, gap=4))
        self.assertFalse(main.overlaps(info, gap=4))
        self.assertFalse(detail.overlaps(info, gap=4))
        share = main.w / (main.w + detail.w)
        self.assertGreater(share, 0.62)
        self.assertLess(share, 0.75)

    def test_scales_with_window(self):
        small = compute_bgf_help_layout(1000, 650)
        large = compute_bgf_help_layout(1920, 1080)
        self.assertGreater(large.main_cross_section.h, small.main_cross_section.h)
        self.assertGreater(large.main_cross_section.w, small.main_cross_section.w)


class TestBgfHelpWindow(unittest.TestCase):
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
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.bgf_size_var.set("M10")
        app.load_bgf_values()
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        for key, val in (
            ("single_x", "0"),
            ("single_y", "0"),
            ("single_surface_z", "0"),
            ("approach_clearance", "1.000"),
            ("bgf_core_hole_depth", ""),
        ):
            app.entries[key].delete(0, "end")
            app.entries[key].insert(0, val)
        app.entries["bgf_thread_depth"].delete(0, "end")
        app.entries["bgf_thread_depth"].insert(0, "25.060")

    def _open(self):
        win = BGFGeometryHelpWindow(self.root, source_provider=self.app.collect_bgf_help_source)
        win.win.update_idletasks()
        win.canvas.config(width=720, height=560)
        win.detail_canvas.config(width=320, height=240)
        win.win.update_idletasks()
        win._redraw_main()
        win._redraw_detail()
        return win

    def test_help_button_visible_in_bgf(self):
        self.assertTrue(is_mapped(self.app.bgf_processing_frame))
        self.assertTrue(hasattr(self.app, "open_bgf_geometry_help"))

    def test_help_button_hidden_with_bgf_panel_in_bsf(self):
        self.app.mode_var.set(MODE_BSF)
        self.app.on_mode_change(None)
        self.assertFalse(is_mapped(self.app.bgf_processing_frame))

    def test_window_template_m10(self):
        win = self._open()
        self.assertEqual(win.win.title(), "CERATIZIT BGF – Gewinde- und Tiefengeometrie")
        main = _canvas_text(win.canvas)
        detail = _canvas_text(win.detail_canvas)
        info = win.info_dump()
        self.assertTrue(win.canvas.find_withtag("workpiece"))
        self.assertTrue(win.canvas.find_withtag("hole"))
        self.assertTrue(win.canvas.find_withtag("thread"))
        self.assertTrue(win.canvas.find_withtag("surface"))
        self.assertTrue(win.canvas.find_withtag("mill_start"))
        self.assertTrue(win.canvas.find_withtag("drill"))
        self.assertFalse(win.canvas.find_withtag("template_overlay"))
        self.assertFalse(win.canvas.find_withtag("core_hole"))
        self.assertIn("Z Oberfläche", main)
        self.assertIn("Gewindeende", main)
        self.assertIn("NC-Bohrposition", main)
        self.assertIn("SCHEMATISCH", main)
        self.assertIn("aus dem Werkstück", main)
        self.assertNotIn("Kernlochtiefe Soll", main)
        self.assertIn("Inkrementelle CERATIZIT-Bahn unverändert", detail)
        self.assertIn("Verschiebung: 0.000 mm", detail)
        self.assertIn("M10", info)
        self.assertIn("5089810000", info)
        self.assertIn("R+3.9790 mm", info)
        self.assertIn("-24.8990", info)
        self.assertIn("-27.8700", info)
        self.assertIn("Kernlochtiefe Soll       —", info)
        self.assertIn("FREIGEGEBEN", win.status_head.cget("text"))
        self.assertIn("CERATIZIT HERSTELLER-TEMPLATE", win.status_sub.cget("text"))
        workpiece = win.canvas.bbox("workpiece")
        self.assertIsNotNone(workpiece)
        wp_h = workpiece[3] - workpiece[1]
        self.assertGreater(wp_h, 0.45 * 560)
        win.win.destroy()

    def test_variable_depth20_overlay(self):
        self.app.entries["bgf_thread_depth"].delete(0, "end")
        self.app.entries["bgf_thread_depth"].insert(0, "20")
        self.app.entries["single_surface_z"].delete(0, "end")
        self.app.entries["single_surface_z"].insert(0, "35")
        self.app.entries["approach_clearance"].delete(0, "end")
        self.app.entries["approach_clearance"].insert(0, "5")
        self.app.entries["bgf_core_hole_depth"].delete(0, "end")
        self.app.entries["bgf_core_hole_depth"].insert(0, "30")
        win = self._open()
        main = _canvas_text(win.canvas)
        detail = _canvas_text(win.detail_canvas)
        info = win.info_dump()
        self.assertTrue(win.canvas.find_withtag("template_overlay"))
        self.assertTrue(win.canvas.find_withtag("core_hole"))
        self.assertIn("Kernlochtiefe Soll", main)
        self.assertIn("NC-Bohrposition", main)
        self.assertIn("+40.0000", info)
        self.assertIn("+15.0000", info)
        self.assertIn("+15.1610", info)
        self.assertIn("+13.2110", info)
        self.assertIn("+12.1900", info)
        self.assertIn("19.839 mm", info)
        self.assertIn("22.810 mm", info)
        self.assertIn("1.021 mm", info)
        self.assertIn("30.000 mm", info)
        self.assertIn("5.060 mm", detail)
        self.assertIn("AXIALE TEMPLATE-VERSCHIEBUNG", win.status_sub.cget("text"))
        win.refresh()
        win.win.geometry("1200x800")
        win.win.update_idletasks()
        win._redraw_main()
        self.assertTrue(win.canvas.find_withtag("template_overlay"))
        win.win.destroy()

    def test_depth10_and_blocked26(self):
        self.app.entries["bgf_thread_depth"].delete(0, "end")
        self.app.entries["bgf_thread_depth"].insert(0, "10")
        win = self._open()
        info = win.info_dump()
        self.assertIn("9.839 mm", info)
        self.assertIn("12.810 mm", info)
        self.app.entries["bgf_thread_depth"].delete(0, "end")
        self.app.entries["bgf_thread_depth"].insert(0, "26")
        win.refresh()
        self.assertIn("BLOCKIERT", win.status_head.cget("text"))
        self.assertIn("THREAD_DEPTH_EXCEEDS_APPROVED_MAX", win.status_sub.cget("text"))
        self.assertIsNone(win.snapshot.mill_start_depth)
        self.assertIsNone(win.snapshot.depth_delta)
        self.assertFalse(win.canvas.find_withtag("template_overlay"))
        win.win.destroy()

    def test_m16_predrill_canvas(self):
        self.app.bgf_size_var.set("M16")
        self.app.load_bgf_values()
        self.app.entries["bgf_thread_depth"].delete(0, "end")
        self.app.entries["bgf_thread_depth"].insert(0, "20")
        win = self._open()
        main = _canvas_text(win.canvas)
        self.assertTrue(win.canvas.find_withtag("predrill"))
        self.assertIn("Vorbohr-/Anbohrtiefe", main)
        self.assertFalse(win.snapshot.predrill_shifted)
        self.assertAlmostEqual(win.snapshot.predrill_depth, 2.100, places=3)
        win.win.destroy()

    def test_coord_list_navigation_local(self):
        self.app.position_mode_var.set("Koordinatenliste")
        self.app.on_position_mode_change(None)
        self.app.coord_rows = [
            BGFCoordinatePosition(0.0, 0.0, 0.0, 25.06),
            BGFCoordinatePosition(235.0, -80.5, 35.0, 20.0, 30.0),
            BGFCoordinatePosition(10.0, 20.0, 0.0, 10.0),
        ]
        self.app._refresh_coord_tree()
        self.app.coord_tree.selection_set("1")
        win = self._open()
        self.assertEqual(win.snapshot.position_index, 2)
        self.assertAlmostEqual(win.snapshot.x, 235.0)
        self.assertAlmostEqual(win.snapshot.thread_depth, 20.0)
        self.assertIn("Position 2 / 3", win.nav_label.cget("text"))
        self.assertIn("+235.000", win.xy_label.cget("text"))
        win._nav(1)
        self.assertEqual(win.snapshot.position_index, 3)
        self.assertAlmostEqual(win.snapshot.thread_depth, 10.0)
        self.assertEqual(self.app.coord_tree.selection(), ("1",))
        self.assertEqual(self.app.coord_rows[1].thread_depth, 20.0)
        win.win.destroy()

    def test_empty_coord_list_opens(self):
        self.app.position_mode_var.set("Koordinatenliste")
        self.app.on_position_mode_change(None)
        self.app.coord_rows = []
        self.app._refresh_coord_tree()
        win = self._open()
        self.assertTrue(win.win.winfo_exists())
        self.assertIn("Keine Position vorhanden", win.nav_label.cget("text"))
        self.assertTrue(win.canvas.find_withtag("empty") or "Keine Position" in _canvas_text(win.canvas))
        win.win.destroy()

    def test_circle_header_not_multi_cut(self):
        self.app.position_mode_var.set("Teilkreis")
        self.app.on_position_mode_change(None)
        win = self._open()
        self.assertEqual(win.snapshot.position_count, 1)
        self.assertIn("Teilkreis", win.nav_label.cget("text"))
        self.assertIn("Ø715", win.nav_label.cget("text"))
        self.assertIn("24 Positionen", win.nav_label.cget("text"))
        win.win.destroy()

    def test_nc_unchanged_after_help(self):
        import tkinter.messagebox as mb

        self.app.position_mode_var.set("Teilkreis")
        self.app.on_position_mode_change(None)
        orig = mb.showerror
        mb.showerror = lambda *a, **k: None
        try:
            self.app.generate_bgf_code()
            before = self.app.output_text.get("1.0", "end")
            win = self._open()
            win.refresh()
            win._nav(1)
            win.win.geometry("1200x800")
            win.win.update_idletasks()
            win._redraw_main()
            win.win.destroy()
            self.app.generate_bgf_code()
            after = self.app.output_text.get("1.0", "end")
        finally:
            mb.showerror = orig
        self.assertEqual(before, after)
        self.assertIn("BEGIN PGM", before)

    def test_bsf_help_still_opens(self):
        from help_views.bsf_geometry_help import BSFGeometryHelpWindow

        self.app.mode_var.set(MODE_BSF)
        self.app.on_mode_change(None)
        self.app.z0_var.set("Z0 ist Unterkante Bund")
        for key, val in (("bund_thickness", "18"), ("sink_depth", "38"), ("clearance", "23")):
            self.app.entries[key].delete(0, "end")
            self.app.entries[key].insert(0, val)
        self.app.entries["blade_thickness"].delete(0, "end")
        self.app.entries["blade_thickness"].insert(0, "3")
        self.app.blade_measurement_var.set("Spindelseitige Schwertkante (Oberkante)")
        win = BSFGeometryHelpWindow(self.root, snapshot_provider=self.app.build_bsf_geometry_help_snapshot)
        win.win.update_idletasks()
        self.assertEqual(win.win.title(), "HEULE BSF – Senkgeometrie")
        self.assertTrue(win.canvas.find_withtag("flange"))
        win.win.destroy()


if __name__ == "__main__":
    unittest.main()
