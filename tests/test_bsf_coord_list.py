"""PHASE BSF.COORD.1 – HEULE BSF Koordinatenliste (X/Y)."""

from __future__ import annotations

import re
import unittest

from bsf_blade import MEASUREMENT_LABELS, MEASUREMENT_PLACEHOLDER, BladeMeasurementReference
import bsf_generator_verbessert_v3 as gen
from coordinates import (
    BGFCoordinatePosition,
    BSFCoordinatePosition,
    CoordinateParseError,
    parse_coordinate_text,
)
from coordinates.bsf_list_nc import emit_bsf_coordinate_program_body
from preview.bgf_preview_transform import fit_transform
from ui import MODE_BGF, MODE_BSF, POSITION_LABELS_BSF
from ui.visibility import is_mapped


TEST_BLADE_THICKNESS = 3.0
SPINDLE_LABEL = MEASUREMENT_LABELS[BladeMeasurementReference.SPINDLE_SIDE_EDGE]
TIP_LABEL = MEASUREMENT_LABELS[BladeMeasurementReference.TOOL_TIP_SIDE_EDGE]

_Z_RE = re.compile(r"Z([+-]\d+\.\d+)")
_XY_WITH_Z = re.compile(r"\sZ[+-]")


def _z_of(line: str) -> float:
    match = _Z_RE.search(line)
    if not match:
        raise AssertionError(f"Kein Z-Wert in: {line}")
    return float(match.group(1))


def _machining_sequence(code: str) -> list[str]:
    lines = code.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("M5 ; Spindel aus"))
    end = next(i for i, line in enumerate(lines) if "Aus der Bohrung" in line)
    return lines[start : end + 1]


def _fill_blade(app, thickness: str, label: str) -> None:
    app.entries["blade_thickness"].delete(0, "end")
    app.entries["blade_thickness"].insert(0, thickness)
    app.blade_measurement_var.set(label)


def _silence_boxes():
    import tkinter.messagebox as mb

    orig = {
        "error": mb.showerror,
        "warn": mb.showwarning,
        "info": mb.showinfo,
        "yesno": mb.askyesno,
    }
    mb.showerror = lambda *a, **k: None
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None
    mb.askyesno = lambda *a, **k: True
    return mb, orig


def _restore_boxes(mb, orig) -> None:
    mb.showerror = orig["error"]
    mb.showwarning = orig["warn"]
    mb.showinfo = orig["info"]
    mb.askyesno = orig["yesno"]


class TestBsfCoordEmitHelper(unittest.TestCase):
    def test_order_and_first_approach_at_safe_z(self):
        positions = [
            BSFCoordinatePosition(0, 0),
            BSFCoordinatePosition(100, 0),
        ]
        body = emit_bsf_coordinate_program_body(
            positions,
            sequence_lines=["M5 ; Spindel aus", "L Z+100.0000 R0 FMAX ; Aus der Bohrung"],
            safe_z=100.0,
            fmt_axis=gen.fmt_axis,
        )
        self.assertEqual(body[0], "; --- KOORDINATENLISTE BSF ---")
        self.assertIn("; POSITIONIERUNG: KOORDINATENLISTE", body)
        self.assertIn("; ANZAHL POSITIONEN: 2", body)
        self.assertIn("L X+0.0000 Y+0.0000 Z+100.0000 R0 FMAX", body)
        self.assertIn("L X+100.0000 Y+0.0000 R0 FMAX", body)
        self.assertLess(
            body.index("L X+0.0000 Y+0.0000 Z+100.0000 R0 FMAX"),
            body.index("L X+100.0000 Y+0.0000 R0 FMAX"),
        )


