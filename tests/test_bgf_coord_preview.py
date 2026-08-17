"""PHASE BGF.COORD.4 – Positionsvorschau: Transform, Modell, Teilkreis, Read-only."""

from __future__ import annotations

import copy
import unittest

import bsf_generator_verbessert_v3 as gen
from bgf_depth import DepthGateStatus
from coordinates import BGFCoordinatePosition
from coordinates.circle_positions import compute_circle_xy_positions
from preview.bgf_preview_model import (
    build_circle_positions_for_preview,
    build_preview_from_positions,
)
from preview.bgf_preview_transform import (
    ViewTransform,
    canvas_is_ready_for_fit,
    compute_bounds,
    fit_transform,
    resolve_view_after_resize,
)


def _m10_policy():
    data = gen.BGF_DATA["M10"]
    return gen.policy_from_tool(
        data.size,
        data.thread_length,
        data.drill_depth,
        data.mill_start_depth,
        article_no=data.article_no,
        approved_max_thread_depth=gen.approved_max_thread_depth(data.size, data.article_no),
        axial_increment=gen.axial_increment_from_passes(data.passes),
        variable_depth_rule_validated=True,
    )


class TestPreviewTransform(unittest.TestCase):
    def test_y_positive_is_above_on_canvas(self):
        pts = [(0.0, 100.0), (0.0, -100.0)]
        t = fit_transform(pts, 800, 600)
        c1 = t.world_to_canvas(0.0, 100.0)
        c2 = t.world_to_canvas(0.0, -100.0)
        self.assertLess(c1[1], c2[1], "Y=+100 muss oberhalb von Y=-100 liegen")

    def test_x_positive_is_right(self):
        pts = [(100.0, 0.0), (-100.0, 0.0)]
        t = fit_transform(pts, 800, 600)
        c1 = t.world_to_canvas(100.0, 0.0)
        c2 = t.world_to_canvas(-100.0, 0.0)
        self.assertGreater(c1[0], c2[0])

    def test_bounds_0_100_canvas_mapping(self):
        pts = [(0.0, 0.0), (100.0, 100.0)]
        t = fit_transform(pts, 800, 600)
        c0 = t.world_to_canvas(0.0, 0.0)
        c1 = t.world_to_canvas(100.0, 100.0)
        self.assertLess(c0[0], c1[0])
        self.assertGreater(c0[1], c1[1])  # Y oben = kleinere Canvas-Y

    def test_single_point_no_div0(self):
        t = fit_transform([(50.0, 25.0)], 800, 600)
        self.assertGreater(t.scale, 0)
        cx, cy = t.world_to_canvas(50.0, 25.0)
        self.assertAlmostEqual(cx, 400.0, delta=5.0)
        self.assertAlmostEqual(cy, 300.0, delta=5.0)

    def test_all_x_equal(self):
        pts = [(100.0, 0.0), (100.0, 50.0), (100.0, 100.0)]
        t = fit_transform(pts, 800, 600)
        self.assertGreater(t.scale, 0)
        ys = [t.world_to_canvas(x, y)[1] for x, y in pts]
        self.assertLess(ys[2], ys[0])  # Y=100 oben

    def test_all_y_equal(self):
        pts = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]
        t = fit_transform(pts, 800, 600)
        xs = [t.world_to_canvas(x, y)[0] for x, y in pts]
        self.assertLess(xs[0], xs[2])

    def test_negative_coords(self):
        pts = [(-200.0, -50.0), (-100.0, -10.0)]
        t = fit_transform(pts, 800, 600)
        self.assertGreater(t.scale, 0)

    def test_large_coords(self):
        pts = [(1e6, 1e6), (1e6 + 100, 1e6 + 50)]
        t = fit_transform(pts, 800, 600)
        self.assertGreater(t.scale, 0)

    def test_tiny_spacing(self):
        pts = [(0.0, 0.0), (0.001, 0.001)]
        t = fit_transform(pts, 800, 600)
        self.assertGreater(t.scale, 0)

    def test_zoom_at_preserves_pivot(self):
        t = ViewTransform(2.0, 100.0, 200.0, 800, 600)
        pivot = (150.0, 180.0)
        wx, wy = t.canvas_to_world(*pivot)
        t2 = t.zoom_at(1.5, *pivot)
        wx2, wy2 = t2.canvas_to_world(*pivot)
        self.assertAlmostEqual(wx, wx2, places=9)
        self.assertAlmostEqual(wy, wy2, places=9)


