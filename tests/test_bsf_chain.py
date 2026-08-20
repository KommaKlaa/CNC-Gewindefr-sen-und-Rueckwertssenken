"""PHASE BSF.CHAIN.1 – Tests fuer waehlbares BSF-Programmende.

Testkategorien:
  - BSF-Endmodus-Konstanten und Hilfsfunktionen (bsf_chain.py)
  - Neues GUI-Default = CHAIN_CALL_PGM
  - Legacy-JSON ohne end_mode → STANDALONE_M30
  - JSON-Roundtrip CHAIN + STANDALONE
  - Ungültiger end_mode → fail closed
  - NC-Stale nach Endmodus-Wechsel
  - Teilkreis: M30-Count 0/1, FN9-Guard, kein Fallthrough, END PGM erreichbar
  - Count-Regression 1/6/8/24 für beide Modi
  - Einzelposition: M30-Count 0/1
  - Koordinatenliste: M30-Count 0/1
  - Prozess-M-Funktionen + Z-Geometrie identisch zwischen Chain und Standalone
  - HEULE_MOTION_IDENTICAL: Bearbeitungssequenz unverändert
"""
from __future__ import annotations

import json
import re
import tempfile
import unittest

import bsf_generator_verbessert_v3 as gen
from bsf_chain import (
    BSF_END_LABEL,
    BSF_END_MODE_CHAIN,
    BSF_END_MODE_STANDALONE,
    analyze_bsf_part_circle_nc,
    bsf_end_mode_comment,
    bsf_end_mode_from_label,
    bsf_end_mode_label,
    m30_exec_count,
    validate_bsf_end_mode,
)
from coordinates import BSFCoordinatePosition, build_bsf_document, load_bsf_document_json, save_bsf_document_json
from coordinates.bsf_list_document import document_to_dict, parse_document_dict
from heule_bsf_tools import BSF_TOOL_PROFILES
from ui import MODE_BSF

import tkinter as tk

TOOL_KEY = "BSF_C_1000_050_10_5_23"
TOOL_C = BSF_TOOL_PROFILES[TOOL_KEY]


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_app():
    root = tk.Tk()
    root.withdraw()
    app = gen.BSFGeneratorGUI(root)
    return root, app


def _set_bsf_common(app, *, end_mode=BSF_END_MODE_CHAIN):
    app.mode_var.set(MODE_BSF)
    app.on_mode_change(None)
    app.bsf_tool_profile_var.set(TOOL_C.designation)
    app.on_bsf_tool_profile_change()
    app.bsf_end_mode_var.set(bsf_end_mode_label(end_mode))
    for k, v in [
        ("spindle_speed", "800"), ("feed_rate", "60"), ("dwell_time", "1.0"),
        
        ("safe_z", "100"), ("end_safe_z", "200"),
        ("program_name", "TEST_BSF"), ("raw_stock_top_z", "0"),
        ("blank_height", "60"), ("blank_size", "1000"),
        # FAIL-CLOSED: ref=0, sink=38 -> target=38; dep=-5: X=-27.25, B=-14.55, C=-13.3, D=29.45
        ("entry_edge_z", "20"), ("exit_edge_z", "-5"), ("target_surface_z", "38"),
        ("x_safety_clearance", "2.000"), ("entry_clearance", "1.000"),
        ("full_cut_overlap_mm", "0.250"),
    ]:
        app.entries[k].delete(0, "end")
        app.entries[k].insert(0, v)


def _gen_circle(app, count=6, end_mode=BSF_END_MODE_CHAIN) -> str:
    _set_bsf_common(app, end_mode=end_mode)
    app.position_mode_var.set("Teilkreis")
    app.on_position_mode_change(None)
    for k, v in [("diameter", "430"), ("start_angle", "0"),
                 ("center_x", "0"), ("center_y", "0"), ("count", str(count))]:
        app.entries[k].delete(0, "end")
        app.entries[k].insert(0, v)
    app.generate_bsf_code()
    return app.output_text.get("1.0", "end").strip()


def _gen_single(app, end_mode=BSF_END_MODE_CHAIN) -> str:
    _set_bsf_common(app, end_mode=end_mode)
    app.position_mode_var.set("Einzelposition")
    app.on_position_mode_change(None)
    app.entries["single_x"].delete(0, "end"); app.entries["single_x"].insert(0, "0")
    app.entries["single_y"].delete(0, "end"); app.entries["single_y"].insert(0, "0")
    app.generate_bsf_code()
    return app.output_text.get("1.0", "end").strip()


