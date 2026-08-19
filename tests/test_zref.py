"""PHASE ZREF.1 – freie Z-Lage der Bearbeitungsebene fuer BGF und BSF."""

from __future__ import annotations

import json
import os
import re
import tempfile
import unittest

from bgf_depth import BGFDepthRequest, evaluate_bgf_depth
from bgf_surface import absolute_from_surface, above_surface
from bsf_blade import (
    apply_workpiece_reference_z,
    calculate_workpiece_bsf_z,
    parse_reference_z,
    spindle_on_z,
    validate_bsf_safe_z_against_reference,
    validate_reference_z,
)
import bsf_generator_verbessert_v3 as gen
from coordinates import (
    BSFCoordinatePosition,
    export_bsf_csv,
    import_bsf_csv_text,
)
from coordinates.bsf_list_document import build_bsf_document, document_to_dict, parse_document_dict
from help_views.bsf_geometry_model import build_bsf_geometry_help_snapshot
from heule_bsf_tools import (
    BSF_TOOL_PROFILES,
    cutting_edge_z_from_measurement_face_z,
    programmed_measurement_face_z_for_cutting_edge,
)
from ui import MODE_BGF, MODE_BSF

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]
TOOL_E = BSF_TOOL_PROFILES["BSF_E_1350_050_16_5_14"]

_Z_RE = re.compile(r"Z([+-]\d+\.\d+)")
_WORKPIECE_NEEDLES = (
    "Durch den Bund tauchen",
    "Spindel einschalten",
    "Messer unten aktivieren",
    "Vorposition vor Kontakt",
    "Senken mit 50 Prozent",
    "Senken auf Fertigmass",
    "Unten freifahren",
)
_DATUM_NEEDLES = ("CYCL DEF 7", "TRANS DATUM", "DATUM SHIFT")


def _policy_m10():
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


def _z_of(line: str) -> float:
    match = _Z_RE.search(line)
    if not match:
        raise AssertionError(f"Kein Z-Wert in: {line}")
    return float(match.group(1))


def _workpiece_z_map(code: str) -> dict:
    found = {}
    for line in code.splitlines():
        for needle in _WORKPIECE_NEEDLES:
            if needle in line:
                found[needle] = _z_of(line)
    return found


def _safe_lines(code: str) -> list:
    return [line for line in code.splitlines() if "Aus der Bohrung" in line or line.startswith("L Z+") and "M30" in line]


def _silence(mb):
    orig = {"err": mb.showerror, "warn": mb.showwarning, "info": mb.showinfo}
    mb.showerror = lambda *a, **k: None
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None
    return orig


def _restore(mb, orig):
    mb.showerror = orig["err"]
    mb.showwarning = orig["warn"]
    mb.showinfo = orig["info"]


def _fill_blade(app, designation=TOOL_C.designation):
    app.bsf_tool_profile_var.set(designation)
    app.on_bsf_tool_profile_change()


def _set_entry(app, key, value):
    app.entries[key].delete(0, "end")
    app.entries[key].insert(0, value)


class TestReferenceZValidation(unittest.TestCase):
    def test_finite_zero_pos_neg(self):
        self.assertIsNone(validate_reference_z(0.0))
        self.assertIsNone(validate_reference_z(20.0))
        self.assertIsNone(validate_reference_z(-20.5))

    def test_nan_inf_blocked(self):
        self.assertIsNotNone(validate_reference_z(float("nan")))
        self.assertIsNotNone(validate_reference_z(float("inf")))
        self.assertIsNotNone(validate_reference_z(float("-inf")))

    def test_decimal_comma(self):
        ok, val, err = parse_reference_z("20,5")
        self.assertTrue(ok)
        self.assertEqual(val, 20.5)
        self.assertIsNone(err)
        ok, val, err = parse_reference_z("-20,5")
        self.assertTrue(ok)
        self.assertEqual(val, -20.5)


