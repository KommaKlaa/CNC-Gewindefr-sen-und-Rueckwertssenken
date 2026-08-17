"""PHASE BSF.GEOM.1 – Schwertgeometrie, Offset, Z-Invarianten, NC-Kopf."""

from __future__ import annotations

import math
import re
import unittest

from bsf_blade import (
    FINISH_EDGE,
    MEASUREMENT_LABELS,
    MEASUREMENT_PLACEHOLDER,
    BladeMeasurementReference,
    BSFBladeError,
    apply_blade_offset,
    blade_reference_offset,
    calculate_workpiece_bsf_z,
    parse_blade_thickness,
    parse_measurement_reference,
    physical_finish_edge_z,
    validate_blade_thickness,
)
import bsf_generator_verbessert_v3 as gen
from ui import MODE_BSF


# TESTWERT, kein Herstellerwert.
TEST_BLADE_THICKNESS = 3.0

SPINDLE_LABEL = MEASUREMENT_LABELS[BladeMeasurementReference.SPINDLE_SIDE_EDGE]
TIP_LABEL = MEASUREMENT_LABELS[BladeMeasurementReference.TOOL_TIP_SIDE_EDGE]


def _z_line(code: str, needle: str) -> str:
    for line in code.splitlines():
        if needle in line:
            return line
    raise AssertionError(f"Zeile nicht gefunden: {needle}")


def _parse_z(line: str) -> float:
    match = re.search(r"Z([+-]\d+\.\d+)", line)
    if not match:
        raise AssertionError(f"Kein Z-Wert in: {line}")
    return float(match.group(1))


def _fill_blade(app, thickness: str, label: str) -> None:
    app.entries["blade_thickness"].delete(0, "end")
    app.entries["blade_thickness"].insert(0, thickness)
    app.blade_measurement_var.set(label)


class TestBladeValidation(unittest.TestCase):
    def test_thickness_pass(self):
        self.assertIsNone(validate_blade_thickness(3.0))
        self.assertIsNone(validate_blade_thickness(0.1))
        ok, val, err = parse_blade_thickness("3,0")
        self.assertTrue(ok)
        self.assertEqual(val, 3.0)
        self.assertIsNone(err)

    def test_thickness_block(self):
        self.assertIsNotNone(validate_blade_thickness(0))
        self.assertIsNotNone(validate_blade_thickness(-1))
        self.assertIsNotNone(validate_blade_thickness(float("nan")))
        self.assertIsNotNone(validate_blade_thickness(float("inf")))
        self.assertFalse(parse_blade_thickness("")[0])
        self.assertFalse(parse_blade_thickness("abc")[0])

    def test_measurement_enums(self):
        ok, ref, _ = parse_measurement_reference(SPINDLE_LABEL)
        self.assertTrue(ok)
        self.assertEqual(ref, BladeMeasurementReference.SPINDLE_SIDE_EDGE)
        ok, ref, _ = parse_measurement_reference(TIP_LABEL)
        self.assertTrue(ok)
        self.assertEqual(ref, BladeMeasurementReference.TOOL_TIP_SIDE_EDGE)

    def test_unknown_measurement_blocked(self):
        self.assertFalse(parse_measurement_reference("")[0])
        self.assertFalse(parse_measurement_reference(MEASUREMENT_PLACEHOLDER)[0])
        self.assertFalse(parse_measurement_reference("TOP_EDGE")[0])
        self.assertFalse(parse_measurement_reference("unten")[0])


class TestBladeOffset(unittest.TestCase):
    def test_finish_edge_is_spindle_side(self):
        self.assertEqual(FINISH_EDGE, BladeMeasurementReference.SPINDLE_SIDE_EDGE)

    def test_offset_table(self):
        t = TEST_BLADE_THICKNESS
        self.assertEqual(
            blade_reference_offset(t, BladeMeasurementReference.SPINDLE_SIDE_EDGE),
            0.0,
        )
        self.assertEqual(
            blade_reference_offset(t, BladeMeasurementReference.TOOL_TIP_SIDE_EDGE),
            -t,
        )

    def test_unknown_enum_blocked(self):
        with self.assertRaises(BSFBladeError):
            blade_reference_offset(3.0, "spindle_side")  # type: ignore[arg-type]