def _gen_coords(app, end_mode=BSF_END_MODE_CHAIN) -> str:
    _set_bsf_common(app, end_mode=end_mode)
    app.position_mode_var.set("Koordinatenliste")
    app.on_position_mode_change(None)
    app.bsf_coord_rows = [
        BSFCoordinatePosition(0, 0),
        BSFCoordinatePosition(100, 50),
    ]
    app.generate_bsf_code()
    return app.output_text.get("1.0", "end").strip()


def _non_end_lines(code: str) -> list[str]:
    """Alle Zeilen ausser dem LBL999-Block und END PGM."""
    lines = code.splitlines()
    result = []
    in_end_block = False
    for line in lines:
        stripped = line.split(";")[0].strip()
        if re.match(r"^LBL 999\b", stripped):
            in_end_block = True
        if in_end_block:
            continue
        if line.startswith("END PGM"):
            continue
        result.append(line)
    return result


def _doc_base(**kwargs):
    base = dict(
        program_name="BSF_TEST",
        tool_number=8,
        blank_size=1000.0,
        blank_height=60.0,
        tool_profile_key=TOOL_KEY,
        spindle_speed=1500,
        feed=120.0,
        dwell_time=1.5,
        reduce_approach=True,
        approach_feed_factor=0.5,
        activate_preset="IKZ Ein (M7)",
        activate_custom="M107",
        deactivate_preset="Alles AUS (M9)",
        deactivate_custom="M9",
        safe_z=100.0,
        end_safe_z=200.0,
        positions=[BSFCoordinatePosition(0.0, 0.0), BSFCoordinatePosition(100.0, 50.0)],
        entry_edge_z=20.0,
        exit_edge_z=-5.0,
        target_surface_z=38.0,
    )
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# bsf_chain.py Konstanten und Hilfsfunktionen
# ---------------------------------------------------------------------------

class TestBsfChainModule(unittest.TestCase):
    def test_end_mode_values(self):
        self.assertEqual(BSF_END_MODE_CHAIN, "CHAIN_CALL_PGM")
        self.assertEqual(BSF_END_MODE_STANDALONE, "STANDALONE_M30")

    def test_end_label(self):
        self.assertEqual(BSF_END_LABEL, 999)

    def test_label_roundtrip(self):
        for mode in (BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE):
            self.assertEqual(bsf_end_mode_from_label(bsf_end_mode_label(mode)), mode)

    def test_label_invalid_raises(self):
        with self.assertRaises(ValueError):
            bsf_end_mode_from_label("UNKNOWN")

    def test_validate_valid(self):
        validate_bsf_end_mode(BSF_END_MODE_CHAIN)
        validate_bsf_end_mode(BSF_END_MODE_STANDALONE)

    def test_validate_invalid_raises(self):
        with self.assertRaises(ValueError):
            validate_bsf_end_mode("GARBAGE")

    def test_end_mode_comment_chain(self):
        self.assertIn("VERKETTUNG", bsf_end_mode_comment(BSF_END_MODE_CHAIN))

    def test_end_mode_comment_standalone(self):
        self.assertIn("EINZELPROGRAMM", bsf_end_mode_comment(BSF_END_MODE_STANDALONE))


# ---------------------------------------------------------------------------
# GUI-Default
# ---------------------------------------------------------------------------

class TestBsfGuiDefault(unittest.TestCase):
    def setUp(self):
        self.root, self.app = _make_app()

    def tearDown(self):
        self.root.destroy()

    def test_new_gui_default_is_chain(self):
        root2, app2 = _make_app()
        try:
            app2.mode_var.set(MODE_BSF)
            app2.on_mode_change(None)
            self.assertEqual(app2.get_bsf_end_mode(), BSF_END_MODE_CHAIN)
        finally:
            root2.destroy()


# ---------------------------------------------------------------------------
# JSON-Persistenz
# ---------------------------------------------------------------------------