class TestBgfSurfaceZDomain(unittest.TestCase):
    def test_zero_regression_m10_20(self):
        ev = evaluate_bgf_depth(BGFDepthRequest(20.0), _policy_m10(), surface_z=0.0)
        self.assertTrue(ev.ok_for_nc)
        self.assertAlmostEqual(ev.thread_end_z, -20.0, places=4)
        self.assertAlmostEqual(ev.nc_mill_start_z, -19.839, places=3)
        self.assertAlmostEqual(ev.nc_drill_z, -22.810, places=3)
        self.assertAlmostEqual(ev.deepest_milling_depth, 21.789, places=3)
        self.assertAlmostEqual(absolute_from_surface(0.0, ev.deepest_milling_depth), -21.789, places=3)

    def test_plus20(self):
        surface_z = 20.0
        ev = evaluate_bgf_depth(BGFDepthRequest(20.0), _policy_m10(), surface_z=surface_z)
        self.assertTrue(ev.ok_for_nc)
        self.assertAlmostEqual(ev.thread_end_z, 0.0, places=4)
        self.assertAlmostEqual(ev.nc_mill_start_z, 0.161, places=3)
        self.assertAlmostEqual(absolute_from_surface(surface_z, ev.deepest_milling_depth), -1.789, places=3)
        self.assertAlmostEqual(ev.nc_drill_z, -2.810, places=3)
        self.assertAlmostEqual(above_surface(surface_z, 5.0), 25.0, places=4)

    def test_minus20(self):
        surface_z = -20.0
        ev = evaluate_bgf_depth(BGFDepthRequest(20.0), _policy_m10(), surface_z=surface_z)
        self.assertTrue(ev.ok_for_nc)
        self.assertAlmostEqual(ev.thread_end_z, -40.0, places=4)
        self.assertAlmostEqual(ev.nc_mill_start_z, -39.839, places=3)
        self.assertAlmostEqual(absolute_from_surface(surface_z, ev.deepest_milling_depth), -41.789, places=3)
        self.assertAlmostEqual(ev.nc_drill_z, -42.810, places=3)
        self.assertAlmostEqual(above_surface(surface_z, 5.0), -15.0, places=4)


class TestBsfReferenceShiftDomain(unittest.TestCase):
    def test_plus20_finish(self):
        wp = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=True)
        shifted = apply_workpiece_reference_z(wp, 20.0)
        self.assertEqual(wp["z_sink_finish"], 38.0)
        self.assertEqual(shifted["z_sink_finish"], 58.0)
        self.assertEqual(shifted["z_clearance"], -3.0)

    def test_minus20_finish(self):
        wp = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=True)
        shifted = apply_workpiece_reference_z(wp, -20.0)
        self.assertEqual(shifted["z_sink_finish"], 18.0)
        self.assertEqual(shifted["z_clearance"], -43.0)

    def test_zero_identity(self):
        wp = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=True)
        shifted = apply_workpiece_reference_z(wp, 0.0)
        self.assertEqual(shifted, wp)

    def test_spindle_on_z(self):
        self.assertEqual(spindle_on_z(0.0), 1.0)
        self.assertEqual(spindle_on_z(20.0), 21.0)
        self.assertEqual(spindle_on_z(-20.0), -19.0)

    def test_tool_profile_invariant(self):
        wp = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=True)
        for tool in (TOOL_C, TOOL_E):
            for ref in (0.0, 20.0, -20.0):
                target = apply_workpiece_reference_z(wp, ref)["z_sink_finish"]
                measurement_face = programmed_measurement_face_z_for_cutting_edge(target, tool)
                self.assertAlmostEqual(
                    cutting_edge_z_from_measurement_face_z(measurement_face, tool),
                    target,
                )


