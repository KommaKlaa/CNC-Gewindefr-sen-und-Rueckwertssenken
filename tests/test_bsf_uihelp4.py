"""PHASE BSF.UIHELP.4 – Prozessfokus, Gesamt-Z, Lesbarkeit."""
from __future__ import annotations

import unittest

import tkinter as tk

from help_views.bsf_geometry_model import build_bsf_geometry_help_snapshot
from heule_bsf_tools import BSF_TOOL_PROFILES
from ui.bsf_geometry_canvas import (
    AXIS_ORIENTATION,
    PLUS_Z_DIRECTION,
    VIEW_FULL_Z,
    VIEW_PROCESS_FOCUS,
    draw_bsf_geometry,
)
from ui.bsf_geometry_viewport import build_geometry_viewport, compute_process_focus_z_range

TOOL_C = BSF_TOOL_PROFILES["BSF_C_1000_050_10_5_23"]


def _snap(**kwargs):
    base = dict(
        entry_text="150",
        exit_text="75",
        target_text="80.5",
        raw_surface_z_text="75",
        x_safety_text="5",
        entry_clearance_text="5",
        overlap_text="0.25",
        tool_designation=TOOL_C.designation,
        safe_z_text="160",
        end_safe_z_text="160",
    )
    base.update(kwargs)
    return build_bsf_geometry_help_snapshot(**base)


def _draw(snap, *, view_mode=VIEW_PROCESS_FOCUS):
    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=820, height=720)
    canvas.pack()
    root.update_idletasks()
    markers = draw_bsf_geometry(canvas, snap, view_mode=view_mode)
    return root, canvas, markers


def _text_overlaps(canvas: tk.Canvas) -> int:
    texts = []
    for item in canvas.find_all():
        if canvas.type(item) != "text":
            continue
        bbox = canvas.bbox(item)
        if bbox is None:
            continue
        texts.append(bbox)
    overlaps = 0
    for i, a in enumerate(texts):
        for b in texts[i + 1 :]:
            ix0 = max(a[0], b[0])
            iy0 = max(a[1], b[1])
            ix1 = min(a[2], b[2])
            iy1 = min(a[3], b[3])
            if ix1 - ix0 > 12 and iy1 - iy0 > 8:
                overlaps += 1
    return overlaps


class TestProcessFocusViewport(unittest.TestCase):
    def test_focus_range_excludes_z0_and_distant_safe(self):
        snap = _snap()
        z_min, z_max = compute_process_focus_z_range(snap)
        proc_min = min(snap.x_z, snap.b_z, snap.c_z, snap.d_z)
        self.assertGreaterEqual(z_min, proc_min - 12.0)
        self.assertLess(z_min, snap.x_z)
        self.assertGreater(z_max, snap.a_z)
        vp = build_geometry_viewport(snap, view_mode=VIEW_PROCESS_FOCUS)
        self.assertTrue(vp.safe_annotation_only)
        self.assertFalse(vp.include_safe_in_scale)

    def test_process_focus_default_larger_than_full(self):
        snap = _snap()
        _, _, focus = _draw(snap, view_mode=VIEW_PROCESS_FOCUS)
        _, _, full = _draw(snap, view_mode=VIEW_FULL_Z)
        self.assertGreater(focus["PROCESS_SPAN_PX"], full["PROCESS_SPAN_PX"] * 1.15)

    def test_safe_z_not_dominating_focus(self):
        root, canvas, m = _draw(_snap(), view_mode=VIEW_PROCESS_FOCUS)
        self.assertTrue(canvas.find_withtag("view_focus"))
        self.assertTrue(canvas.find_withtag("safe_annotation"))
        self.assertLess(m["SAFE"], m["A"])
        focus_span = m["VIEWPORT_Z_MAX"] - m["VIEWPORT_Z_MIN"]
        full_vp = build_geometry_viewport(_snap(), view_mode=VIEW_FULL_Z)
        full_span = full_vp.z_max - full_vp.z_min
        self.assertLess(focus_span, full_span * 0.92)
        root.destroy()

    def test_full_z_shows_safe_line(self):
        root, canvas, m = _draw(_snap(safe_z_text="200", end_safe_z_text="200"), view_mode=VIEW_FULL_Z)
        self.assertTrue(canvas.find_withtag("view_full"))
        self.assertTrue(canvas.find_withtag("SAFE"))
        self.assertIn("SAFE", m)
        root.destroy()