class TestBsfJsonPersistence(unittest.TestCase):
    def test_roundtrip_chain(self):
        doc = build_bsf_document(**_doc_base(end_mode=BSF_END_MODE_CHAIN))
        with tempfile.NamedTemporaryFile(suffix=".bsf.json", delete=False, mode="w") as f:
            fname = f.name
        save_bsf_document_json(fname, doc)
        loaded = load_bsf_document_json(fname)
        self.assertEqual(loaded.end_mode, BSF_END_MODE_CHAIN)

    def test_roundtrip_standalone(self):
        doc = build_bsf_document(**_doc_base(end_mode=BSF_END_MODE_STANDALONE))
        with tempfile.NamedTemporaryFile(suffix=".bsf.json", delete=False, mode="w") as f:
            fname = f.name
        save_bsf_document_json(fname, doc)
        loaded = load_bsf_document_json(fname)
        self.assertEqual(loaded.end_mode, BSF_END_MODE_STANDALONE)

    def test_legacy_without_end_mode_defaults_to_standalone(self):
        doc = build_bsf_document(**_doc_base(end_mode=BSF_END_MODE_CHAIN))
        d = document_to_dict(doc)
        d.pop("program_end", None)
        loaded = parse_document_dict(d)
        self.assertEqual(loaded.end_mode, BSF_END_MODE_STANDALONE)

    def test_invalid_end_mode_fail_closed(self):
        from coordinates.bsf_list_document import BSFDocumentError
        doc = build_bsf_document(**_doc_base(end_mode=BSF_END_MODE_CHAIN))
        d = document_to_dict(doc)
        d["program_end"] = {"end_mode": "INVALID_GARBAGE"}
        with self.assertRaises(BSFDocumentError):
            parse_document_dict(d)

    def test_missing_end_mode_field_fail_closed(self):
        from coordinates.bsf_list_document import BSFDocumentError
        doc = build_bsf_document(**_doc_base(end_mode=BSF_END_MODE_CHAIN))
        d = document_to_dict(doc)
        d["program_end"] = {}  # end_mode-Feld fehlt
        with self.assertRaises(BSFDocumentError):
            parse_document_dict(d)


# ---------------------------------------------------------------------------
# NC Stale
# ---------------------------------------------------------------------------

class TestBsfEndModeStale(unittest.TestCase):
    def setUp(self):
        self.root, self.app = _make_app()

    def tearDown(self):
        self.root.destroy()

    def test_stale_after_end_mode_change(self):
        code = _gen_circle(self.app, 6, BSF_END_MODE_CHAIN)
        self.assertTrue(self.app.nc_guard.is_current(self.app, output_text=code))
        self.app.bsf_end_mode_var.set(bsf_end_mode_label(BSF_END_MODE_STANDALONE))
        self.assertFalse(self.app.nc_guard.is_current(self.app, output_text=code))

    def test_regenerate_after_stale(self):
        _gen_circle(self.app, 6, BSF_END_MODE_CHAIN)
        self.app.bsf_end_mode_var.set(bsf_end_mode_label(BSF_END_MODE_STANDALONE))
        code2 = _gen_circle(self.app, 6, BSF_END_MODE_STANDALONE)
        self.assertTrue(self.app.nc_guard.is_current(self.app, output_text=code2))
        self.assertEqual(m30_exec_count(code2), 1)


# ---------------------------------------------------------------------------
# Teilkreis – M30-Counts + Control Flow
# ---------------------------------------------------------------------------