class TestBgfGuiZref(unittest.TestCase):
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
        _set_entry(app, "bgf_thread_depth", "20")
        _set_entry(app, "approach_clearance", "5")
        _set_entry(app, "single_x", "0")
        _set_entry(app, "single_y", "0")
        _set_entry(app, "safe_z", "100")
        _set_entry(app, "end_safe_z", "200")

    def _code(self, surface: str) -> str:
        _set_entry(self.app, "single_surface_z", surface)
        sz = float(str(surface).replace(",", "."))
        _set_entry(self.app, "raw_stock_top_z", f"{sz if sz > 0 else 0.0:g}")
        self.app.generate_bgf_code()
        return self.app.output_text.get("1.0", "end")

    def test_zero_nc_regression(self):
        code = self._code("0")
        self.assertIn("L Z-22.8100 F1348 M", code)
        self.assertIn("L Z-19.8390 R0 FMAX M", code)
        self.assertIn("Z+5.0000", code)
        self.assertIn("CP IPA-360 IZ-1.5000 DR- RR F292 M", code)
        for needle in _DATUM_NEEDLES:
            self.assertNotIn(needle, code)

    def test_plus20_nc(self):
        code = self._code("20")
        self.assertIn("L X+0.0000 Y+0.0000 Z+25.0000 R0 FMAX M13", code)
        self.assertIn("L Z-2.8100 F1348 M", code)
        self.assertIn("L Z+0.1610 R0 FMAX M", code)
        self.assertIn("CP IPA-360 IZ-1.5000 DR- RR F292 M", code)
        for needle in _DATUM_NEEDLES:
            self.assertNotIn(needle, code)

    def test_minus20_nc(self):
        code = self._code("-20")
        self.assertIn("L X+0.0000 Y+0.0000 Z-15.0000 R0 FMAX M13", code)
        self.assertIn("L Z-42.8100 F1348 M", code)
        self.assertIn("L Z-39.8390 R0 FMAX M", code)

    def test_decimal_comma(self):
        code = self._code("20,0")
        self.assertIn("L X+0.0000 Y+0.0000 Z+25.0000 R0 FMAX M13", code)

    def test_circle_common_surface(self):
        app = self.app
        app.position_mode_var.set("Teilkreis")
        app.on_position_mode_change(None)
        _set_entry(app, "circle_surface_z", "20")
        _set_entry(app, "raw_stock_top_z", "20")
        app.generate_bgf_code()
        code = app.output_text.get("1.0", "end")
        self.assertIn("; --- TEILKREIS ---", code)
        self.assertIn("L Z+25.0000 R0 FMAX M13", code)
        self.assertIn("L Z-2.8100 F1348 M", code)

    def test_coordinate_list_keeps_per_position_z(self):
        from coordinates import BGFCoordinatePosition

        app = self.app
        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        app.coord_rows = [
            BGFCoordinatePosition(0.0, 0.0, 20.0, 20.0, None),
            BGFCoordinatePosition(100.0, 0.0, 25.0, 20.0, None),
            BGFCoordinatePosition(200.0, 0.0, -10.0, 20.0, None),
        ]
        _set_entry(app, "raw_stock_top_z", "25")
        app.generate_bgf_code()
        code = app.output_text.get("1.0", "end")
        self.assertIn("surface_z=20", code)
        self.assertIn("surface_z=25", code)
        self.assertIn("surface_z=-10", code)
        self.assertIn("L Z-2.8100 F1348 M", code)
        self.assertIn("L Z+2.1900 F1348 M", code)
        self.assertIn("L Z-32.8100 F1348 M", code)


