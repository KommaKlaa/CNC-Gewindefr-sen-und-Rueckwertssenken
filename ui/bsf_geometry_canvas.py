"""Canvas-Darstellung fuer den Reiter 'Eigene Geometrie'."""

from __future__ import annotations

import tkinter as tk

from help_views.bsf_geometry_model import BSFGeometryHelpSnapshot, fmt_axis_z


def draw_bsf_geometry(canvas: tk.Canvas, snapshot: BSFGeometryHelpSnapshot) -> None:
    canvas.delete("all")
    w = max(200, int(canvas.winfo_width()))
    h = max(160, int(canvas.winfo_height()))

    canvas.create_text(12, 12, anchor="w", text="Werkzeug rechts | -Z: nach links | +Z: nach rechts")
    canvas.create_line(20, h // 2, w - 20, h // 2, fill="#667788", dash=(3, 3))

    x_a = int(w * 0.82)
    x_x = int(w * 0.34)
    x_d = int(w * 0.62)
    y = h // 2

    # Werkstueck / Bohrung
    canvas.create_rectangle(
        int(w * 0.28), y - 32, int(w * 0.72), y + 32,
        fill="#d0d7de", outline="#57606a", tags=("flange",),
    )
    canvas.create_rectangle(
        int(w * 0.45), y - 20, int(w * 0.55), y + 20,
        fill="#f6f8fa", outline="#57606a", tags=("hole",),
    )

    # Prozesspositionen (schematisch)
    canvas.create_text(x_a, y - 42, text="A", fill="#1f883d", font=("Segoe UI", 10, "bold"))
    canvas.create_text(x_x, y - 42, text="X", fill="#0969da", font=("Segoe UI", 10, "bold"))
    canvas.create_text(x_d, y + 48, text="D", fill="#cf222e", font=("Segoe UI", 10, "bold"))
    canvas.create_line(x_a, y - 2, x_x, y - 2, arrow=tk.LAST, fill="#57606a", width=2)
    canvas.create_line(x_x, y + 2, x_d, y + 2, arrow=tk.LAST, fill="#cf222e", width=2)

    canvas.create_text(14, h - 74, anchor="w", text=f"Bezugsebene: Z{fmt_axis_z(snapshot.reference_z)}")
    canvas.create_text(14, h - 56, anchor="w", text=f"Rohflaeche: Z{fmt_axis_z(snapshot.raw_surface_z)}")
    canvas.create_text(14, h - 38, anchor="w", text=f"Ziel-Senkflaeche: Z{fmt_axis_z(snapshot.target_cutting_edge_z)}")
    if snapshot.material_removal is None:
        removal = "—"
    else:
        removal = f"{snapshot.material_removal:.3f} mm"
    canvas.create_text(14, h - 20, anchor="w", text=f"Materialabtrag: {removal}")