class TestBsfPartCircle(unittest.TestCase):
    def setUp(self):
        self.root, self.app = _make_app()

    def tearDown(self):
        self.root.destroy()

    def test_chain_m30_count_zero(self):
        code = _gen_circle(self.app, 6, BSF_END_MODE_CHAIN)
        self.assertEqual(m30_exec_count(code), 0)

    def test_standalone_m30_count_one(self):
        code = _gen_circle(self.app, 6, BSF_END_MODE_STANDALONE)
        self.assertEqual(m30_exec_count(code), 1)

    def test_standalone_m30_final_only(self):
        """M30 darf nur im LBL999-Endblock stehen."""
        code = _gen_circle(self.app, 6, BSF_END_MODE_STANDALONE)
        lines = code.splitlines()
        lbl999_i = next((i for i, l in enumerate(lines) if l.split(";")[0].strip().startswith("LBL 999")), None)
        self.assertIsNotNone(lbl999_i)
        # Kein M30 vor LBL 999
        before = "\n".join(lines[:lbl999_i])
        self.assertEqual(m30_exec_count(before), 0)

    def test_no_fallthrough_chain(self):
        code = _gen_circle(self.app, 6, BSF_END_MODE_CHAIN)
        a = analyze_bsf_part_circle_nc(code)
        self.assertFalse(a["fallthrough"])

    def test_no_fallthrough_standalone(self):
        code = _gen_circle(self.app, 6, BSF_END_MODE_STANDALONE)
        a = analyze_bsf_part_circle_nc(code)
        self.assertFalse(a["fallthrough"])

    def test_fn9_guard_present_chain(self):
        code = _gen_circle(self.app, 6, BSF_END_MODE_CHAIN)
        self.assertIn("FN 9:", code)
        self.assertIn(f"GOTO LBL {BSF_END_LABEL}", code)

    def test_fn9_guard_present_standalone(self):
        code = _gen_circle(self.app, 6, BSF_END_MODE_STANDALONE)
        self.assertIn("FN 9:", code)

    def test_lbl999_present(self):
        for mode in (BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE):
            code = _gen_circle(self.app, 6, mode)
            self.assertIn(f"LBL {BSF_END_LABEL}", code, f"LBL {BSF_END_LABEL} fehlt in {mode}")

    def test_end_pgm_reachable_chain(self):
        code = _gen_circle(self.app, 6, BSF_END_MODE_CHAIN)
        a = analyze_bsf_part_circle_nc(code)
        self.assertTrue(a["end_pgm_reachable"])

    def test_header_comment_chain(self):
        code = _gen_circle(self.app, 6, BSF_END_MODE_CHAIN)
        self.assertIn("VERKETTUNG", code)

    def test_header_comment_standalone(self):
        code = _gen_circle(self.app, 6, BSF_END_MODE_STANDALONE)
        self.assertIn("EINZELPROGRAMM", code)


# ---------------------------------------------------------------------------
# Count-Regression
# ---------------------------------------------------------------------------

class TestBsfCountRegression(unittest.TestCase):
    def setUp(self):
        self.root, self.app = _make_app()

    def tearDown(self):
        self.root.destroy()

    def _check_count(self, count, end_mode):
        code = _gen_circle(self.app, count, end_mode)
        a = analyze_bsf_part_circle_nc(code)
        # CALL LBL 100 kommt genau count-mal vor (alle im Schleifenbereich, 1x aus Schleife)
        call_lbl = len(re.findall(r"CALL LBL 100", code))
        self.assertEqual(call_lbl, 1, f"Genau 1x CALL LBL 100 erwartet (Schleife), gefunden: {call_lbl}")
        self.assertFalse(a["fallthrough"], f"Fallthrough fuer count={count} mode={end_mode}")
        # FN 12 nutzt LT count
        self.assertIn(f"IF +Q2 LT +{count}", code)

    def test_count_1_chain(self):    self._check_count(1, BSF_END_MODE_CHAIN)
    def test_count_2_chain(self):    self._check_count(2, BSF_END_MODE_CHAIN)
    def test_count_6_chain(self):    self._check_count(6, BSF_END_MODE_CHAIN)
    def test_count_8_chain(self):    self._check_count(8, BSF_END_MODE_CHAIN)
    def test_count_24_chain(self):   self._check_count(24, BSF_END_MODE_CHAIN)
    def test_count_1_standalone(self):   self._check_count(1, BSF_END_MODE_STANDALONE)
    def test_count_6_standalone(self):   self._check_count(6, BSF_END_MODE_STANDALONE)
    def test_count_8_standalone(self):   self._check_count(8, BSF_END_MODE_STANDALONE)
    def test_count_24_standalone(self):  self._check_count(24, BSF_END_MODE_STANDALONE)


# ---------------------------------------------------------------------------
# Einzelposition
# ---------------------------------------------------------------------------

class TestBsfSinglePosition(unittest.TestCase):
    def setUp(self):
        self.root, self.app = _make_app()

    def tearDown(self):
        self.root.destroy()

    def test_chain_m30_zero(self):
        self.assertEqual(m30_exec_count(_gen_single(self.app, BSF_END_MODE_CHAIN)), 0)

    def test_standalone_m30_one(self):
        self.assertEqual(m30_exec_count(_gen_single(self.app, BSF_END_MODE_STANDALONE)), 1)

    def test_no_lbl_subprogram(self):
        for mode in (BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE):
            code = _gen_single(self.app, mode)
            self.assertNotIn("LBL 100", code)

    def test_end_pgm_present(self):
        for mode in (BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE):
            code = _gen_single(self.app, mode)
            self.assertIn("END PGM", code)