class TestBsfGuiZref(unittest.TestCase):
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
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.z0_var.set("Z0 ist Unterkante Bund")
        for key, val in (
            ("bund_thickness", "18"),
            ("sink_depth", "38"),
            ("clearance", "23"),
            ("single_x", "0"),
            ("single_y", "0"),
            ("safe_z", "100"),
            ("end_safe_z", "200"),
            ("bsf_reference_z", "0"),
        ):
            _set_entry(app, key, val)
        _fill_blade(app)

    def _generate(self, reference: str, designation=TOOL_C.designation) -> str:
        _set_entry(self.app, "bsf_reference_z", reference)
        _fill_blade(self.app, designation)
        self.app.generate_bsf_code()
        return self.app.output_text.get("1.0", "end")

    def test_zero_regression(self):
        code = self._generate("0")
        wp = _workpiece_z_map(code)
        self.assertAlmostEqual(wp["Senken mit 50 Prozent"], 29.45, places=3)
        self.assertAlmostEqual(wp["Durch den Bund tauchen"], -31.55, places=3)
        self.assertEqual(wp["Spindel einschalten"], 1.0)
        self.assertIn("L Z+100.0000 R0 FMAX ; Aus der Bohrung", code)
        self.assertIn("L Z+200.0000 R0 FMAX M30", code)
        self.assertIn("L X+0.0000 Y+0.0000 Z+100.0000 R0 FMAX", code)
        for needle in _DATUM_NEEDLES:
            self.assertNotIn(needle, code)

    def test_plus20_shifts_workpiece_only(self):
        zero = self._generate("0")
        plus = self._generate("20")
        z0 = _workpiece_z_map(zero)
        z20 = _workpiece_z_map(plus)
        self.assertEqual(set(z0), set(z20))
        for key in z0:
            self.assertAlmostEqual(z20[key], z0[key] + 20.0)
        self.assertIn("L Z+100.0000 R0 FMAX ; Aus der Bohrung", plus)
        self.assertIn("L Z+200.0000 R0 FMAX M30", plus)
        self.assertIn("L X+0.0000 Y+0.0000 Z+100.0000 R0 FMAX", plus)
        self.assertEqual(z20["Spindel einschalten"], 21.0)
        self.assertAlmostEqual(z20["Senken mit 50 Prozent"], 49.45, places=3)

    def test_minus20_shifts_workpiece_only(self):
        zero = self._generate("0")
        minus = self._generate("-20")
        z0 = _workpiece_z_map(zero)
        zm = _workpiece_z_map(minus)
        for key in z0:
            self.assertAlmostEqual(zm[key], z0[key] - 20.0)
        self.assertIn("L Z+100.0000 R0 FMAX ; Aus der Bohrung", minus)
        self.assertEqual(zm["Spindel einschalten"], -19.0)
        self.assertAlmostEqual(zm["Senken mit 50 Prozent"], 9.45, places=3)

    def test_xy_m_feed_unchanged(self):
        zero = self._generate("0")
        plus = self._generate("20")

        def motion_skeleton(code: str):
            lines = []
            for line in code.splitlines():
                stripped = _Z_RE.sub("Z*", line)
                if stripped.startswith("L X") or stripped.startswith("L Y") or "M3" in line or "M5" in line or "M7" in line or "M9" in line or "F" in line:
                    if "BLK FORM" in line:
                        continue
                    lines.append(stripped)
            return lines

        # XY, F, M und Reihenfolge der Werkstueckbewegung bleiben; nur Z-Adresse aendert sich.
        self.assertIn("L X+0.0000 Y+0.0000 Z+100.0000 R0 FMAX", plus)
        self.assertIn("CYCL DEF 9.0 VERWEILZEIT", plus)
        self.assertEqual(zero.count("M5 ; Spindel aus"), plus.count("M5 ; Spindel aus"))
        self.assertEqual(zero.count("M3"), plus.count("M3"))

    def test_tool_profile_offset_with_reference(self):
        for ref in ("0", "20", "-20"):
            a = self._generate(ref, TOOL_C.designation)
            b = self._generate(ref, TOOL_E.designation)
            za = _workpiece_z_map(a)["Senken mit 50 Prozent"]
            zb = _workpiece_z_map(b)["Senken mit 50 Prozent"]
            target = 38.0 + float(ref)
            self.assertAlmostEqual(cutting_edge_z_from_measurement_face_z(za, TOOL_C), target, places=3)
            self.assertAlmostEqual(cutting_edge_z_from_measurement_face_z(zb, TOOL_E), target, places=3)

    def test_safe_z_high_reference_blocked(self):
        import tkinter.messagebox as mb

        _set_entry(self.app, "bsf_reference_z", "120")
        _set_entry(self.app, "safe_z", "100")
        self.app.output_text.delete("1.0", "end")
        orig = _silence(mb)
        try:
            self.app.generate_bsf_code()
        finally:
            _restore(mb, orig)
        self.assertEqual(self.app.output_text.get("1.0", "end").strip(), "")

    def test_safe_z_not_auto_shifted(self):
        code = self._generate("20")
        self.assertIn("L Z+100.0000 R0 FMAX ; Aus der Bohrung", code)
        self.assertNotIn("L Z+120.0000 R0 FMAX ; Aus der Bohrung", code)

    def test_mode_switch_keeps_reference(self):
        _set_entry(self.app, "bsf_reference_z", "-20")
        for mode in ("Teilkreis", "Einzelposition", "Koordinatenliste"):
            self.app.position_mode_var.set(mode)
            self.app.on_position_mode_change(None)
            self.assertEqual(self.app.entries["bsf_reference_z"].get(), "-20")
        self.app.mode_var.set(MODE_BGF)
        self.app.on_mode_change(None)
        self.app.mode_var.set(MODE_BSF)
        self.app.on_mode_change(None)
        self.assertEqual(self.app.entries["bsf_reference_z"].get(), "-20")

    def test_csv_does_not_change_reference(self):
        _set_entry(self.app, "bsf_reference_z", "20")
        text = export_bsf_csv([BSFCoordinatePosition(1.0, 2.0), BSFCoordinatePosition(3.0, 4.0)])
        parsed = import_bsf_csv_text(text)
        self.app.bsf_coord_rows = parsed
        self.assertEqual(self.app.entries["bsf_reference_z"].get(), "20")
        self.assertNotIn("reference_z", text)
        self.assertTrue(text.startswith("Nr;X;Y"))

    def test_all_bsf_modes_use_global_reference(self):
        _set_entry(self.app, "bsf_reference_z", "20")
        codes = []
        self.app.bsf_coord_rows = [BSFCoordinatePosition(0.0, 0.0)]
        for mode in ("Teilkreis", "Einzelposition", "Koordinatenliste"):
            self.app.position_mode_var.set(mode)
            self.app.on_position_mode_change(None)
            self.app.generate_bsf_code()
            codes.append(self.app.output_text.get("1.0", "end"))
        maps = [_workpiece_z_map(c) for c in codes]
        self.assertAlmostEqual(maps[0]["Senken mit 50 Prozent"], 49.45, places=3)
        self.assertAlmostEqual(maps[1]["Senken mit 50 Prozent"], 49.45, places=3)
        self.assertAlmostEqual(maps[2]["Senken mit 50 Prozent"], 49.45, places=3)