class TestPreviewOrderAndStatus(unittest.TestCase):
    def test_order_preserved(self):
        positions = [
            BGFCoordinatePosition(100, 0, 0, 25.06),
            BGFCoordinatePosition(0, 100, 0, 25.06),
            BGFCoordinatePosition(50, 50, 0, 25.06),
        ]
        snap = build_preview_from_positions(
            positions,
            policy=_m10_policy(),
            safe_z=50,
            end_safe_z=50,
            approach_clearance=2,
            mode_label="Koordinatenliste",
            thread_size="M10",
            article_no="5089810000",
            tool_radius=3.9790,
            tool_number=8,
            program_name="TEST",
        )
        self.assertEqual([p.index for p in snap.points], [1, 2, 3])
        self.assertEqual([(p.x, p.y) for p in snap.points], [(100, 0), (0, 100), (50, 50)])

    def test_depth_status_m10(self):
        positions = [
            BGFCoordinatePosition(0, 0, 0, 25.06),
            BGFCoordinatePosition(10, 0, 0, 20.0),
            BGFCoordinatePosition(20, 0, 0, 26.0),
        ]
        snap = build_preview_from_positions(
            positions,
            policy=_m10_policy(),
            safe_z=50,
            end_safe_z=50,
            approach_clearance=2,
            mode_label="Koordinatenliste",
            thread_size="M10",
            article_no="5089810000",
            tool_radius=3.9790,
            tool_number=8,
            program_name="TEST",
        )
        self.assertEqual(snap.points[0].status_code, DepthGateStatus.TEMPLATE_OK)
        self.assertEqual(snap.points[1].status_code, DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK)
        self.assertEqual(snap.points[2].status_code, DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX)
        self.assertTrue(snap.points[0].ok_for_nc)
        self.assertTrue(snap.points[1].ok_for_nc)
        self.assertFalse(snap.points[2].ok_for_nc)
        self.assertFalse(snap.nc_allowed)
        self.assertGreaterEqual(snap.blocked_count, 1)

    def test_tool_info(self):
        data = gen.BGF_DATA["M10"]
        snap = build_preview_from_positions(
            [BGFCoordinatePosition(0, 0, 0, data.thread_length)],
            policy=_m10_policy(),
            safe_z=50,
            end_safe_z=50,
            approach_clearance=2,
            mode_label="Einzelposition",
            thread_size=data.size,
            article_no=data.article_no,
            tool_radius=data.radius,
            tool_number=8,
            program_name="BGF_M10",
        )
        self.assertEqual(snap.thread_size, "M10")
        self.assertEqual(snap.article_no, "5089810000")
        self.assertAlmostEqual(snap.tool_radius, 3.9790)

    def test_duplicates(self):
        positions = [
            BGFCoordinatePosition(10, 20, 0, 25.06),
            BGFCoordinatePosition(10, 20, 0, 25.06),
        ]
        snap = build_preview_from_positions(
            positions,
            policy=_m10_policy(),
            safe_z=50,
            end_safe_z=50,
            approach_clearance=2,
            mode_label="Koordinatenliste",
            thread_size="M10",
            article_no="5089810000",
            tool_radius=3.9790,
            tool_number=8,
            program_name="TEST",
        )
        self.assertTrue(snap.points[0].is_duplicate_xyz)
        self.assertTrue(snap.points[1].is_duplicate_xyz)
        self.assertEqual(snap.points[0].xy_overlap_count, 2)

    def test_surface_z_overlap_same_xy(self):
        positions = [
            BGFCoordinatePosition(10, 20, 0.0, 25.06),
            BGFCoordinatePosition(10, 20, 5.0, 25.06),
        ]
        snap = build_preview_from_positions(
            positions,
            policy=_m10_policy(),
            safe_z=50,
            end_safe_z=50,
            approach_clearance=2,
            mode_label="Koordinatenliste",
            thread_size="M10",
            article_no="5089810000",
            tool_radius=3.9790,
            tool_number=8,
            program_name="TEST",
        )
        self.assertFalse(snap.points[0].is_duplicate_xyz)
        self.assertEqual(snap.points[0].xy_overlap_count, 2)
        self.assertEqual(snap.points[0].x, snap.points[1].x)
        self.assertEqual(snap.points[0].y, snap.points[1].y)
        self.assertNotEqual(snap.points[0].surface_z, snap.points[1].surface_z)

    def test_program_status_allowed(self):
        positions = [
            BGFCoordinatePosition(0, 0, 0, 25.06),
            BGFCoordinatePosition(10, 0, 0, 20.0),
        ]
        snap = build_preview_from_positions(
            positions,
            policy=_m10_policy(),
            safe_z=50,
            end_safe_z=50,
            approach_clearance=2,
            mode_label="Koordinatenliste",
            thread_size="M10",
            article_no="5089810000",
            tool_radius=3.9790,
            tool_number=8,
            program_name="TEST",
        )
        self.assertTrue(snap.nc_allowed)


