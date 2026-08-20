"""PHASE BSF.UIHELP.3 – vertikale Z-Hilfsgrafik."""
from __future__ import annotations

import unittest

import tkinter as tk

from help_views.bsf_geometry_model import build_bsf_geometry_help_snapshot
from heule_bsf_tools import BSF_TOOL_PROFILES
from ui.bsf_geometry_canvas import (
    AXIS_ORIENTATION,
    BLADE_CLOSED,
    BLADE_DEPLOYED,
    PLUS_Z_DIRECTION,
    draw_bsf_geometry,
)

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


def _draw(snap, *, blade=BLADE_CLOSED, tool_z=None):
    root = tk.Tk()
    root.withdraw()
    canvas = tk.Canvas(root, width=760, height=680)
    canvas.pack()
    root.update_idletasks()
    markers = draw_bsf_geometry(canvas, snap, blade_state=blade, tool_z=tool_z)
    return root, canvas, markers


class TestVerticalAxis(unittest.TestCase):
    def test_orientation_constants(self):
        self.assertEqual(AXIS_ORIENTATION, "VERTICAL")
        self.assertEqual(PLUS_Z_DIRECTION, "UP")

    def test_plus_z_up_minus_z_down(self):
        root, canvas, m = _draw(_snap())
        self.assertLess(m["A"], m["X"])
        self.assertLess(m["ENTRY"], m["EXIT"])
        self.assertLess(m["TARGET"], m["EXIT"])
        self.assertLess(m["D"], m["X"])
        self.assertLess(m["SAFE"], m["A"])
        self.assertTrue(canvas.find_withtag("axis_plus"))
        self.assertTrue(canvas.find_withtag("axis_minus"))
        self.assertTrue(canvas.find_withtag("z_axis"))
        root.destroy()

    def test_z0_horizontal_reference(self):
        root, canvas, m = _draw(_snap())
        self.assertIn("Z0", m)
        self.assertTrue(canvas.find_withtag("z0_line"))
        ids = canvas.find_withtag("z0_line")
        coords = canvas.coords(ids[0])
        self.assertAlmostEqual(coords[1], coords[3], places=1)
        root.destroy()

    def test_positions_and_safe_visible(self):
        root, canvas, m = _draw(_snap())
        for key in ("A", "X", "B", "C", "D", "SAFE", "MIN", "ENTRY", "EXIT", "TARGET"):
            self.assertIn(key, m)
        self.assertTrue(canvas.find_withtag("A"))
        self.assertTrue(canvas.find_withtag("X"))
        self.assertTrue(canvas.find_withtag("D"))
        self.assertTrue(canvas.find_withtag("legend"))
        self.assertTrue(canvas.find_withtag("dir_enter"))
        self.assertTrue(canvas.find_withtag("dir_sink"))
        root.destroy()

    def test_al_hs_visible(self):
        root, canvas, m = _draw(_snap(), blade=BLADE_DEPLOYED, tool_z=155.0)
        self.assertTrue(canvas.find_withtag("dim_al"))
        self.assertTrue(canvas.find_withtag("dim_hs"))
        self.assertTrue(canvas.find_withtag("blade_deployed"))
        root.destroy()

    def test_tool_closed_state(self):
        root, canvas, m = _draw(_snap(), blade=BLADE_CLOSED, tool_z=155.0)
        self.assertTrue(canvas.find_withtag("blade_closed"))
        self.assertFalse(canvas.find_withtag("blade_deployed"))
        root.destroy()

    def test_no_severe_label_overlap(self):
        root, canvas, m = _draw(_snap())
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
        self.assertLess(overlaps, 8, f"zu viele Textueberlappungen: {overlaps}")
        root.destroy()

    def test_process_direction_tags(self):
        root, canvas, m = _draw(_snap())
        # Einfahren: Pfeil nach unten (y steigt)
        enter = canvas.find_withtag("dir_enter_line")
        coords = canvas.coords(enter[0])
        self.assertGreater(coords[3], coords[1])
        sink = canvas.find_withtag("dir_sink_line")
        scoords = canvas.coords(sink[0])
        self.assertLess(scoords[3], scoords[1])
        root.destroy()


if __name__ == "__main__":
    unittest.main()
