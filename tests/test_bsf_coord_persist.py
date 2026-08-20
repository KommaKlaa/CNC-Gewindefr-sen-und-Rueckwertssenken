from __future__ import annotations

import tempfile
import unittest

import bsf_generator_verbessert_v3 as gen
from coordinates import BSFCoordinatePosition, build_bsf_document, load_bsf_document_json, save_bsf_document_json
from coordinates.bsf_list_document import FORMAT_NAME, FORMAT_VERSION, document_to_dict, parse_document_dict
from heule_bsf_tools import BSF_TOOL_PROFILES
from ui import MODE_BSF

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]
TOOL_E = BSF_TOOL_PROFILES["BSF_E_1350_050_16_5_14"]


def _legacy_workpiece_fields() -> dict:
    """Minimale V1–V4-Werkstückfelder ohne Auto-Migration auf V5-Z."""
    return {
        "z_reference": "BOTTOM_EDGE",
        "reference_z": 0.0,
        "bund_thickness": 18.0,
        "sink_finish": 38.0,
        "clearance": 23.0,
    }


def _doc(tool_profile_key: str = TOOL_C.key, **kwargs):
    base = dict(
        program_name="BSF_TEST",
        tool_number=8,
        blank_size=1000.0,
        blank_height=60.0,
        tool_profile_key=tool_profile_key,
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
    return build_bsf_document(**base)


class TestBsfPersist(unittest.TestCase):
    def test_v2_roundtrip_tool_c(self):
        doc = _doc(TOOL_C.key)
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}\\x.bsf.json"
            save_bsf_document_json(path, doc)
            loaded = load_bsf_document_json(path)
        self.assertEqual(loaded.format_name, FORMAT_NAME)
        self.assertEqual(loaded.version, FORMAT_VERSION)
        self.assertEqual(loaded.tool_profile_key, TOOL_C.key)

    def test_v2_roundtrip_tool_e(self):
        payload = document_to_dict(_doc(TOOL_E.key))
        loaded = parse_document_dict(payload)
        self.assertEqual(loaded.tool_profile_key, TOOL_E.key)
        self.assertNotIn("blade", payload)
        self.assertNotIn("activation_speed_rpm", str(payload))

    def test_legacy_v1_load_blocks_tool_selection(self):
        payload = document_to_dict(_doc())
        payload["version"] = 1
        payload["blade"] = {"thickness": 3.0, "measurement_reference": "SPINDLE_SIDE_EDGE"}
        del payload["tool"]
        payload["workpiece"] = _legacy_workpiece_fields()
        loaded = parse_document_dict(payload)
        self.assertIsNone(loaded.tool_profile_key)
        self.assertEqual(loaded.reference_z, 0.0)

    def test_gui_apply_legacy_keeps_positions_but_no_tool(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        payload = document_to_dict(_doc())
        payload["version"] = 1
        payload["blade"] = {"thickness": 3.0, "measurement_reference": "SPINDLE_SIDE_EDGE"}
        del payload["tool"]
        payload["workpiece"] = _legacy_workpiece_fields()
        doc = parse_document_dict(payload)
        app._apply_bsf_position_list_document(doc)
        self.assertEqual(app.bsf_tool_profile_var.get(), "--- bitte HEULE-Werkzeug waehlen ---")
        self.assertEqual(len(app.bsf_coord_rows), 2)
        root.destroy()

    def test_json_roundtrip_activation_from_profile(self):
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        app = gen.BSFGeneratorGUI(root)
        app.mode_var.set(MODE_BSF)
        app.on_mode_change(None)
        app.bsf_tool_profile_var.set(TOOL_C.designation)
        app.on_bsf_tool_profile_change()
        app.entries["spindle_speed"].delete(0, "end")
        app.entries["spindle_speed"].insert(0, "777")
        # FAIL-CLOSED: Pflichtparameter setzen
        for k, v in [
            
            ("safe_z", "100"), ("end_safe_z", "200"),
            ("feed_rate", "60"), ("dwell_time", "1.5"),
            ("entry_edge_z", "20"), ("exit_edge_z", "-5"), ("target_surface_z", "38"),
            ("x_safety_clearance", "2.000"), ("entry_clearance", "1.000"),
            ("full_cut_overlap_mm", "0.250"),
        ]:
            app.entries[k].delete(0, "end")
            app.entries[k].insert(0, v)
        app.bsf_coord_rows = [BSFCoordinatePosition(0.0, 0.0)]
        app.position_mode_var.set("Koordinatenliste")
        app.on_position_mode_change(None)
        doc = app._collect_bsf_position_list_document()
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}\\c.bsf.json"
            save_bsf_document_json(path, doc)
            loaded = load_bsf_document_json(path)
        app._apply_bsf_position_list_document(loaded)
        app.generate_bsf_code()
        code = app.output_text.get("1.0", "end")
        self.assertIn("TOOL CALL 8 Z S777", code)
        self.assertIn("S2000 M3 ; Spindel einschalten", code)
        root.destroy()


if __name__ == "__main__":
    unittest.main()