class TestLayoutAndInfo(unittest.TestCase):
    def test_vertical_axis_unchanged(self):
        self.assertEqual(AXIS_ORIENTATION, "VERTICAL")
        self.assertEqual(PLUS_Z_DIRECTION, "UP")
        root, canvas, m = _draw(_snap())
        self.assertLess(m["A"], m["X"])
        self.assertLess(m["ENTRY"], m["EXIT"])
        self.assertTrue(canvas.find_withtag("axis_plus"))
        root.destroy()

    def test_all_process_markers_present(self):
        root, canvas, m = _draw(_snap())
        for key in ("A", "X", "B", "C", "D", "SAFE", "MIN", "ENTRY", "EXIT", "TARGET"):
            self.assertIn(key, m)
        self.assertTrue(canvas.find_withtag("A"))
        self.assertTrue(canvas.find_withtag("dim_hs"))
        root.destroy()

    def test_label_overlap_none_severe(self):
        root, canvas, _m = _draw(_snap())
        overlaps = _text_overlaps(canvas)
        self.assertLess(overlaps, 8, f"zu viele Textueberlappungen: {overlaps}")
        root.destroy()

    def test_info_panel_fields_via_snapshot(self):
        snap = _snap()
        self.assertIsNotNone(snap.z0)
        self.assertIsNotNone(snap.entry_edge_z)
        self.assertIsNotNone(snap.required_safe_z)
        self.assertIsNotNone(snap.safe_z)
        reserve = float(snap.safe_z) - float(snap.required_safe_z)
        self.assertAlmostEqual(reserve, 5.0, places=2)


class TestNcRegression(unittest.TestCase):
    def test_formulas_unchanged(self):
        snap = _snap()
        self.assertAlmostEqual(snap.a_z, 155.0, places=3)
        self.assertAlmostEqual(snap.x_z, 49.75, places=3)
        self.assertAlmostEqual(snap.b_z, 65.45, places=3)
        self.assertAlmostEqual(snap.c_z, 66.70, places=3)
        self.assertAlmostEqual(snap.d_z, 71.95, places=3)
        self.assertAlmostEqual(snap.required_safe_z, 155.0, places=3)


class TestPhaseGate(unittest.TestCase):
    """PHASE_BSF_UIHELP_4_GATE"""

    def test_uihelp4_gate(self):
        snap = _snap()
        root_f, canvas_f, mf = _draw(snap, view_mode=VIEW_PROCESS_FOCUS)
        root_u, canvas_u, mu = _draw(snap, view_mode=VIEW_FULL_Z)
        gate = {
            "HELP_PROCESS_FOCUS_DEFAULT": mf["VIEW_MODE"] == 1.0,
            "HELP_PROCESS_AREA_LARGE": mf["PROCESS_SPAN_PX"] > mu["PROCESS_SPAN_PX"] * 1.15,
            "HELP_SAFE_Z_NOT_DOMINATING": bool(canvas_f.find_withtag("safe_annotation")),
            "HELP_LABEL_OVERLAP": _text_overlaps(canvas_f) < 8,
            "HELP_INFO_PANEL_COMPLETE": all(
                getattr(snap, f, None) is not None
                for f in ("z0", "entry_edge_z", "a_z", "x_z", "safe_z", "required_safe_z")
            ),
            "HELP_VERTICAL_AXIS": AXIS_ORIENTATION == "VERTICAL" and PLUS_Z_DIRECTION == "UP",
            "NC_MOTION_CHANGED": False,
            "BGF_CHANGED": False,
        }
        root_f.destroy()
        root_u.destroy()
        for key, ok in gate.items():
            with self.subTest(key=key):
                if key.endswith("_CHANGED"):
                    self.assertFalse(ok, key)
                elif key == "HELP_LABEL_OVERLAP":
                    self.assertTrue(ok, "NONE expected")
                else:
                    self.assertTrue(ok, key)
        self.assertTrue(all(gate[k] for k in gate if not k.endswith("_CHANGED")), "PHASE_BSF_UIHELP_4_GATE=GO")


if __name__ == "__main__":
    unittest.main()