class TestBsfCoordGui(unittest.TestCase):
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
        for key, val in (
            ("bund_thickness", "18"),
            ("sink_depth", "38"),
            ("clearance", "23"),
            ("safe_z", "100"),
            ("end_safe_z", "200"),
        ):
            app.entries[key].delete(0, "end")
            app.entries[key].insert(0, val)
        app.bsf_coord_rows = []
        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        _fill_blade(app, "3", SPINDLE_LABEL)

    def _generate(self) -> str:
        mb, orig = _silence_boxes()
        try:
            self.app.generate_bsf_code()
        finally:
            _restore_boxes(mb, orig)
        return self.app.output_text.get("1.0", "end")

    def test_combo_has_three_bsf_modes(self):
        self.assertEqual(tuple(self.app.position_mode_combo.cget("values")), POSITION_LABELS_BSF)
        self.assertTrue(is_mapped(self.app.coord_list_frame))
        self.assertTrue(is_mapped(self.app.bsf_coord_inner))

    def test_empty_list_blocks_nc(self):
        self.app.output_text.delete("1.0", "end")
        code = self._generate()
        self.assertEqual(code.strip(), "")

    def test_single_position_equivalence(self):
        app = self.app
        app.bsf_coord_rows = [BSFCoordinatePosition(100.0, 50.0)]
        list_code = self._generate()
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.entries["single_x"].delete(0, "end")
        app.entries["single_x"].insert(0, "100")
        app.entries["single_y"].delete(0, "end")
        app.entries["single_y"].insert(0, "50")
        single = self._generate()
        self.assertEqual(_machining_sequence(list_code), _machining_sequence(single))
        self.assertIn("L X+100.0000 Y+50.0000 Z+100.0000 R0 FMAX", list_code)
        self.assertIn("L X+100.0000 Y+50.0000 Z+100.0000 R0 FMAX", single)
        self.assertIn("; SCHWERTDICKE AXIAL: 3.0000 MM", list_code)
        self.assertEqual(list_code.count("; SCHWERTDICKE AXIAL: 3.0000 MM"), 1)
        self.assertIn("; POSITIONIERUNG: KOORDINATENLISTE", list_code)
        self.assertNotIn("; POSITIONIERUNG: KOORDINATENLISTE", single)

    def test_multiple_positions_order_preserved(self):
        self.app.bsf_coord_rows = [
            BSFCoordinatePosition(0, 0),
            BSFCoordinatePosition(100, 0),
            BSFCoordinatePosition(100, 50),
            BSFCoordinatePosition(0, 50),
        ]
        code = self._generate()
        i1 = code.index("; POSITION 1  X+0.0000 Y+0.0000")
        i2 = code.index("; POSITION 2  X+100.0000 Y+0.0000")
        i3 = code.index("; POSITION 3  X+100.0000 Y+50.0000")
        i4 = code.index("; POSITION 4  X+0.0000 Y+50.0000")
        self.assertLess(i1, i2)
        self.assertLess(i2, i3)
        self.assertLess(i3, i4)
        self.assertIn("; ANZAHL POSITIONEN: 4", code)

    def test_negative_coordinates(self):
        self.app.bsf_coord_rows = [BSFCoordinatePosition(-100.5, -50.25)]
        code = self._generate()
        self.assertIn("L X-100.5000 Y-50.2500 Z+100.0000 R0 FMAX", code)

    def test_decimal_comma_paste(self):
        n = self.app.import_bsf_coordinate_text("-100,5;50,25")
        self.assertEqual(n, 1)
        self.assertEqual(self.app.bsf_coord_rows[0], BSFCoordinatePosition(-100.5, 50.25))

    def test_atomic_paste_keeps_existing_list(self):
        self.app.bsf_coord_rows = [BSFCoordinatePosition(1.0, 2.0)]
        with self.assertRaises(CoordinateParseError):
            self.app.import_bsf_coordinate_text("0;0\n100;ABC\n200;50")
        self.assertEqual(self.app.bsf_coord_rows, [BSFCoordinatePosition(1.0, 2.0)])

    def test_header_paste(self):
        self.app.import_bsf_coordinate_text("X;Y\n0;0\n100;50")
        self.assertEqual(
            self.app.bsf_coord_rows,
            [BSFCoordinatePosition(0.0, 0.0), BSFCoordinatePosition(100.0, 50.0)],
        )

    def test_nan_inf_paste_blocked(self):
        for raw in ("NaN;0", "0;Inf", "1;-Infinity"):
            with self.assertRaises(CoordinateParseError):
                parse_coordinate_text(raw)

    def test_blade_fail_closed_with_valid_xy(self):
        app = self.app
        app.bsf_coord_rows = [
            BSFCoordinatePosition(0, 0),
            BSFCoordinatePosition(100, 50),
        ]
        app.entries["blade_thickness"].delete(0, "end")
        app.output_text.delete("1.0", "end")
        code = self._generate()
        self.assertEqual(code.strip(), "")

        _fill_blade(app, "3", MEASUREMENT_PLACEHOLDER)
        app.output_text.delete("1.0", "end")
        code = self._generate()
        self.assertEqual(code.strip(), "")

    def test_measurement_refs_same_offset_all_positions(self):
        positions = [BSFCoordinatePosition(0, 0), BSFCoordinatePosition(100, 50)]
        self.app.bsf_coord_rows = list(positions)
        _fill_blade(self.app, "3", SPINDLE_LABEL)
        spindle = self._generate()
        _fill_blade(self.app, "3", TIP_LABEL)
        tip = self._generate()

        def finish_values(code: str) -> list[float]:
            return [
                _z_of(line)
                for line in code.splitlines()
                if "Senken mit 50 Prozent Vorschub" in line
            ]

        zs = finish_values(spindle)
        zt = finish_values(tip)
        self.assertEqual(len(zs), 2)
        self.assertEqual(len(zt), 2)
        self.assertEqual(zs[0], zs[1])
        self.assertEqual(zt[0], zt[1])
        self.assertAlmostEqual(abs(zs[0] - zt[0]), TEST_BLADE_THICKNESS)

    def test_safe_xy_transfer_structural(self):
        self.app.bsf_coord_rows = [
            BSFCoordinatePosition(0, 0),
            BSFCoordinatePosition(100, 0),
            BSFCoordinatePosition(100, 50),
        ]
        code = self._generate()
        lines = code.splitlines()
        pos_starts = [i for i, line in enumerate(lines) if line.startswith("; POSITION ")]
        self.assertEqual(len(pos_starts), 3)
        for i, start in enumerate(pos_starts[:-1]):
            nxt = pos_starts[i + 1]
            block = lines[start:nxt]
            z_moves = [line for line in block if line.startswith("L Z")]
            self.assertTrue(z_moves)
            last_z = z_moves[-1]
            self.assertIn("Aus der Bohrung", last_z)
            self.assertIn("Z+100.0000", last_z)
            self.assertTrue(any("Messer schliessen" in line for line in block))
            close_idx = next(j for j, line in enumerate(block) if "Messer schliessen" in line)
            self.assertLess(close_idx, block.index(last_z))
            after = block[block.index(last_z) + 1 :]
            for line in after:
                self.assertFalse(line.startswith("L X"), line)
            next_xy = next(line for line in lines[nxt:] if line.startswith("L X"))
            self.assertIsNone(_XY_WITH_Z.search(next_xy), next_xy)
            self.assertNotIn("38.0000", next_xy)

    def test_m_functions_copied_per_position(self):
        self.app.bsf_coord_rows = [BSFCoordinatePosition(0, 0)]
        single_list = self._generate()
        seq = _machining_sequence(single_list)
        self.app.bsf_coord_rows = [
            BSFCoordinatePosition(0, 0),
            BSFCoordinatePosition(10, 10),
        ]
        multi = self._generate()
        self.assertEqual(multi.count("M5 ; Spindel aus"), 2 * seq.count("M5 ; Spindel aus"))
        self.assertEqual(multi.count("M7 ; Messer unten aktivieren"), 2)
        self.assertEqual(multi.count("M9 ; Messer schliessen"), 2)
        self.assertEqual(multi.count("CYCL DEF 9.0 VERWEILZEIT"), 2)

    def test_crud_order_and_edit(self):
        app = self.app
        app.import_bsf_coordinate_text("0;0\n100;0\n100;50\n0;50\n10,5;20,25")
        self.assertEqual(len(app.bsf_coord_rows), 5)
        app.bsf_coord_rows[1] = BSFCoordinatePosition(110.0, 5.0)
        del app.bsf_coord_rows[4]
        app._refresh_bsf_coord_tree()
        self.assertEqual(
            [(p.x, p.y) for p in app.bsf_coord_rows],
            [(0.0, 0.0), (110.0, 5.0), (100.0, 50.0), (0.0, 50.0)],
        )
        code = self._generate()
        self.assertIn("; POSITION 2  X+110.0000 Y+5.0000", code)
        self.assertNotIn("X+10.5000", code)

    def test_preview_four_points_bsf_header(self):
        from preview.bgf_preview_window import BGFPreviewWindow

        self.app.bsf_coord_rows = [
            BSFCoordinatePosition(0, 0),
            BSFCoordinatePosition(100, 0),
            BSFCoordinatePosition(100, 100),
            BSFCoordinatePosition(0, 100),
        ]
        snap = self.app.build_bsf_preview_snapshot()
        self.assertEqual(snap.process_kind, "BSF")
        self.assertEqual(len(snap.points), 4)
        self.assertEqual([p.index for p in snap.points], [1, 2, 3, 4])
        self.assertEqual([(p.x, p.y) for p in snap.points], [(0, 0), (100, 0), (100, 100), (0, 100)])
        self.assertTrue(snap.nc_allowed)
        t = fit_transform([(p.x, p.y) for p in snap.points], 600, 500)
        screens = [t.world_to_canvas(p.x, p.y) for p in snap.points]
        width = max(s[0] for s in screens) - min(s[0] for s in screens)
        height = max(s[1] for s in screens) - min(s[1] for s in screens)
        self.assertGreater(width, 0.50 * min(600, 500))
        self.assertGreater(height, 0.50 * min(600, 500))

        win = BGFPreviewWindow(self.root, snapshot_provider=self.app.build_bsf_preview_snapshot)
        win.win.update_idletasks()
        win.canvas.config(width=600, height=500)
        win.win.update_idletasks()
        win.fit_to_positions()
        self.assertEqual(win.win.title(), "BSF Positionsvorschau")
        self.assertIn("HEULE BSF", win.header_tool.cget("text"))
        self.assertNotIn("CERATIZIT", win.header_tool.cget("text"))
        self.assertIn("Schwertdicke", win.header_prog.cget("text"))
        self.assertGreaterEqual(len(win.canvas.find_withtag("pos")), 4)
        if win.transform:
            cx, cy = win.transform.world_to_canvas(0, 0)
            win._on_left_click(type("E", (), {"x": int(cx), "y": int(cy)})())
        detail = win.detail.get("1.0", "end")
        self.assertIn("Position 1", detail)
        self.assertIn("Bunddicke", detail)
        self.assertNotIn("Gewindetiefe", detail)
        win.win.destroy()

    def test_duplicates_are_warning_not_blocked(self):
        self.app.bsf_coord_rows = [
            BSFCoordinatePosition(100, 50),
            BSFCoordinatePosition(100, 50),
        ]
        code = self._generate()
        self.assertIn("BEGIN PGM", code)
        labels = [self.app.bsf_coord_tree.item(iid)["values"][-1] for iid in self.app.bsf_coord_tree.get_children()]
        self.assertTrue(all("Doppelte XY-Position" in str(v) for v in labels))

    def test_bsf_circle_regression(self):
        app = self.app
        app.position_mode_var.set("Teilkreis")
        app.on_position_mode_change(None)
        code = self._generate()
        self.assertIn("; --- TEILKREIS ---", code)
        self.assertIn("LP PR+", code)
        self.assertIn("PA+Q1", code)
        self.assertIn("FN 12:", code)
        self.assertIn("LBL 100 ; Unterprogramm BSF", code)
        self.assertNotIn("; --- KOORDINATENLISTE BSF ---", code)

    def test_bsf_single_geom1_regression(self):
        app = self.app
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.entries["single_x"].delete(0, "end")
        app.entries["single_x"].insert(0, "0")
        app.entries["single_y"].delete(0, "end")
        app.entries["single_y"].insert(0, "0")
        code = self._generate()
        self.assertIn("L Z+38.0000 R0 F30 ; Senken mit 50 Prozent Vorschub", code)
        self.assertIn("L Z-23.0000 R0 FMAX ; Durch den Bund tauchen", code)
        self.assertIn("L Z+100.0000 R0 FMAX ; Aus der Bohrung", code)

    def test_bgf_coord_list_unchanged(self):
        app = self.app
        bgf_rows = [
            BGFCoordinatePosition(10, 20, 0.0, 20.0),
        ]
        app.coord_rows = list(bgf_rows)
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.bgf_size_var.set("M10")
        app.load_bgf_values()
        app.entries["bgf_thread_depth"].delete(0, "end")
        app.entries["bgf_thread_depth"].insert(0, "20")
        app.entries["approach_clearance"].delete(0, "end")
        app.entries["approach_clearance"].insert(0, "5")
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        for k, v in (("single_x", "0"), ("single_y", "0"), ("single_surface_z", "0")):
            app.entries[k].delete(0, "end")
            app.entries[k].insert(0, v)
        mb, orig = _silence_boxes()
        try:
            app.generate_bgf_code()
        finally:
            _restore_boxes(mb, orig)
        code = app.output_text.get("1.0", "end")
        self.assertIn("L Z-22.8100 F1348 M", code)
        self.assertIn("L Z-19.8390 R0 FMAX M", code)
        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        self.assertTrue(is_mapped(app.bgf_coord_inner))
        self.assertFalse(is_mapped(app.bsf_coord_inner))
        self.assertEqual(app.coord_rows, bgf_rows)
        self.assertEqual(app.coord_tree["columns"], ("nr", "x", "y", "sz", "td", "ch", "status"))


