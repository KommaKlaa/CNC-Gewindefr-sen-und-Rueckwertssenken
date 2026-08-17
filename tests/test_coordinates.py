"""Automatisierte Tests fuer PHASE COORD.1."""

from __future__ import annotations

import unittest

from coordinates import (
    CoordinateParseError,
    XYCoordinate,
    emit_coordinate_calls,
    format_xy_rapid,
    parse_coordinate_text,
    validate_coordinates,
)
from coordinates.nc import fmt_axis


class TestCoordinateParser(unittest.TestCase):
    def test_whitespace(self):
        coords = parse_coordinate_text("100 200")
        self.assertEqual(coords, [XYCoordinate(100.0, 200.0)])

    def test_semicolon(self):
        coords = parse_coordinate_text("100;200")
        self.assertEqual(coords, [XYCoordinate(100.0, 200.0)])

    def test_decimal_point_semicolon(self):
        coords = parse_coordinate_text("100.5;200.25")
        self.assertEqual(coords, [XYCoordinate(100.5, 200.25)])

    def test_decimal_comma_semicolon(self):
        coords = parse_coordinate_text("100,5;200,25")
        self.assertEqual(coords, [XYCoordinate(100.5, 200.25)])

    def test_excel_tab(self):
        coords = parse_coordinate_text("100\t200")
        self.assertEqual(coords, [XYCoordinate(100.0, 200.0)])

    def test_negative(self):
        coords = parse_coordinate_text("-100.5;200")
        self.assertEqual(coords, [XYCoordinate(-100.5, 200.0)])

    def test_invalid_token(self):
        with self.assertRaises(CoordinateParseError) as ctx:
            parse_coordinate_text("ABC;200")
        self.assertTrue(any("Zeile 1" in m for m in ctx.exception.messages))

    def test_missing_y(self):
        with self.assertRaises(CoordinateParseError) as ctx:
            parse_coordinate_text("100")
        self.assertTrue(any("Y-Wert fehlt" in m for m in ctx.exception.messages))

    def test_ambiguous_comma_as_only_separator(self):
        with self.assertRaises(CoordinateParseError):
            parse_coordinate_text("100,200")

    def test_multiline_mixed(self):
        text = "100 200\n150;250\n200\t300"
        coords = parse_coordinate_text(text)
        self.assertEqual(len(coords), 3)
        self.assertEqual(coords[0], XYCoordinate(100.0, 200.0))
        self.assertEqual(coords[1], XYCoordinate(150.0, 250.0))
        self.assertEqual(coords[2], XYCoordinate(200.0, 300.0))

    def test_xy_header_skipped(self):
        coords = parse_coordinate_text("X;Y\n0;0\n100;50")
        self.assertEqual(coords, [XYCoordinate(0.0, 0.0), XYCoordinate(100.0, 50.0)])

    def test_nan_inf_blocked(self):
        for raw in ("NaN;0", "0;Inf", "1;-Infinity"):
            with self.assertRaises(CoordinateParseError):
                parse_coordinate_text(raw)

    def test_error_aborts_without_partial_success(self):
        with self.assertRaises(CoordinateParseError):
            parse_coordinate_text("100 200\nABC 1\n150 250")


class TestCoordinateNc(unittest.TestCase):
    def test_axis_formatting(self):
        self.assertEqual(fmt_axis("X", 100), "X+100.0000")
        self.assertEqual(fmt_axis("Y", 200), "Y+200.0000")
        self.assertEqual(fmt_axis("Y", -250), "Y-250.0000")
        self.assertEqual(fmt_axis("X", -50), "X-50.0000")
        self.assertEqual(fmt_axis("Y", 75.5), "Y+75.5000")

    def test_order_preserved(self):
        coords = [
            XYCoordinate(100, 200),
            XYCoordinate(150, -250),
            XYCoordinate(-50, 75.5),
        ]
        lines = emit_coordinate_calls(coords, sub_label=100)
        self.assertEqual(lines[0], "; --- KOORDINATENLISTE ---")
        self.assertIn("L X+100.0000 Y+200.0000 R0 FMAX", lines)
        self.assertIn("L X+150.0000 Y-250.0000 R0 FMAX", lines)
        self.assertIn("L X-50.0000 Y+75.5000 R0 FMAX", lines)

        # Reihenfolge der Positionsbloecke
        i1 = lines.index("; POSITION 1")
        i2 = lines.index("; POSITION 2")
        i3 = lines.index("; POSITION 3")
        self.assertLess(i1, i2)
        self.assertLess(i2, i3)
        self.assertEqual(lines[i1 + 1], format_xy_rapid(100, 200))
        self.assertEqual(lines[i2 + 1], format_xy_rapid(150, -250))
        self.assertEqual(lines[i3 + 1], format_xy_rapid(-50, 75.5))
        self.assertEqual(lines[i1 + 2], "CALL LBL 100")
        self.assertEqual(lines[i2 + 2], "CALL LBL 100")
        self.assertEqual(lines[i3 + 2], "CALL LBL 100")


class TestCoordinateValidation(unittest.TestCase):
    def test_requires_active(self):
        result = validate_coordinates([XYCoordinate(1, 2, active=False)])
        self.assertFalse(result.ok)

    def test_duplicate_warning(self):
        result = validate_coordinates(
            [XYCoordinate(1, 2), XYCoordinate(3, 4), XYCoordinate(1, 2)]
        )
        self.assertTrue(result.ok)
        self.assertTrue(any("doppelte" in w for w in result.warnings))
        self.assertEqual(len(result.active), 3)


if __name__ == "__main__":
    unittest.main()
