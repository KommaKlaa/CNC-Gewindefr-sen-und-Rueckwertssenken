"""NC.STALE.1 – veralteten NC nach Parameteraenderung nicht exportieren."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tkinter as tk

import bsf_generator_verbessert_v3 as gen
from bgf_chain import BGF_END_MODE_CHAIN, BGF_END_MODE_STANDALONE, bgf_end_mode_label
from coordinates import BGFCoordinatePosition
from nc_state import (
    NC_STATE_CURRENT,
    NC_STATE_STALE,
    STATUS_CURRENT_TEXT,
    STATUS_STALE_TEXT,
    fingerprint_nc_inputs,
)
from ui import MODE_BGF, MODE_BSF


def _set(app, key: str, value) -> None:
    if key not in app.entries:
        return
    app.entries[key].delete(0, tk.END)
    app.entries[key].insert(0, str(value))
    app.refresh_nc_output_status()


def _generate_bgf_circle(app, *, blank_size: str = "1000", start_angle: str = "0") -> str:
    app.mode_var.set(MODE_BGF)
    app.on_mode_change(None)
    app.position_mode_var.set("Teilkreis")
    app.on_position_mode_change(None)
    app.bgf_size_var.set("M16")
    app.load_bgf_values()
    _set(app, "diameter", "580")
    _set(app, "count", "8")
    _set(app, "start_angle", start_angle)
    _set(app, "center_x", "0")
    _set(app, "center_y", "0")
    _set(app, "circle_surface_z", "30")
    _set(app, "bgf_thread_depth", "22")
    _set(app, "approach_clearance", "10")
    _set(app, "blank_size", blank_size)
    _set(app, "blank_height", "60")
    _set(app, "raw_stock_top_z", "30")
    app.bgf_end_mode_var.set(bgf_end_mode_label(BGF_END_MODE_CHAIN))
    app.generate_code()
    return app.output_text.get("1.0", tk.END)


class TestNcStaleGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.app = gen.BSFGeneratorGUI(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _state(self) -> str:
        return self.app.nc_guard.nc_state(
            self.app, output_text=self.app.output_text.get("1.0", tk.END)
        )

    def test_blank_size_change_makes_stale_and_blocks_export_clipboard(self):
        app = self.app
        code = _generate_bgf_circle(app, blank_size="1000")
        self.assertIn("X-500.0000", code)
        self.assertEqual(self._state(), NC_STATE_CURRENT)
        self.assertEqual(app._nc_status_label.cget("text"), STATUS_CURRENT_TEXT)

        _set(app, "blank_size", "1500")
        self.assertEqual(self._state(), NC_STATE_STALE)
        self.assertEqual(app._nc_status_label.cget("text"), STATUS_STALE_TEXT)

        errors = []

        def _err(*args, **kwargs):
            errors.append(args)
            return None

        with mock.patch("bsf_generator_verbessert_v3.messagebox.showerror", side_effect=_err):
            with mock.patch("bsf_generator_verbessert_v3.messagebox.showwarning", side_effect=_err):
                with mock.patch("bsf_generator_verbessert_v3.filedialog.asksaveasfilename") as save:
                    app.export_to_h()
                    save.assert_not_called()
                with mock.patch.object(app.root, "clipboard_append") as clip:
                    app.copy_to_clipboard()
                    clip.assert_not_called()
        blob = "\n".join(str(item) for item in errors)
        self.assertIn("nicht mehr aktuell", blob)
        self.assertIn("NC-Code generieren", blob)

        app.generate_code()
        self.assertEqual(self._state(), NC_STATE_CURRENT)
        self.assertIn("X-750.0000", app.output_text.get("1.0", tk.END))
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "out.H")
            with mock.patch("bsf_generator_verbessert_v3.filedialog.asksaveasfilename", return_value=path):
                with mock.patch("bsf_generator_verbessert_v3.messagebox.showinfo"):
                    app.export_to_h()
            exported = Path(path).read_text(encoding="cp1252")
        self.assertIn("X-750.0000", exported)
        self.assertIn("Y-750.0000", exported)

    def test_start_angle_change_stale_then_regenerate(self):
        app = self.app
        _generate_bgf_circle(app, start_angle="0")
        self.assertIn("Q1 = +0.000", app.output_text.get("1.0", tk.END))
        _set(app, "start_angle", "15")
        self.assertEqual(self._state(), NC_STATE_STALE)
        app.generate_code()
        self.assertEqual(self._state(), NC_STATE_CURRENT)
        self.assertIn("Q1 = +15.000", app.output_text.get("1.0", tk.END))
        self.assertIn("CC X+0.0000 Y+0.0000 ; Teilkreis-Mitte / Pol", app.output_text.get("1.0", tk.END))
        self.assertIn("LP PR+290.0000 PA+Q1 R0 FMAX", app.output_text.get("1.0", tk.END))

    def _setup_bsf_with_edges(self, app):
        """BSF-Grundkonfiguration mit FAIL-CLOSED Pflichtparametern."""
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        app.bsf_tool_profile_var.set("BSF-C-1000/050-10.5-23")
        app.on_bsf_tool_profile_change()
        for k, v in [
            
            ("safe_z", "100"), ("end_safe_z", "200"),
            ("spindle_speed", "800"), ("feed_rate", "60"), ("dwell_time", "1.5"),
            ("single_x", "0"), ("single_y", "0"),
            # ref=0, sink=38 -> target=38; dep=-5: X<B<C<D OK
            ("entry_edge_z", "20"), ("exit_edge_z", "-5"), ("target_surface_z", "38"),
            ("x_safety_clearance", "2.000"), ("entry_clearance", "1.000"),
            ("full_cut_overlap_mm", "0.250"),
        ]:
            _set(app, k, v)

    def test_tool_change_stale(self):
        app = self.app
        self._setup_bsf_with_edges(app)
        app.generate_bsf_code()
        self.assertEqual(self._state(), NC_STATE_CURRENT)
        app.bsf_tool_profile_var.set("BSF-E-1350/050-16.5-14")
        app.on_bsf_tool_profile_change()
        self.assertEqual(self._state(), NC_STATE_STALE)

    def test_zref_change_stale(self):
        app = self.app
        self._setup_bsf_with_edges(app)
        app.generate_bsf_code()
        _set(app, "target_surface_z", "58")
        self.assertEqual(self._state(), NC_STATE_STALE)

    def test_coord_list_mutations_stale(self):
        app = self.app
        app.mode_var.set(MODE_BGF)
        app.on_mode_change(None)
        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        app.bgf_size_var.set("M16")
        app.load_bgf_values()
        _set(app, "bgf_thread_depth", "22")
        _set(app, "raw_stock_top_z", "30")
        app.coord_rows = [BGFCoordinatePosition(0, 0, 30.0, 22.0)]
        app._refresh_coord_tree()
        app.generate_bgf_code()
        self.assertEqual(self._state(), NC_STATE_CURRENT)

        app.coord_rows[0] = BGFCoordinatePosition(10, 0, 30.0, 22.0)
        app._refresh_coord_tree()
        self.assertEqual(self._state(), NC_STATE_STALE)
        app.generate_bgf_code()
        self.assertEqual(self._state(), NC_STATE_CURRENT)

        app.coord_rows.append(BGFCoordinatePosition(20, 5, 30.0, 22.0))
        app._refresh_coord_tree()
        self.assertEqual(self._state(), NC_STATE_STALE)
        app.generate_bgf_code()

        del app.coord_rows[0]
        app._refresh_coord_tree()
        self.assertEqual(self._state(), NC_STATE_STALE)
        app.generate_bgf_code()

        app.coord_rows = [
            BGFCoordinatePosition(20, 5, 30.0, 22.0),
            BGFCoordinatePosition(0, 0, 30.0, 22.0),
        ]
        app._refresh_coord_tree()
        self.assertEqual(self._state(), NC_STATE_STALE)

    def test_mode_change_stale(self):
        app = self.app
        _generate_bgf_circle(app)
        self.assertEqual(self._state(), NC_STATE_CURRENT)
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        self.assertEqual(self._state(), NC_STATE_STALE)

    def test_programmer_change_stale(self):
        app = self.app
        _generate_bgf_circle(app)
        app.programmer_var.set("Tester")
        self.assertEqual(self._state(), NC_STATE_STALE)

    def test_end_mode_change_stale_then_regenerate(self):
        app = self.app
        _generate_bgf_circle(app)
        self.assertEqual(self._state(), NC_STATE_CURRENT)
        self.assertIn("; PROGRAMMENDE: VERKETTUNG / CALL PGM", app.output_text.get("1.0", tk.END))
        app.bgf_end_mode_var.set(bgf_end_mode_label(BGF_END_MODE_STANDALONE))
        self.assertEqual(self._state(), NC_STATE_STALE)
        app.generate_code()
        self.assertEqual(self._state(), NC_STATE_CURRENT)
        code = app.output_text.get("1.0", tk.END)
        self.assertIn("; PROGRAMMENDE: EINZELPROGRAMM / M30", code)
        self.assertRegex(code, r"LBL 999\s+L Z\+200\.0000 R0 FMAX M30\s+END PGM")

    def test_unchanged_state_export_pass(self):
        app = self.app
        _generate_bgf_circle(app, blank_size="1500")
        before = fingerprint_nc_inputs(app)
        self.assertEqual(self._state(), NC_STATE_CURRENT)
        self.assertEqual(app.nc_guard.generated_input_fingerprint, before)
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "ok.H")
            with mock.patch("bsf_generator_verbessert_v3.filedialog.asksaveasfilename", return_value=path):
                with mock.patch("bsf_generator_verbessert_v3.messagebox.showinfo"):
                    app.export_to_h()
            self.assertTrue(Path(path).is_file())
            self.assertIn("X-750.0000", Path(path).read_text(encoding="cp1252"))

    def test_teilkreis_hotfix_after_stale_cycle(self):
        app = self.app
        _generate_bgf_circle(app)
        _set(app, "blank_size", "1500")
        app.generate_code()
        code = app.output_text.get("1.0", tk.END)
        self.assertIn("LBL 1 ; Schleifenanfang Teilkreis", code)
        self.assertIn("CC X+0.0000 Y+0.0000 ; Teilkreis-Mitte / Pol", code)
        self.assertIn("LP PR+290.0000 PA+Q1 R0 FMAX", code)
        self.assertIn("CALL LBL 100", code)


if __name__ == "__main__":
    unittest.main()