class TestWorkpieceZBaseline(unittest.TestCase):
    """Golden Master der Werkstueck-Z vor Schwertkorrektur (Defaultmasse)."""

    def test_z0_bottom_legacy(self):
        z = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=True)
        self.assertEqual(z["z_clearance"], -23.0)
        self.assertEqual(z["z_sink_finish"], 38.0)

    def test_z0_top_legacy(self):
        z = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=False)
        self.assertEqual(z["z_clearance"], -41.0)
        self.assertEqual(z["z_sink_finish"], 20.0)


class TestFourCombinations(unittest.TestCase):
    def _pair(self, z0_bottom: bool):
        wp = calculate_workpiece_bsf_z(18, 38, 23, z0_is_flange_bottom=z0_bottom)
        off_a = blade_reference_offset(TEST_BLADE_THICKNESS, BladeMeasurementReference.SPINDLE_SIDE_EDGE)
        off_b = blade_reference_offset(TEST_BLADE_THICKNESS, BladeMeasurementReference.TOOL_TIP_SIDE_EDGE)
        a = apply_blade_offset(wp, off_a)
        b = apply_blade_offset(wp, off_b)
        return wp, a, b, off_a, off_b

    def test_z0_bottom_both_measurements(self):
        wp, a, b, off_a, off_b = self._pair(True)
        self.assertEqual(a["z_sink_finish"], wp["z_sink_finish"])
        self.assertAlmostEqual(abs(a["z_sink_finish"] - b["z_sink_finish"]), TEST_BLADE_THICKNESS)
        self.assertAlmostEqual(
            physical_finish_edge_z(a["z_sink_finish"], off_a),
            physical_finish_edge_z(b["z_sink_finish"], off_b),
        )
        self.assertAlmostEqual(physical_finish_edge_z(a["z_sink_finish"], off_a), wp["z_sink_finish"])

    def test_z0_top_both_measurements(self):
        wp, a, b, off_a, off_b = self._pair(False)
        self.assertAlmostEqual(abs(a["z_sink_finish"] - b["z_sink_finish"]), TEST_BLADE_THICKNESS)
        self.assertAlmostEqual(
            physical_finish_edge_z(a["z_sink_finish"], off_a),
            physical_finish_edge_z(b["z_sink_finish"], off_b),
        )
        self.assertAlmostEqual(physical_finish_edge_z(a["z_sink_finish"], off_a), wp["z_sink_finish"])