class TestBsfJsonReferenceZ(unittest.TestCase):
    def _doc(self, **kwargs):
        base = dict(
            program_name="BSF_TEST",
            tool_number=8,
            blank_size=1000.0,
            blank_height=60.0,
            z_reference="BOTTOM_EDGE",
            tool_profile_key="BSF_C_1000_050_10_5_23",
            bund_thickness=18.0,
            sink_finish=38.0,
            clearance=23.0,
            spindle_speed=800,
            feed=60.0,
            dwell_time=1.5,
            reduce_approach=True,
            approach_feed_factor=0.5,
            activate_preset="IKZ Ein (M7)",
            activate_custom="M107",
            deactivate_preset="Alles AUS (M9)",
            deactivate_custom="M9",
            safe_z=100.0,
            end_safe_z=200.0,
            positions=[BSFCoordinatePosition(0.0, 0.0)],
        )
        base.update(kwargs)
        return build_bsf_document(**base)

    def test_roundtrip_20_5(self):
        doc = self._doc(reference_z=20.5)
        payload = document_to_dict(doc)
        self.assertEqual(payload["workpiece"]["reference_z"], 20.5)
        loaded = parse_document_dict(payload)
        self.assertEqual(loaded.reference_z, 20.5)
        self.assertEqual(loaded.version, 2)

    def test_legacy_defaults_zero(self):
        payload = document_to_dict(self._doc())
        payload["version"] = 1
        payload["blade"] = {"thickness": 3.0, "measurement_reference": "SPINDLE_SIDE_EDGE"}
        del payload["tool"]
        del payload["workpiece"]["reference_z"]
        loaded = parse_document_dict(payload)
        self.assertEqual(loaded.reference_z, 0.0)

    def test_gui_json_roundtrip_keeps_nc(self):
        import tkinter as tk
        import tkinter.messagebox as mb

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        _fill_blade(app)
        _set_entry(app, "bsf_reference_z", "20.5")
        app.bsf_coord_rows = [BSFCoordinatePosition(10.0, 20.0)]
        orig = _silence(mb)
        try:
            app.generate_bsf_code()
            before = app.output_text.get("1.0", "end")
            doc = app._collect_bsf_position_list_document()
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "t.bsf.json")
                from coordinates import save_bsf_document_json, load_bsf_document_json

                save_bsf_document_json(path, doc)
                loaded = load_bsf_document_json(path)
            app._apply_bsf_position_list_document(loaded)
            self.assertEqual(app.entries["bsf_reference_z"].get(), "20.5")
            app.generate_bsf_code()
            after = app.output_text.get("1.0", "end")
        finally:
            _restore(mb, orig)
            root.destroy()
        self.assertEqual(before, after)
        self.assertIn("Z+49.9500", before)

    def test_nan_json_blocked(self):
        payload = document_to_dict(self._doc())
        payload["workpiece"]["reference_z"] = float("nan")
        with self.assertRaises(Exception):
            parse_document_dict(payload)


