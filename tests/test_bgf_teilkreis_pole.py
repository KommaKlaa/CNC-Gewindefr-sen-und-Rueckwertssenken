"""BGF Teilkreis: Heidenhain-Pol vor jedem LP wiederherstellen.

ROOT CAUSE: Das BGF-Unterprogramm setzt eigene CC IX... und ueberschreibt
den aktiven Teilkreis-Pol. Deshalb muss vor jedem LP ein absolutes CC
auf die Teilkreis-Mitte gesetzt werden.

PART_CIRCLE_POLE_MUST_BE_RESTORED_AFTER_SUBPROGRAM = YES
"""

from __future__ import annotations

import math
import re
import unittest

import tkinter as tk

import bsf_generator_verbessert_v3 as gen
from coordinates.circle_positions import compute_circle_xy_positions
from preview.bgf_preview_model import build_circle_positions_for_preview
from ui import MODE_BGF, MODE_BSF


CC_ABS_RE = re.compile(r"^CC X([+-]\d+\.\d+) Y([+-]\d+\.\d+) ; Teilkreis-Mitte / Pol$")
LP_RE = re.compile(r"^LP PR\+(\d+\.\d+) PA\+Q1 R0 FMAX")
CC_INC_RE = re.compile(r"^CC IX")


def _set(app, key: str, value) -> None:
    app.entries[key].delete(0, tk.END)
    app.entries[key].insert(0, str(value))


def _teilkreis_loop_lines(code: str) -> list[str]:
    lines = [ln.rstrip() for ln in code.splitlines()]
    start = next(i for i, ln in enumerate(lines) if ln.startswith("LBL 1 ;"))
    end = next(i for i, ln in enumerate(lines) if "GOTO LBL 1" in ln)
    return lines[start : end + 1]


def _subprogram_lines(code: str) -> list[str]:
    lines = [ln.rstrip() for ln in code.splitlines()]
    start = next(i for i, ln in enumerate(lines) if ln.startswith("LBL 100 ;"))
    return lines[start:]


def _prepare_bgf_circle(
    app,
    *,
    size: str = "M16",
    diameter: str = "580",
    count: str = "8",
    start_angle: str = "0",
    center_x: str = "0",
    center_y: str = "0",
    surface_z: str = "30",
    thread_depth: str = "22",
    approach_clearance: str = "10",
    blank_size: str = "1500",
    blank_height: str = "60",
) -> str:
    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    app.position_mode_var.set("Teilkreis")
    app.on_position_mode_change(None)
    app.bgf_size_var.set(size)
    app.load_bgf_values()
    _set(app, "diameter", diameter)
    _set(app, "count", count)
    _set(app, "start_angle", start_angle)
    _set(app, "center_x", center_x)
    _set(app, "center_y", center_y)
    _set(app, "circle_surface_z", surface_z)
    _set(app, "bgf_thread_depth", thread_depth)
    _set(app, "approach_clearance", approach_clearance)
    _set(app, "blank_size", blank_size)
    _set(app, "blank_height", blank_height)
    _set(app, "raw_stock_top_z", surface_z)
    _set(app, "program_name", "LPR_5_AUF_M16")
    app.generate_bgf_code()
    return app.output_text.get("1.0", tk.END)