class TestGuiBsfGeom(unittest.TestCase):
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
        ):
            app.entries[key].delete(0, "end")
            app.entries[key].insert(0, val)

    def _generate(self, thickness: str, label: str, position: str = "Einzelposition") -> str:
        app = self.app
        app.position_mode_var.set(position)
        app.on_position_mode_change(None)
        if position == "Einzelposition":
            app.entries["single_x"].delete(0, "end")
            app.entries["single_x"].insert(0, "0")
            app.entries["single_y"].delete(0, "end")
            app.entries["single_y"].insert(0, "0")
        _fill_blade(app, thickness, label)
        app.generate_bsf_code()
        return app.output_text.get("1.0", "end")

    def test_fail_closed_without_geometry(self):
        import tkinter.messagebox as mb

        app = self.app
        app.entries["blade_thickness"].delete(0, "end")
        app.blade_measurement_var.set(MEASUREMENT_PLACEHOLDER)
        app.output_text.delete("1.0", "end")
        orig = mb.showerror
        mb.showerror = lambda *a, **k: None
        try:
            app.generate_bsf_code()
        finally:
            mb.showerror = orig
        self.assertEqual(app.output_text.get("1.0", "end").strip(), "")

    def test_spindle_side_matches_legacy_z(self):
        code = self._generate("3", SPINDLE_LABEL)
        self.assertIn("L Z+38.0000 R0 F30 ; Senken mit 50 Prozent Vorschub", code)
        self.assertIn("L Z-23.0000 R0 FMAX ; Durch den Bund tauchen", code)
        self.assertIn("L Z+100.0000 R0 FMAX ; Aus der Bohrung", code)

    def test_tip_side_shifts_finish_by_thickness(self):
        code_a = self._generate("3", SPINDLE_LABEL)
        code_b = self._generate("3", TIP_LABEL)
        za = _parse_z(_z_line(code_a, "Senken mit 50 Prozent Vorschub"))
        zb = _parse_z(_z_line(code_b, "Senken mit 50 Prozent Vorschub"))
        self.assertAlmostEqual(abs(za - zb), TEST_BLADE_THICKNESS)
        off_a = 0.0
        off_b = -TEST_BLADE_THICKNESS
        self.assertAlmostEqual(physical_finish_edge_z(za, off_a), physical_finish_edge_z(zb, off_b))
        self.assertAlmostEqual(physical_finish_edge_z(za, off_a), 38.0)

    def test_header_once(self):
        code = self._generate("3", SPINDLE_LABEL, position="Teilkreis")
        self.assertEqual(code.count("; SCHWERTDICKE AXIAL: 3.0000 MM"), 1)
        self.assertEqual(code.count("; WERKZEUG VERMESSEN AN: SPINDELSEITIGER SCHWERTKANTE"), 1)
        code_tip = self._generate("3", TIP_LABEL, position="Teilkreis")
        self.assertEqual(
            code_tip.count("; WERKZEUG VERMESSEN AN: WERKZEUGSPITZENSEITIGER SCHWERTKANTE"),
            1,
        )

    def test_z0_top_invariant(self):
        self.app.z0_var.set("Z0 ist Oberkante Bund")
        code_a = self._generate("3", SPINDLE_LABEL)
        code_b = self._generate("3", TIP_LABEL)
        za = _parse_z(_z_line(code_a, "Senken mit 50 Prozent Vorschub"))
        zb = _parse_z(_z_line(code_b, "Senken mit 50 Prozent Vorschub"))
        self.assertAlmostEqual(abs(za - zb), TEST_BLADE_THICKNESS)
        self.assertAlmostEqual(physical_finish_edge_z(za, 0.0), physical_finish_edge_z(zb, -3.0))
        self.assertAlmostEqual(physical_finish_edge_z(za, 0.0), 20.0)

    def test_single_and_circle_same_z_sequence(self):
        single = self._generate("3", TIP_LABEL, "Einzelposition")
        circle = self._generate("3", TIP_LABEL, "Teilkreis")

        def seq_z(code: str):
            lines = []
            for line in code.splitlines():
                if line.startswith("L Z") and (
                    "tauchen" in line
                    or "aktivieren" in line
                    or "Vorposition" in line
                    or "Senken" in line
                    or "freifahren" in line
                ):
                    lines.append(line)
            return lines

        self.assertEqual(seq_z(single), seq_z(circle))
        self.assertIn("; --- EINZELPOSITION ---", single)
        self.assertIn("; --- TEILKREIS ---", circle)

    def test_safe_z_not_shifted(self):
        code = self._generate("3", TIP_LABEL)
        self.assertIn("L Z+100.0000 R0 FMAX ; Aus der Bohrung", code)
        self.assertIn("L Z+200.0000 R0 FMAX", code)

    def test_cycl_def_9_unchanged(self):
        code = self._generate("3", SPINDLE_LABEL)
        self.assertIn("CYCL DEF 9.0 VERWEILZEIT", code)
        self.assertIn("CYCL DEF 9.1 V.ZEIT 1.5", code)

    def test_gui_fields_visible_in_bsf_tool(self):
        self.assertIn("blade_thickness", self.app.entries)
        self.assertTrue(hasattr(self.app, "blade_measurement_combo"))


if __name__ == "__main__":
    unittest.main()