class TestBgfHelpZref(unittest.TestCase):
    def test_plus20_and_minus20(self):
        from help_views.bgf_geometry_model import build_bgf_geometry_help_snapshot

        data = gen.BGF_DATA["M10"]
        policy = _policy_m10()
        common = dict(
            tool_size=data.size,
            article_no=data.article_no,
            radius=data.radius,
            pitch=data.pitch,
            predrill_depth=data.predrill_depth,
            policy=policy,
            thread_depth=20.0,
            core_hole_depth=None,
            approach_clearance=5.0,
        )
        snap20 = build_bgf_geometry_help_snapshot(surface_z=20.0, **common)
        self.assertAlmostEqual(snap20.approach_z, 25.0, places=4)
        self.assertAlmostEqual(snap20.thread_end_z, 0.0, places=4)
        self.assertAlmostEqual(snap20.mill_start_z, 0.161, places=3)
        self.assertAlmostEqual(snap20.deepest_milling_z, -1.789, places=3)
        self.assertAlmostEqual(snap20.drill_z, -2.810, places=3)
        snap_m = build_bgf_geometry_help_snapshot(surface_z=-20.0, **common)
        self.assertAlmostEqual(snap_m.approach_z, -15.0, places=4)
        self.assertAlmostEqual(snap_m.thread_end_z, -40.0, places=4)
        self.assertAlmostEqual(snap_m.mill_start_z, -39.839, places=3)
        self.assertAlmostEqual(snap_m.deepest_milling_z, -41.789, places=3)
        self.assertAlmostEqual(snap_m.drill_z, -42.810, places=3)


class TestBsfHelpZref(unittest.TestCase):
    def test_help_shows_shifted_z(self):
        snap0 = build_bsf_geometry_help_snapshot(
            bund_text="18",
            sink_text="38",
            clearance_text="23",
            z0_label="Z0 ist Unterkante Bund",
            reference_z_text="0",
            tool_designation=TOOL_C.designation,
        )
        snap20 = build_bsf_geometry_help_snapshot(
            bund_text="18",
            sink_text="38",
            clearance_text="23",
            z0_label="Z0 ist Unterkante Bund",
            reference_z_text="20",
            tool_designation=TOOL_C.designation,
        )
        self.assertAlmostEqual(snap0.programmed_measurement_face_z_sink_finish, 29.45, places=3)
        self.assertAlmostEqual(snap20.programmed_measurement_face_z_sink_finish, 49.45, places=3)
        self.assertEqual(snap20.reference_z, 20.0)
        from help_views.bsf_geometry_model import format_help_info

        info = format_help_info(snap20)
        self.assertIn("Bezugsebene", info)
        self.assertIn("+20.0000", info)
        self.assertIn("+58.0000", info)


class TestSafeZGateDomain(unittest.TestCase):
    def test_high_reference_blocked(self):
        wp = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=True)
        programmed = {
            "z_sink_finish": programmed_measurement_face_z_for_cutting_edge(158.0, TOOL_C),
            "z_clearance": programmed_measurement_face_z_for_cutting_edge(97.0, TOOL_C),
        }
        err = validate_bsf_safe_z_against_reference(
            100.0,
            200.0,
            programmed,
            reference_z=120.0,
            bund_thickness=18.0,
            z0_is_flange_bottom=True,
            reduce_approach=True,
        )
        self.assertIsNotNone(err)

    def test_default_allowed(self):
        programmed = {
            "z_sink_finish": programmed_measurement_face_z_for_cutting_edge(38.0, TOOL_C),
            "z_clearance": programmed_measurement_face_z_for_cutting_edge(-23.0, TOOL_C),
        }
        err = validate_bsf_safe_z_against_reference(
            100.0,
            200.0,
            programmed,
            reference_z=0.0,
            bund_thickness=18.0,
            z0_is_flange_bottom=True,
            reduce_approach=True,
        )
        self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()