class TestCirclePreview(unittest.TestCase):
    def test_circle_100_4_start0(self):
        xy = compute_circle_xy_positions(
            center_x=0, center_y=0, diameter=100, count=4, start_angle_deg=0
        )
        expected = [(50.0, 0.0), (0.0, 50.0), (-50.0, 0.0), (0.0, -50.0)]
        self.assertEqual(len(xy), 4)
        for (ax, ay), (ex, ey) in zip(xy, expected):
            self.assertAlmostEqual(ax, ex, places=9)
            self.assertAlmostEqual(ay, ey, places=9)

    def test_circle_positions_for_preview_order(self):
        positions = build_circle_positions_for_preview(
            center_x=0,
            center_y=0,
            diameter=100,
            count=4,
            start_angle_deg=0,
            thread_depth=25.06,
            core_hole_depth=None,
        )
        self.assertAlmostEqual(positions[0].x, 50.0)
        self.assertAlmostEqual(positions[1].y, 50.0)


class TestPreviewGuiSmokeAndReadonly(unittest.TestCase):
    def test_preview_window_opens_and_readonly(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set("Bohrgewindefraesen (BGF)")
        app.on_mode_change(None)
        app.bgf_size_var.set("M10")
        app.on_bgf_size_change(None)
        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)

        rows_before = [
            BGFCoordinatePosition(0, 0, 0, 25.06),
            BGFCoordinatePosition(100, 0, 0, 20.0),
            BGFCoordinatePosition(0, 100, 0, 26.0),
            BGFCoordinatePosition(50, 50, 0, 25.06),
            BGFCoordinatePosition(10, 10, 0, 25.06),
        ]
        app.coord_rows = list(rows_before)
        app._refresh_coord_tree()
        snapshot_rows = copy.deepcopy(app.coord_rows)

        snap = app.build_bgf_preview_snapshot()
        self.assertEqual(len(snap.points), 5)
        self.assertEqual(snap.thread_size, "M10")
        self.assertAlmostEqual(snap.tool_radius, 3.9790)
        self.assertFalse(snap.nc_allowed)  # depth 26 blocked
        self.assertEqual(snap.points[1].status_code, DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK)
        self.assertEqual(snap.points[2].status_code, DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX)

        # Y-Richtung im Snapshot + Transform
        t = fit_transform([(p.x, p.y) for p in snap.points], 900, 600)
        c_high = t.world_to_canvas(0, 100)
        c_low = t.world_to_canvas(0, 0)
        self.assertLess(c_high[1], c_low[1])

        from preview.bgf_preview_window import BGFPreviewWindow

        win = BGFPreviewWindow(root, snapshot_provider=app.build_bgf_preview_snapshot)
        win.win.update_idletasks()
        win.canvas.config(width=600, height=500)
        win.win.update_idletasks()
        win.fit_to_positions()
        self.assertTrue(win.win.winfo_exists())
        self.assertGreaterEqual(len(win.canvas.find_withtag("pos")), 5)
        win.fit_all()
        win._zoom_at(1.2, 200, 200)
        win.transform = win.transform.pan(30, -20)
        win._user_view_changed = True
        win._redraw()
        # Klick auf Punkt 1 (approx)
        if win.transform:
            cx, cy = win.transform.world_to_canvas(0, 0)
            win._on_left_click(type("E", (), {"x": int(cx), "y": int(cy)})())
        detail = win.detail.get("1.0", tk.END)
        self.assertIn("Position", detail)

        win.win.destroy()
        win = None
        root.update_idletasks()

        # Read-only: Daten unveraendert
        self.assertEqual(app.coord_rows, snapshot_rows)
        # Nur gueltige Liste fuer NC-Vergleich (depth26 blockiert Generierung)
        app.coord_rows = [
            BGFCoordinatePosition(0, 0, 0, 25.06),
            BGFCoordinatePosition(100, 0, 0, 20.0),
        ]
        app._refresh_coord_tree()
        rows_ok = copy.deepcopy(app.coord_rows)
        app.generate_code()
        nc_before = app.output_text.get("1.0", tk.END)
        _ = app.build_bgf_preview_snapshot()
        self.assertEqual(app.coord_rows, rows_ok)
        app.generate_code()
        nc_after = app.output_text.get("1.0", tk.END)
        self.assertEqual(nc_before, nc_after)
        self.assertIn("BEGIN PGM", nc_before)

        # Teilkreis
        app.position_mode_var.set("Teilkreis")
        app.on_position_mode_change(None)
        for key, val in [
            ("diameter", "100"),
            ("count", "4"),
            ("start_angle", "0"),
            ("center_x", "0"),
            ("center_y", "0"),
        ]:
            app.entries[key].delete(0, tk.END)
            app.entries[key].insert(0, val)
        circle_snap = app.build_bgf_preview_snapshot()
        self.assertEqual(len(circle_snap.points), 4)
        self.assertAlmostEqual(circle_snap.points[0].x, 50.0, places=6)
        self.assertAlmostEqual(circle_snap.points[1].y, 50.0, places=6)

        # Einzelposition
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        for key, val in [("single_x", "12.5"), ("single_y", "-8"), ("single_surface_z", "0")]:
            app.entries[key].delete(0, tk.END)
            app.entries[key].insert(0, val)
        single = app.build_bgf_preview_snapshot()
        self.assertEqual(len(single.points), 1)
        self.assertAlmostEqual(single.points[0].x, 12.5)
        self.assertAlmostEqual(single.points[0].y, -8.0)

        # Duplikat
        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        app.coord_rows = [
            BGFCoordinatePosition(1, 2, 0, 25.06),
            BGFCoordinatePosition(1, 2, 0, 25.06),
        ]
        dup = app.build_bgf_preview_snapshot()
        self.assertTrue(dup.points[0].is_duplicate_xyz)

        # 1000 Positionen Fit
        many = [BGFCoordinatePosition(float(i % 50), float(i // 50), 0, 25.06) for i in range(1000)]
        many_snap = build_preview_from_positions(
            many,
            policy=_m10_policy(),
            safe_z=100,
            end_safe_z=100,
            approach_clearance=2,
            mode_label="Koordinatenliste",
            thread_size="M10",
            article_no="5089810000",
            tool_radius=3.9790,
            tool_number=8,
            program_name="MANY",
        )
        self.assertEqual(len(many_snap.points), 1000)
        t1000 = fit_transform([(p.x, p.y) for p in many_snap.points], 900, 650)
        self.assertGreater(t1000.scale, 0)

        root.destroy()

    def test_button_exists(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        self.assertTrue(hasattr(app, "open_bgf_positions_preview"))
        from app_info import APP_NAME

        self.assertEqual(app.root.title(), APP_NAME)
        root.destroy()


class TestPreviewAutoFitCoord4a(unittest.TestCase):
    def test_circle_715_24_15_radius(self):
        xy = compute_circle_xy_positions(
            center_x=0, center_y=0, diameter=715, count=24, start_angle_deg=15
        )
        self.assertEqual(len(xy), 24)
        for x, y in xy:
            r = (x * x + y * y) ** 0.5
            self.assertAlmostEqual(r, 357.5, places=6)
        min_x, max_x, min_y, max_y = compute_bounds(xy)
        self.assertGreater(max_x, 300)
        self.assertLess(min_x, -300)
        self.assertGreater(max_y, 300)
        self.assertLess(min_y, -300)
        self.assertLess(abs(min_x) - 357.5, 20)
        self.assertLess(abs(max_x) - 357.5, 20)

    def test_fit_715_fills_600x500_canvas(self):
        xy = compute_circle_xy_positions(
            center_x=0, center_y=0, diameter=715, count=24, start_angle_deg=15
        )
        t = fit_transform(xy, 600, 500)
        screens = [t.world_to_canvas(x, y) for x, y in xy]
        xs = [p[0] for p in screens]
        ys = [p[1] for p in screens]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        smaller = min(600, 500)
        self.assertGreater(max(width, height), 0.60 * smaller)
        self.assertGreater(min(width, height), 0.55 * smaller)
        self.assertLess(width, 600)
        self.assertLess(height, 500)
        for sx, sy in screens:
            self.assertGreaterEqual(sx, 0)
            self.assertLessEqual(sx, 600)
            self.assertGreaterEqual(sy, 0)
            self.assertLessEqual(sy, 500)

    def test_initial_1x1_then_real_canvas_uses_real_size(self):
        xy = compute_circle_xy_positions(
            center_x=0, center_y=0, diameter=715, count=24, start_angle_deg=15
        )
        self.assertFalse(canvas_is_ready_for_fit(1, 1))
        deferred = resolve_view_after_resize(xy, 1, 1, None, user_view_changed=False)
        self.assertIsNone(deferred)
        # Alter Bug: Fit auf 100×100, dann Resize ohne Re-Fit → Knäuel
        tiny = fit_transform(xy, 100, 100)
        tiny_span = tiny.world_to_canvas(357.5, 0)[0] - tiny.world_to_canvas(-357.5, 0)[0]
        grown_without_refit = tiny.with_canvas_size(600, 500)
        grown_span = (
            grown_without_refit.world_to_canvas(357.5, 0)[0]
            - grown_without_refit.world_to_canvas(-357.5, 0)[0]
        )
        self.assertAlmostEqual(tiny_span, grown_span, places=6)
        self.assertLess(grown_span, 0.30 * 600)

        fitted = resolve_view_after_resize(xy, 600, 500, tiny, user_view_changed=False)
        self.assertIsNotNone(fitted)
        fit_span = fitted.world_to_canvas(357.5, 0)[0] - fitted.world_to_canvas(-357.5, 0)[0]
        self.assertGreater(fit_span, 0.60 * min(600, 500))
        self.assertAlmostEqual(fitted.canvas_w, 600)
        self.assertAlmostEqual(fitted.canvas_h, 500)

    def test_alles_anzeigen_resets_zoom_semantics(self):
        xy = [(0.0, 0.0), (500.0, 0.0), (500.0, 300.0), (0.0, 300.0)]
        base = fit_transform(xy, 600, 500)
        zoomed = base.zoom_at(2.0, 300, 250).pan(40, -20)
        restored = fit_transform(xy, 600, 500)
        self.assertAlmostEqual(restored.scale, base.scale, places=9)
        rel = restored.scale / base.scale
        self.assertAlmostEqual(rel, 1.0, places=9)
        self.assertNotAlmostEqual(zoomed.scale, base.scale, places=6)

    def test_coord_list_rectangle_fills_canvas(self):
        xy = [(0.0, 0.0), (500.0, 0.0), (500.0, 300.0), (0.0, 300.0)]
        t = fit_transform(xy, 600, 500)
        screens = [t.world_to_canvas(x, y) for x, y in xy]
        width = max(p[0] for p in screens) - min(p[0] for p in screens)
        height = max(p[1] for p in screens) - min(p[1] for p in screens)
        self.assertGreater(width, 0.60 * 600)
        self.assertGreater(height, 0.50 * 500)

    def test_negative_extents_fit(self):
        xy = [(-500.0, -300.0), (500.0, 300.0)]
        t = fit_transform(xy, 600, 500)
        c1 = t.world_to_canvas(-500, -300)
        c2 = t.world_to_canvas(500, 300)
        self.assertGreater(c2[0] - c1[0], 0.60 * 600)
        self.assertLess(c2[1], c1[1])  # +Y oben

    def test_origin_not_forced_into_distant_bounds(self):
        xy = [(10000.0, 5000.0), (11000.0, 6000.0)]
        t = fit_transform(xy, 600, 500)
        c0 = t.world_to_canvas(0, 0)
        c_pts = [t.world_to_canvas(x, y) for x, y in xy]
        # Punkte im Canvas, Ursprung darf weit ausserhalb liegen
        for sx, sy in c_pts:
            self.assertGreater(sx, 0)
            self.assertLess(sx, 600)
            self.assertGreater(sy, 0)
            self.assertLess(sy, 500)
        self.assertTrue(c0[0] < -50 or c0[0] > 650 or c0[1] < -50 or c0[1] > 550)

    def test_user_zoom_survives_resize(self):
        xy = compute_circle_xy_positions(
            center_x=0, center_y=0, diameter=715, count=24, start_angle_deg=15
        )
        fitted = fit_transform(xy, 600, 500)
        zoomed = fitted.zoom_at(2.0, 300, 250)
        after = resolve_view_after_resize(xy, 700, 550, zoomed, user_view_changed=True)
        self.assertAlmostEqual(after.scale, zoomed.scale, places=9)


if __name__ == "__main__":
    unittest.main()