class TestBgfTeilkreisPoleRestore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_absolute_cc_immediately_before_each_lp(self):
        code = _prepare_bgf_circle(self.app)
        loop = _teilkreis_loop_lines(code)
        self.assertEqual(loop[0], "LBL 1 ; Schleifenanfang Teilkreis")
        self.assertEqual(loop[1], "CC X+0.0000 Y+0.0000 ; Teilkreis-Mitte / Pol")
        self.assertEqual(loop[2], "LP PR+290.0000 PA+Q1 R0 FMAX ; Teilkreisposition")
        self.assertEqual(loop[3], "CALL LBL 100 ; Bearbeitung aufrufen")
        self.assertEqual(loop[4], "Q1 = Q1 + 45.0000 ; Naechster Winkel")
        self.assertEqual(loop[5], "Q2 = Q2 + 1 ; Zaehler erhoehen")
        self.assertEqual(loop[6], "FN 12: IF +Q2 LT +8 GOTO LBL 1 ; exakt 8 Bohrungen")

        header = code.split("LBL 1 ;")[0]
        self.assertNotIn("CC X+0.0000 Y+0.0000", header)

    def test_subprogram_modifies_cc_so_pole_must_be_restored(self):
        code = _prepare_bgf_circle(self.app)
        sub = _subprogram_lines(code)
        inc_cc = [ln for ln in sub if CC_INC_RE.match(ln)]
        self.assertGreaterEqual(len(inc_cc), 1)
        self.assertTrue(
            any("CC IX" in ln for ln in sub),
            "BGF machining subroutine modifies CC; pole restore is mandatory.",
        )

    def test_nonzero_center_restores_absolute_pole(self):
        code = _prepare_bgf_circle(self.app, center_x="100", center_y="-50")
        loop = _teilkreis_loop_lines(code)
        self.assertEqual(loop[1], "CC X+100.0000 Y-50.0000 ; Teilkreis-Mitte / Pol")
        self.assertTrue(loop[2].startswith("LP PR+290.0000 PA+Q1"))
        self.assertNotRegex(loop[1], r"CC IX|CC IY")

    def test_start_angles_keep_pole_restore(self):
        for start in ("0", "30", "45", "-30"):
            with self.subTest(start=start):
                code = _prepare_bgf_circle(self.app, start_angle=start)
                loop = _teilkreis_loop_lines(code)
                self.assertEqual(loop[1], "CC X+0.0000 Y+0.0000 ; Teilkreis-Mitte / Pol")
                self.assertTrue(loop[2].startswith("LP PR+290.0000 PA+Q1"))
                q1 = next(ln for ln in code.splitlines() if ln.startswith("Q1 = "))
                expected = gen.fmt_q(float(start))
                self.assertTrue(q1.startswith(f"Q1 = {expected}"))

    def test_exact_position_count(self):
        for count in (1, 4, 8, 24):
            with self.subTest(count=count):
                code = _prepare_bgf_circle(self.app, count=str(count))
                loop = _teilkreis_loop_lines(code)
                self.assertEqual(loop[2].count("LP PR+"), 1)
                self.assertIn(f"FN 12: IF +Q2 LT +{count} GOTO LBL 1", loop[-1])
                self.assertEqual(code.count("CALL LBL 100 ; Bearbeitung aufrufen"), 1)

    def test_center_variants(self):
        cases = (("0", "0"), ("100", "0"), ("0", "-50"), ("100", "-50"))
        for cx, cy in cases:
            with self.subTest(center=(cx, cy)):
                code = _prepare_bgf_circle(self.app, center_x=cx, center_y=cy)
                loop = _teilkreis_loop_lines(code)
                expected = (
                    f"CC {gen.fmt_axis('X', float(cx))} {gen.fmt_axis('Y', float(cy))} "
                    "; Teilkreis-Mitte / Pol"
                )
                self.assertEqual(loop[1], expected)
                self.assertTrue(CC_ABS_RE.match(loop[1]))

    def test_mathematical_positions_match_preview(self):
        expected = [
            (290.0, 0.0),
            (290.0 * math.cos(math.radians(45)), 290.0 * math.sin(math.radians(45))),
            (0.0, 290.0),
            (-290.0 * math.cos(math.radians(45)), 290.0 * math.sin(math.radians(45))),
            (-290.0, 0.0),
            (-290.0 * math.cos(math.radians(45)), -290.0 * math.sin(math.radians(45))),
            (0.0, -290.0),
            (290.0 * math.cos(math.radians(45)), -290.0 * math.sin(math.radians(45))),
        ]
        xy = compute_circle_xy_positions(
            center_x=0.0, center_y=0.0, diameter=580.0, count=8, start_angle_deg=0.0
        )
        self.assertEqual(len(xy), 8)
        for (x, y), (ex, ey) in zip(xy, expected):
            self.assertAlmostEqual(x, ex, places=5)
            self.assertAlmostEqual(y, ey, places=5)
        self.assertAlmostEqual(xy[1][0], 205.060965, places=5)
        self.assertAlmostEqual(xy[1][1], 205.060965, places=5)

        preview = build_circle_positions_for_preview(
            center_x=0.0,
            center_y=0.0,
            diameter=580.0,
            count=8,
            start_angle_deg=0.0,
            thread_depth=22.0,
            core_hole_depth=None,
            surface_z=30.0,
        )
        self.assertEqual([(p.x, p.y) for p in preview], xy)

    def test_preview_unchanged_by_nc_pole_restore(self):
        _prepare_bgf_circle(self.app)
        snap = self.app.build_bgf_preview_snapshot()
        self.assertEqual(len(snap.points), 8)
        self.assertAlmostEqual(snap.points[0].x, 290.0, places=6)
        self.assertAlmostEqual(snap.points[0].y, 0.0, places=6)
        self.assertAlmostEqual(snap.points[2].x, 0.0, places=6)
        self.assertAlmostEqual(snap.points[2].y, 290.0, places=6)

    def test_bgf_subroutine_incremental_path_unchanged(self):
        code = _prepare_bgf_circle(self.app)
        data = gen.BGF_DATA["M16"]
        seq = self.app.get_bgf_sequence(
            data,
            8,
            surface_z=30.0,
            approach_clearance=10.0,
            drill_depth=None,
            mill_start_depth=None,
        )
        mill = [ln for ln in seq if ln.startswith("CC IX") or ln.startswith("CP IPA") or ln.startswith("L IX")]
        sub = _subprogram_lines(code)
        sub_mill = [ln for ln in sub if ln.startswith("CC IX") or ln.startswith("CP IPA") or ln.startswith("L IX")]
        self.assertEqual(sub_mill, mill)
        self.assertTrue(any(ln.startswith("CC IX") for ln in mill))

    def test_bgf_single_position_has_no_part_circle_loop(self):
        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.bgf_size_var.set("M16")
        app.load_bgf_values()
        _set(app, "single_x", "0")
        _set(app, "single_y", "0")
        _set(app, "single_surface_z", "30")
        _set(app, "raw_stock_top_z", "30")
        _set(app, "bgf_thread_depth", "22")
        _set(app, "approach_clearance", "10")
        app.generate_bgf_code()
        code = app.output_text.get("1.0", tk.END)
        self.assertIn("; --- EINZELPOSITION ---", code)
        self.assertNotIn("LBL 1 ;", code)
        self.assertNotIn("LP PR+", code)
        self.assertNotIn("CALL LBL 100", code)

    def test_bgf_coord_list_unchanged_no_lp_loop(self):
        from coordinates import BGFCoordinatePosition

        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        app.bgf_size_var.set("M16")
        app.load_bgf_values()
        _set(app, "approach_clearance", "10")
        _set(app, "raw_stock_top_z", "30")
        app.coord_rows = [
            BGFCoordinatePosition(0, 0, 30.0, 22.0),
            BGFCoordinatePosition(100, 50, 30.0, 22.0),
        ]
        app.generate_bgf_code()
        code = app.output_text.get("1.0", tk.END)
        self.assertIn("; --- KOORDINATENLISTE BGF ---", code)
        self.assertIn("L X+0.0000 Y+0.0000 R0 FMAX", code)
        self.assertIn("L X+100.0000 Y+50.0000 R0 FMAX", code)
        self.assertNotIn("LP PR+", code)
        self.assertNotIn("CALL LBL 100", code)

    def test_user_repro_nc_and_blk_form_audit(self):
        code = _prepare_bgf_circle(self.app)
        self.assertIn("BEGIN PGM LPR_5_AUF_M16 MM", code)
        self.assertIn("CC X+0.0000 Y+0.0000 ; Teilkreis-Mitte / Pol", code)
        self.assertIn("LP PR+290.0000 PA+Q1 R0 FMAX ; Teilkreisposition", code)
        self.assertIn("FN 12: IF +Q2 LT +8 GOTO LBL 1", code)
        blk = [ln for ln in code.splitlines() if ln.startswith("BLK FORM")]
        self.assertEqual(len(blk), 2)
        self.assertIn("X-750.0000", blk[0])
        self.assertIn("Y-750.0000", blk[0])
        self.assertIn("X+750.0000", blk[1])
        self.assertIn("Y+750.0000", blk[1])


class TestBsfTeilkreisPoleAudit(unittest.TestCase):
    def test_bsf_subroutine_does_not_emit_cc(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = gen.BSFGeneratorGUI(root)
            app.mode_var.set(MODE_BSF)
            app.on_mode_change(None)
            app.position_mode_var.set("Teilkreis")
            app.on_position_mode_change(None)
            app.bsf_tool_profile_var.set("BSF-C-1000/050-10.5-23")
            app.on_bsf_tool_profile_change()
            app.generate_bsf_code()
            code = app.output_text.get("1.0", tk.END)
            sub = _subprogram_lines(code)
            self.assertTrue(sub[0].startswith("LBL 100 ; Unterprogramm BSF"))
            self.assertFalse(any(ln.startswith("CC ") for ln in sub))
            header = code.split("LBL 1 ;")[0]
            self.assertIn("CC X+0.0000 Y+0.0000 ; Teilkreis-Mitte / Pol", header)
            loop = _teilkreis_loop_lines(code)
            self.assertTrue(loop[1].startswith("LP PR+"))
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