class TestBsfCoordGuiSmoke(unittest.TestCase):
    """Startet die echte Anwendung und geht den GUI-Smoke-Pfad durch."""

    def test_full_smoke(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        self.assertEqual(tuple(app.position_mode_combo.cget("values")), POSITION_LABELS_BSF)

        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        self.assertTrue(is_mapped(app.bsf_coord_inner))

        app.import_bsf_coordinate_text("0;0\n100;0\n100;50\n0;50\n10,5;20,25")
        self.assertEqual(len(app.bsf_coord_rows), 5)
        app.bsf_coord_rows[2] = BSFCoordinatePosition(100.0, 55.0)
        del app.bsf_coord_rows[4]
        app._refresh_bsf_coord_tree()
        self.assertEqual(len(app.bsf_coord_rows), 4)
        self.assertEqual(app.bsf_coord_rows[2].y, 55.0)

        for key, val in (("bund_thickness", "18"), ("sink_depth", "38"), ("clearance", "23")):
            app.entries[key].delete(0, "end")
            app.entries[key].insert(0, val)
        _fill_blade(app, "3", SPINDLE_LABEL)

        mb, orig = _silence_boxes()
        try:
            app.generate_bsf_code()
        finally:
            _restore_boxes(mb, orig)
        code = app.output_text.get("1.0", "end")
        self.assertIn("BEGIN PGM", code)
        self.assertIn("; POSITION 1", code)
        self.assertIn("; POSITION 4", code)
        self.assertIn("L X+100.0000 Y+55.0000 R0 FMAX", code)
        self.assertIn("Z+100.0000", code)
        lines = code.splitlines()
        pos2 = next(i for i, line in enumerate(lines) if line.startswith("; POSITION 2"))
        xy2 = next(line for line in lines[pos2:] if line.startswith("L X"))
        self.assertIsNone(_XY_WITH_Z.search(xy2), xy2)

        snap = app.build_bsf_preview_snapshot()
        self.assertEqual(len(snap.points), 4)
        self.assertEqual(snap.process_kind, "BSF")
        t = fit_transform([(p.x, p.y) for p in snap.points], 600, 500)
        self.assertGreater(t.scale, 0)

        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.entries["single_x"].delete(0, "end")
        app.entries["single_x"].insert(0, "0")
        app.entries["single_y"].delete(0, "end")
        app.entries["single_y"].insert(0, "0")
        mb, orig = _silence_boxes()
        try:
            app.generate_bsf_code()
        finally:
            _restore_boxes(mb, orig)
        single = app.output_text.get("1.0", "end")
        self.assertIn("; --- EINZELPOSITION ---", single)
        self.assertIn("L Z+38.0000 R0 F30 ; Senken mit 50 Prozent Vorschub", single)

        app.position_mode_var.set("Teilkreis")
        app.on_position_mode_change(None)
        mb, orig = _silence_boxes()
        try:
            app.generate_bsf_code()
        finally:
            _restore_boxes(mb, orig)
        circle = app.output_text.get("1.0", "end")
        self.assertIn("; --- TEILKREIS ---", circle)
        self.assertIn("FN 12:", circle)

        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        self.assertTrue(is_mapped(app.bgf_coord_inner))
        self.assertEqual(app.coord_tree["columns"], ("nr", "x", "y", "sz", "td", "ch", "status"))
        root.destroy()


if __name__ == "__main__":
    unittest.main()