# ---------------------------------------------------------------------------
# Koordinatenliste
# ---------------------------------------------------------------------------

class TestBsfCoordinateList(unittest.TestCase):
    def setUp(self):
        self.root, self.app = _make_app()

    def tearDown(self):
        self.root.destroy()

    def test_chain_m30_zero(self):
        self.assertEqual(m30_exec_count(_gen_coords(self.app, BSF_END_MODE_CHAIN)), 0)

    def test_standalone_m30_one(self):
        self.assertEqual(m30_exec_count(_gen_coords(self.app, BSF_END_MODE_STANDALONE)), 1)

    def test_no_lbl_subprogram(self):
        for mode in (BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE):
            code = _gen_coords(self.app, mode)
            self.assertNotIn("LBL 100", code)

    def test_position_count_preserved(self):
        for mode in (BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE):
            code = _gen_coords(self.app, mode)
            self.assertIn("ANZAHL POSITIONEN: 2", code)


# ---------------------------------------------------------------------------
# HEULE-Motion-Identität: Chain == Standalone (ausser Endbereich)
# ---------------------------------------------------------------------------

class TestBsfHeuleMotionIdentical(unittest.TestCase):
    def setUp(self):
        self.root, self.app = _make_app()

    def tearDown(self):
        self.root.destroy()

    def _motion_lines(self, code: str) -> list[str]:
        """Alle Zeilen ausser Kommentaren, LBL999-Block und END PGM."""
        lines = []
        in_end = False
        for line in code.splitlines():
            s = line.split(";")[0].strip()
            if re.match(r"^LBL 999\b", s):
                in_end = True
            if in_end:
                continue
            if line.startswith("END PGM"):
                continue
            # Headerkommentare PROGRAMMENDE raus
            if "PROGRAMMENDE:" in line:
                continue
            lines.append(line)
        return lines

    def test_circle_motion_identical(self):
        chain = _gen_circle(self.app, 6, BSF_END_MODE_CHAIN)
        standalone = _gen_circle(self.app, 6, BSF_END_MODE_STANDALONE)
        self.assertEqual(self._motion_lines(chain), self._motion_lines(standalone))

    def _trim_for_motion_compare(self, code: str) -> list[str]:
        """Entfernt Endbereich, END PGM und PROGRAMMENDE-Header fuer Vergleich."""
        lines = code.splitlines()
        result = []
        in_end = False
        for line in lines:
            s = line.split(";")[0].strip()
            if re.match(r"^LBL 999\b", s):
                in_end = True
            if in_end:
                continue
            if line.startswith("END PGM"):
                continue
            if "PROGRAMMENDE:" in line:
                continue
            result.append(line)
        # Letzte Zeile fuer Einzelpos/Koordinaten (Endzeile ohne LBL999)
        if result and re.search(r"\bFMAX\b", result[-1]) and "L Z+" in result[-1]:
            result = result[:-1]
        return result

    def test_single_motion_identical(self):
        chain = _gen_single(self.app, BSF_END_MODE_CHAIN)
        standalone = _gen_single(self.app, BSF_END_MODE_STANDALONE)
        self.assertEqual(self._trim_for_motion_compare(chain),
                         self._trim_for_motion_compare(standalone))

    def test_coords_motion_identical(self):
        chain = _gen_coords(self.app, BSF_END_MODE_CHAIN)
        standalone = _gen_coords(self.app, BSF_END_MODE_STANDALONE)
        self.assertEqual(self._trim_for_motion_compare(chain),
                         self._trim_for_motion_compare(standalone))

    def test_m5_present_in_sequence(self):
        for mode in (BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE):
            code = _gen_circle(self.app, 6, mode)
            self.assertIn("M5", code)

    def test_m9_present_in_sequence(self):
        for mode in (BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE):
            code = _gen_circle(self.app, 6, mode)
            # M9 ist in der HEULE-Sequenz (Messer schliessen)
            self.assertIn("M9", code)

    def test_cycl_def_9_unchanged(self):
        for mode in (BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE):
            code = _gen_circle(self.app, 6, mode)
            self.assertIn("CYCL DEF 9.0 VERWEILZEIT", code)
            self.assertIn("CYCL DEF 9.1 V.ZEIT", code)


if __name__ == "__main__":
    unittest.main()
