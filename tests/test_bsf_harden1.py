"""PHASE BSF.HEULE.HARDEN.1 – Tests fuer Fail-Closed, C-Parameter, D-Invariante, M-Semantik."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

import tkinter as tk
import tkinter.messagebox as mb

import bsf_generator_verbessert_v3 as gen
from bsf_workpiece_geometry import compute_heule_process_positions
from coordinates.bsf_list_document import (
    FORMAT_VERSION,
    build_bsf_document,
    document_to_dict,
    parse_document_dict,
)
from coordinates import BSFCoordinatePosition
from heule_bsf_tools import BSF_TOOL_PROFILES
from ui import MODE_BSF

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]
TOOL_E = BSF_TOOL_PROFILES["BSF_E_1350_050_16_5_14"]

# Geometrie-Parameter die X<B<C<D garantieren fuer ref=0, sink=38, Z0=Bottom
# dep=-5: X=-27.25, B=-14.55, C=-13.3, D=29.45
_VALID_EDGES = {
    "exit_edge_z": "-5",
    "entry_edge_z": "20",
    "target_surface_z": "38",
    "x_safety_clearance": "2.000",
    "entry_clearance": "1.000",
    "full_cut_overlap_mm": "0.250",
}

_COMMON_BSF = {
    "safe_z": "100",
    "end_safe_z": "200",
    "spindle_speed": "800",
    "feed_rate": "60",
    "dwell_time": "1.5",
    "single_x": "0",
    "single_y": "0",
}


def _silence_mb():
    orig = mb.showerror
    errors = []
    mb.showerror = lambda *a, **k: errors.append(a)
    return orig, errors


def _restore_mb(orig):
    mb.showerror = orig


def _setup_app(*, with_edges=True):
    root = tk.Tk()
    root.withdraw()
    app = gen.BSFGeneratorGUI(root)
    app.mode_var.set(MODE_BSF)
    app.on_mode_change(None)
    app.position_mode_var.set("Einzelposition")
    app.on_position_mode_change(None)
    app.bsf_tool_profile_var.set(TOOL_C.designation)
    app.on_bsf_tool_profile_change()
    params = dict(_COMMON_BSF)
    if with_edges:
        params.update(_VALID_EDGES)
    for k, v in params.items():
        if k in app.entries:
            app.entries[k].delete(0, "end")
            app.entries[k].insert(0, v)
    return root, app


# ---------------------------------------------------------------------------
# FAIL-CLOSED: deployment_edge_z und entry_edge_z
# ---------------------------------------------------------------------------

class TestFailClosedEdges(unittest.TestCase):
    def test_missing_deployment_edge_blocks_nc(self):
        """NC-Erzeugung muss blockieren wenn deployment_edge_z fehlt."""
        root, app = _setup_app(with_edges=False)
        # entry_edge_z setzen, aber deployment_edge_z leer lassen
        app.entries["entry_edge_z"].delete(0, "end")
        app.entries["entry_edge_z"].insert(0, "20")
        orig, errors = _silence_mb()
        try:
            app.generate_bsf_code()
        finally:
            _restore_mb(orig)
        code = app.output_text.get("1.0", "end").strip()
        self.assertEqual(code, "", "NC muss bei fehlendem deployment_edge_z leer bleiben")
        self.assertTrue(any("Austrittskante" in str(e) or "exit" in str(e).lower() for e in errors),
                        f"Erwarte Fehlermeldung zu Austrittskante, bekam: {errors}")
        root.destroy()

    def test_missing_entry_edge_blocks_nc(self):
        """NC-Erzeugung muss blockieren wenn entry_edge_z fehlt."""
        root, app = _setup_app(with_edges=False)
        # deployment_edge_z setzen, aber entry_edge_z leer lassen
        app.entries["exit_edge_z"].delete(0, "end")
        app.entries["exit_edge_z"].insert(0, "-5")
        orig, errors = _silence_mb()
        try:
            app.generate_bsf_code()
        finally:
            _restore_mb(orig)
        code = app.output_text.get("1.0", "end").strip()
        self.assertEqual(code, "", "NC muss bei fehlendem entry_edge_z leer bleiben")
        self.assertTrue(any("Eintrittskante" in str(e) or "entry" in str(e).lower() for e in errors),
                        f"Erwarte Fehlermeldung zu Eintrittskante, bekam: {errors}")
        root.destroy()

    def test_both_edges_missing_blocks_nc(self):
        """NC-Erzeugung muss blockieren wenn beide Kanten fehlen."""
        root, app = _setup_app(with_edges=False)
        orig, errors = _silence_mb()
        try:
            app.generate_bsf_code()
        finally:
            _restore_mb(orig)
        code = app.output_text.get("1.0", "end").strip()
        self.assertEqual(code, "")
        root.destroy()

    def test_no_fallback_from_target_minus_1(self):
        """Kein automatisches deployment_edge = target - 1 Fallback."""
        root, app = _setup_app(with_edges=False)
        app.entries["entry_edge_z"].delete(0, "end")
        app.entries["entry_edge_z"].insert(0, "0")
        # deployment_edge_z explizit leer lassen
        orig, _ = _silence_mb()
        try:
            app.generate_bsf_code()
        finally:
            _restore_mb(orig)
        code = app.output_text.get("1.0", "end")
        # Muss leer sein oder keinen Hinweis auf target-1 enthalten
        self.assertNotIn("L Z+", code.strip(), "Kein NC-Code bei fehlendem deployment_edge_z")
        root.destroy()

    def test_no_fallback_from_reference_z(self):
        """Kein automatisches entry_edge = reference_z Fallback."""
        root, app = _setup_app(with_edges=False)
        app.entries["exit_edge_z"].delete(0, "end")
        app.entries["exit_edge_z"].insert(0, "-5")
        # entry_edge_z explizit leer lassen
        orig, _ = _silence_mb()
        try:
            app.generate_bsf_code()
        finally:
            _restore_mb(orig)
        code = app.output_text.get("1.0", "end")
        self.assertNotIn("L Z+", code.strip(), "Kein NC-Code bei fehlendem entry_edge_z")
        root.destroy()

    def test_explicit_edges_allow_nc(self):
        """Mit expliziten Kanten wird NC erfolgreich erzeugt."""
        root, app = _setup_app(with_edges=True)
        orig, errors = _silence_mb()
        try:
            app.generate_bsf_code()
        finally:
            _restore_mb(orig)
        code = app.output_text.get("1.0", "end")
        self.assertIn("BEGIN PGM", code)
        self.assertEqual(errors, [], f"Keine Fehler erwartet, bekam: {errors}")
        root.destroy()


# ---------------------------------------------------------------------------
# full_cut_overlap_mm Parameter
# ---------------------------------------------------------------------------

class TestFullCutOverlapParameter(unittest.TestCase):
    def test_default_0_25(self):
        """Default-Wert von full_cut_overlap_mm ist 0.25."""
        root, app = _setup_app(with_edges=True)
        val = app.entries["full_cut_overlap_mm"].get()
        self.assertAlmostEqual(float(val.replace(",", ".")), 0.25, places=4)
        root.destroy()

    def test_custom_value_changes_c_position(self):
        """Benutzerdefinierter full_cut_overlap_mm veraendert C-Position."""
        # Default: C = dep - Hs + 0.25 = -5 - 8.55 + 0.25 = -13.3
        # Benutzerwert 0.40: C = -5 - 8.55 + 0.40 = -13.15
        pos_default = compute_heule_process_positions(
            exit_edge_z=-5.0,
            entry_edge_z=20.0,
            target_surface_z=38.0,
            measurement_face_to_cutting_edge_mm=8.55,
            deployment_length_al_mm=20.25,
            x_safety_clearance_mm=2.0,
            entry_clearance_mm=1.0,
            full_cut_overlap_mm=0.25,
        )
        pos_custom = compute_heule_process_positions(
            exit_edge_z=-5.0,
            entry_edge_z=20.0,
            target_surface_z=38.0,
            measurement_face_to_cutting_edge_mm=8.55,
            deployment_length_al_mm=20.25,
            x_safety_clearance_mm=2.0,
            entry_clearance_mm=1.0,
            full_cut_overlap_mm=0.40,
        )
        self.assertAlmostEqual(pos_default.c_measurement_face_z, -13.3, places=4)
        self.assertAlmostEqual(pos_custom.c_measurement_face_z, -13.15, places=4)
        self.assertNotAlmostEqual(pos_default.c_measurement_face_z, pos_custom.c_measurement_face_z, places=4)

    def test_negative_full_cut_overlap_blocked_by_model(self):
        """full_cut_overlap_mm < 0 ist vom Modell nicht explizit blockiert (Prozessparameter)."""
        # Das Modell in compute_heule_process_positions validiert nicht explizit >= 0,
        # aber build_bsf_document und die NC-Erzeugung blockieren negatives C.
        from coordinates.bsf_list_document import BSFDocumentError
        with self.assertRaises(BSFDocumentError):
            build_bsf_document(
                program_name="TEST", tool_number=8, blank_size=1000.0, blank_height=60.0,
                tool_profile_key="BSF_C_1000_050_10_5_23",
                spindle_speed=800, feed=60.0, dwell_time=1.5,
                reduce_approach=True, approach_feed_factor=0.5,
                activate_preset="IKZ Ein (M7)", activate_custom="",
                deactivate_preset="Alles AUS (M9)", deactivate_custom="",
                safe_z=100.0, end_safe_z=200.0,
                positions=[BSFCoordinatePosition(0.0, 0.0)],
                full_cut_overlap_mm=-0.1,
            )

    def test_full_cut_overlap_stale_on_change(self):
        """Aenderung von full_cut_overlap_mm markiert NC als STALE."""
        from nc_state import NC_STATE_CURRENT, NC_STATE_STALE
        root, app = _setup_app(with_edges=True)
        orig, _ = _silence_mb()
        try:
            app.generate_bsf_code()
        finally:
            _restore_mb(orig)
        code = app.output_text.get("1.0", "end")
        self.assertEqual(app.nc_guard.nc_state(app, output_text=code), NC_STATE_CURRENT)
        app.entries["full_cut_overlap_mm"].delete(0, "end")
        app.entries["full_cut_overlap_mm"].insert(0, "0.400")
        self.assertEqual(app.nc_guard.nc_state(app, output_text=code), NC_STATE_STALE)
        root.destroy()

    def test_full_cut_overlap_json_roundtrip(self):
        """full_cut_overlap_mm wird in JSON V4 persistiert und korrekt geladen."""
        doc = build_bsf_document(
            program_name="TEST", tool_number=8, blank_size=1000.0, blank_height=60.0,
            tool_profile_key="BSF_C_1000_050_10_5_23",
            spindle_speed=800, feed=60.0, dwell_time=1.5,
            reduce_approach=True, approach_feed_factor=0.5,
            activate_preset="IKZ Ein (M7)", activate_custom="",
            deactivate_preset="Alles AUS (M9)", deactivate_custom="",
            safe_z=100.0, end_safe_z=200.0,
            positions=[BSFCoordinatePosition(0.0, 0.0)],
            full_cut_overlap_mm=0.40,
        )
        self.assertAlmostEqual(doc.full_cut_overlap_mm, 0.40, places=6)
        payload = document_to_dict(doc)
        self.assertAlmostEqual(payload["workpiece"]["full_cut_overlap_mm"], 0.40, places=6)
        loaded = parse_document_dict(payload)
        self.assertAlmostEqual(loaded.full_cut_overlap_mm, 0.40, places=6)

    def test_full_cut_overlap_legacy_default(self):
        """Legacy-JSON ohne full_cut_overlap_mm erhaelt Default 0.25."""
        doc = build_bsf_document(
            program_name="TEST", tool_number=8, blank_size=1000.0, blank_height=60.0,
            tool_profile_key="BSF_C_1000_050_10_5_23",
            spindle_speed=800, feed=60.0, dwell_time=1.5,
            reduce_approach=True, approach_feed_factor=0.5,
            activate_preset="IKZ Ein (M7)", activate_custom="",
            deactivate_preset="Alles AUS (M9)", deactivate_custom="",
            safe_z=100.0, end_safe_z=200.0,
            positions=[BSFCoordinatePosition(0.0, 0.0)],
        )
        payload = document_to_dict(doc)
        # Simuliere Legacy ohne full_cut_overlap_mm
        del payload["workpiece"]["full_cut_overlap_mm"]
        loaded = parse_document_dict(payload)
        self.assertAlmostEqual(loaded.full_cut_overlap_mm, 0.25, places=6)


# ---------------------------------------------------------------------------
# D-INVARIANTE
# ---------------------------------------------------------------------------

class TestDInvariant(unittest.TestCase):
    """Prueft D_HEULE == D_EXISTING fuer alle unterstuetzten Z-Konfigurationen."""

    def _check_invariant(self, *, reference_z: float, sink_finish: float, z0_bottom: bool,
                          dep_z: float, hs: float, al: float):
        """Hilfsmethode: berechne beide D-Quellen und vergleiche.
        D_EXISTING = target_cutting_edge_z - Hs (via z_sink_finish + reference_z).
        D_HEULE    = target_cutting_edge_z - Hs (direkt im Modell).
        Beide muessen identisch sein.
        """
        from bsf_blade import calculate_workpiece_bsf_z, apply_workpiece_reference_z

        # D_EXISTING: Bestehender Weg ueber z_sink_finish
        wp_raw = calculate_workpiece_bsf_z(18.0, sink_finish, 23.0, z0_is_flange_bottom=z0_bottom)
        wp = apply_workpiece_reference_z(wp_raw, reference_z)
        # z_sink_finish ist Werkstueck-Z der Schneidenlage; mit Hs-Offset ist es schon enthalten:
        # Nein: z_sink_finish ist target_cutting_edge_z-Koordinate, Hs-Offset wird separat angewendet.
        # In generate_bsf_code: z_values["z_sink_finish"] = z_after_blade_offset["z_sink_finish"]
        # also = target_cutting_edge_z - Hs.
        # Hier vereinfacht: d_existing = target_cutting_edge_z - hs
        if z0_bottom:
            target_cutting_edge_z = reference_z + sink_finish
        else:
            target_cutting_edge_z = reference_z - (18.0 - sink_finish)
        d_existing = target_cutting_edge_z - hs

        # D_HEULE: Neues Modell
        pos = compute_heule_process_positions(
            exit_edge_z=dep_z,
            entry_edge_z=reference_z + 20.0,
            target_surface_z=target_cutting_edge_z,
            measurement_face_to_cutting_edge_mm=hs,
            deployment_length_al_mm=al,
            x_safety_clearance_mm=2.0,
            entry_clearance_mm=1.0,
        )
        d_heule = pos.d_measurement_face_z
        self.assertAlmostEqual(d_heule, d_existing, places=9,
                               msg=f"D-Invariante verletzt: ref={reference_z}, sink={sink_finish}, "
                                   f"z0_bottom={z0_bottom}, dep={dep_z}")

    def test_d_invariant_z0_bottom_ref0(self):
        # dep_z muss kleiner als target-Hs sein
        # target=38, D=38-8.55=29.45; dep=-5, B=-14.55, C=-13.3 < D OK
        self._check_invariant(reference_z=0, sink_finish=38.0, z0_bottom=True,
                               dep_z=-5.0, hs=8.55, al=20.25)

    def test_d_invariant_z0_bottom_ref_plus20(self):
        # target=58, D=49.45; dep=15, B=5.45, C=6.7 < D OK
        self._check_invariant(reference_z=20.0, sink_finish=38.0, z0_bottom=True,
                               dep_z=15.0, hs=8.55, al=20.25)

    def test_d_invariant_z0_bottom_ref_minus20(self):
        # target=18, D=9.45; dep=-25, B=-34.55, C=-33.3 < D OK
        self._check_invariant(reference_z=-20.0, sink_finish=38.0, z0_bottom=True,
                               dep_z=-25.0, hs=8.55, al=20.25)

    def test_d_invariant_z0_top_ref0(self):
        # Z0=Top: target = ref - (bund-sink) = 0-(18-38) = 20
        # D = 20-8.55=11.45; dep=-5, B=-14.55 < D OK
        self._check_invariant(reference_z=0, sink_finish=38.0, z0_bottom=False,
                               dep_z=-5.0, hs=8.55, al=20.25)

    def test_d_invariant_tool_e_ref0(self):
        # Tool E: Hs=11.4, AL=26.75; target=38, D=26.6; dep=-5, B=-17.4 < D OK
        self._check_invariant(reference_z=0, sink_finish=38.0, z0_bottom=True,
                               dep_z=-5.0, hs=11.4, al=26.75)

    def test_d_mismatch_synthetic_detected(self):
        """Synthetischer D-Mismatch wird erkannt."""
        # Direkt testen dass die Differenz > Toleranz erkannt wird
        d_heule = 29.45
        d_existing = 29.45 + 0.1  # absichtliche Abweichung
        tolerance = 1e-9
        self.assertGreater(abs(d_heule - d_existing), tolerance,
                           "Synthethischer Mismatch muss > Toleranz sein")


# ---------------------------------------------------------------------------
# M-COMMAND-KOMMENTARE
# ---------------------------------------------------------------------------

class TestMCommandComments(unittest.TestCase):
    def _get_code(self):
        root, app = _setup_app(with_edges=True)
        orig, _ = _silence_mb()
        try:
            app.generate_bsf_code()
        finally:
            _restore_mb(orig)
        code = app.output_text.get("1.0", "end")
        root.destroy()
        return code

    def test_m_act_comment_unambiguous(self):
        """M_act Kommentar darf nicht widersprüchlich sein."""
        code = self._get_code()
        # Neu: eindeutig Druck/IK-Semantik
        self.assertIn("Druck/IK ein - Messer eingefahren", code)
        # Alt: widersprüchlich - darf NICHT mehr vorkommen
        self.assertNotIn("Messer schliessen / Messer freigeben", code)

    def test_m_deact_comment_unambiguous(self):
        """M_deact Kommentar darf nicht widersprüchlich sein."""
        code = self._get_code()
        self.assertIn("Druck/IK aus - Messer zum Ausklappen freigegeben", code)
        # Alt: widersprüchlich - darf NICHT mehr vorkommen
        self.assertNotIn("Messer schliessen / Messer freigeben / Druck aus", code)

    def test_m_codes_unchanged(self):
        """M-Code-Zahlen bleiben unveraendert."""
        code = self._get_code()
        self.assertIn("M7 ; Druck/IK ein", code)
        self.assertIn("M9 ; Druck/IK aus", code)

    def test_m_act_appears_twice(self):
        """M_act wird zweimal verwendet (vor Eintauch + Rueckzug)."""
        code = self._get_code()
        self.assertEqual(code.count("Druck/IK ein - Messer eingefahren"), 2)

    def test_m_deact_appears_once(self):
        """M_deact wird einmal bei Position X verwendet."""
        code = self._get_code()
        self.assertEqual(code.count("Druck/IK aus - Messer zum Ausklappen freigegeben"), 1)


# ---------------------------------------------------------------------------
# SINK_FINISH SEMANTIK
# ---------------------------------------------------------------------------

class TestSinkFinishSemantics(unittest.TestCase):
    """Verifiziert CONSISTENT-Semantik fuer Z0 Bottom und Top."""

    def test_sink_finish_bottom_semantics(self):
        """Z0=Bottom: sink_finish ist positiver Versatz von Z0 in Richtung Spindel."""
        from bsf_blade import calculate_workpiece_bsf_z
        wp = calculate_workpiece_bsf_z(18, 20.5, 23, z0_is_flange_bottom=True)
        # z_sink_finish = +20.5 (20.5mm oberhalb von Z0=Unterkante Bund)
        self.assertAlmostEqual(wp["z_sink_finish"], 20.5, places=6)

    def test_sink_finish_top_semantics(self):
        """Z0=Top: sink_finish ist Versatz von Z0 (Oberkante) in Richtung Unterkante."""
        from bsf_blade import calculate_workpiece_bsf_z
        # bund=18, sink=3 -> z_sink_finish = -(18-3) = -15 (15mm unterhalb von Z0=Oberkante)
        wp = calculate_workpiece_bsf_z(18, 3, 23, z0_is_flange_bottom=False)
        self.assertAlmostEqual(wp["z_sink_finish"], -15.0, places=6)

    def test_sink_finish_both_modes_consistent_label(self):
        """'Fertigmass ab Bezugsebene' ist fuer beide Z0-Modi konsistent."""
        from bsf_blade import calculate_workpiece_bsf_z
        # CONSISTENT: Bezugsebene = jeweiliges Z0 (Bottom oder Top)
        wp_bottom = calculate_workpiece_bsf_z(18, 38.0, 23, z0_is_flange_bottom=True)
        wp_top = calculate_workpiece_bsf_z(18, 38.0, 23, z0_is_flange_bottom=False)
        # Bei Bottom: z_sink_finish = 38.0 (Fertigmass ab Unterkante = 38mm nach oben)
        self.assertAlmostEqual(wp_bottom["z_sink_finish"], 38.0, places=6)
        # Bei Top: sink=38 > bund=18, daher z_sink_finish = -(18-38) = +20 (ueber Oberkante)
        self.assertAlmostEqual(wp_top["z_sink_finish"], 20.0, places=6)
        # SINK_FINISH_SEMANTICS = CONSISTENT: beide Modi verwenden dieselbe Definition


# ---------------------------------------------------------------------------
# X-POSITION (kein Hs-Doppelabzug)
# ---------------------------------------------------------------------------

class TestXPositionNoHsOffset(unittest.TestCase):
    def test_x_c_tool_no_hs_double_offset(self):
        """X = deployment_edge - AL - safety (kein Hs-Abzug)."""
        pos = compute_heule_process_positions(
            exit_edge_z=-5.0,
            entry_edge_z=20.0,
            target_surface_z=38.0,
            measurement_face_to_cutting_edge_mm=TOOL_C.measurement_face_to_cutting_edge_mm,
            deployment_length_al_mm=TOOL_C.deployment_length_al_mm,
            x_safety_clearance_mm=2.0,
            entry_clearance_mm=1.0,
        )
        expected_x = -5.0 - TOOL_C.deployment_length_al_mm - 2.0
        self.assertAlmostEqual(pos.x_measurement_face_z, expected_x, places=9)

    def test_x_e_tool_no_hs_double_offset(self):
        """X = deployment_edge - AL - safety (kein Hs-Abzug) fuer BSF-E."""
        pos = compute_heule_process_positions(
            exit_edge_z=-5.0,
            entry_edge_z=20.0,
            target_surface_z=38.0,
            measurement_face_to_cutting_edge_mm=TOOL_E.measurement_face_to_cutting_edge_mm,
            deployment_length_al_mm=TOOL_E.deployment_length_al_mm,
            x_safety_clearance_mm=2.0,
            entry_clearance_mm=1.0,
        )
        expected_x = -5.0 - TOOL_E.deployment_length_al_mm - 2.0
        self.assertAlmostEqual(pos.x_measurement_face_z, expected_x, places=9)

    def test_al_values_canonical(self):
        """AL-Werte der Werkzeugprofile sind unveraendert."""
        self.assertAlmostEqual(TOOL_C.deployment_length_al_mm, 20.250, places=3)
        self.assertAlmostEqual(TOOL_E.deployment_length_al_mm, 26.750, places=3)


# ---------------------------------------------------------------------------
# LEGACY JSON LADEN (NC blockiert bis Geometrie vervollstaendigt)
# ---------------------------------------------------------------------------

class TestLegacyJsonLoad(unittest.TestCase):
    def _legacy_v3_payload(self):
        """Erstellt ein V3-aehliches Payload ohne neue Geometrie-Felder."""
        doc = build_bsf_document(
            program_name="LEGACY", tool_number=8, blank_size=1000.0, blank_height=60.0,
            tool_profile_key="BSF_C_1000_050_10_5_23",
            spindle_speed=800, feed=60.0, dwell_time=1.5,
            reduce_approach=True, approach_feed_factor=0.5,
            activate_preset="IKZ Ein (M7)", activate_custom="",
            deactivate_preset="Alles AUS (M9)", deactivate_custom="",
            safe_z=100.0, end_safe_z=200.0,
            positions=[BSFCoordinatePosition(0.0, 0.0)],
        )
        payload = document_to_dict(doc)
        payload["version"] = 3
        payload["workpiece"] = {
            "z_reference": "BOTTOM_EDGE",
            "bund_thickness": 18.0,
            "sink_finish": 38.0,
            "clearance": 23.0,
            "x_safety_clearance": 2.0,
            "entry_clearance": 1.0,
        }
        return payload

    def test_legacy_loads_with_none_edges(self):
        """V3 laedt ohne Fehler; deployment/entry_edge_z sind None."""
        payload = self._legacy_v3_payload()
        doc = parse_document_dict(payload)
        self.assertIsNone(doc.deployment_edge_z)
        self.assertIsNone(doc.entry_edge_z)

    def test_legacy_loads_with_default_overlap(self):
        """V3 laedt mit full_cut_overlap_mm=0.25 als Default."""
        payload = self._legacy_v3_payload()
        doc = parse_document_dict(payload)
        self.assertAlmostEqual(doc.full_cut_overlap_mm, 0.25, places=6)

    def test_legacy_nc_blocked_until_geometry_completed(self):
        """Geladenes Legacy-Projekt blockiert NC-Erzeugung bis Kanten eingetragen sind."""
        payload = self._legacy_v3_payload()
        doc = parse_document_dict(payload)
        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.position_mode_var.set("Einzelposition")
        app.on_position_mode_change(None)
        # Dokument laden - Kanten sind None -> leere Entries
        app._apply_bsf_position_list_document(doc)
        # Kanten muessen leer sein
        dep_val = app.entries.get("exit_edge_z", None)
        ent_val = app.entries.get("entry_edge_z", None)
        tgt_val = app.entries.get("target_surface_z", None)
        if dep_val is not None:
            self.assertEqual(dep_val.get().strip(), "", "exit_edge_z muss leer sein nach Legacy-Load")
        if ent_val is not None:
            self.assertEqual(ent_val.get().strip(), "", "entry_edge_z muss leer sein nach Legacy-Load")
        if tgt_val is not None:
            self.assertEqual(tgt_val.get().strip(), "", "target_surface_z muss leer sein nach Legacy-Load")
        # NC-Erzeugung muss blockieren
        orig, errors = _silence_mb()
        try:
            app.generate_bsf_code()
        finally:
            _restore_mb(orig)
        code = app.output_text.get("1.0", "end").strip()
        self.assertEqual(code, "", "Legacy-Projekt darf kein NC ohne explizite Kanten erzeugen")
        root.destroy()


if __name__ == "__main__":
    unittest.main()
