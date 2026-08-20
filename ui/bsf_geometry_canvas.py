"""BSF-Geometrie-Canvas mit echter Z-Skalierung (+Z rechts, -Z links)."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from help_views.bsf_geometry_model import BSFGeometryHelpSnapshot, fmt_axis_z
from ui.bsf_safe_status import STATUS_OK, STATUS_TOO_LOW

BLADE_CLOSED = "CLOSED"
BLADE_DEPLOYED = "DEPLOYED"


@dataclass(frozen=True)
class ZScale:
    z_min: float
    z_max: float
    left: float
    right: float

    def map_z(self, z: float) -> float:
        if self.z_max <= self.z_min:
            return (self.left + self.right) / 2.0
        t = (z - self.z_min) / (self.z_max - self.z_min)
        return self.left + t * (self.right - self.left)


def collect_z_values(snapshot: BSFGeometryHelpSnapshot) -> List[float]:
    vals: List[float] = [0.0]
    for value in (
        snapshot.entry_edge_z,
        snapshot.exit_edge_z,
        snapshot.target_surface_z,
        snapshot.raw_surface_z,
        snapshot.a_z,
        snapshot.x_z,
        snapshot.b_z,
        snapshot.c_z,
        snapshot.d_z,
        snapshot.safe_z,
        snapshot.end_safe_z,
        snapshot.required_safe_z,
    ):
        if value is not None:
            vals.append(float(value))
    return vals


def build_z_scale(values: Sequence[float], *, left: float, right: float, pad_ratio: float = 0.08) -> ZScale:
    if not values:
        return ZScale(-10.0, 10.0, left, right)
    z_min = min(values)
    z_max = max(values)
    if abs(z_max - z_min) < 1e-9:
        z_min -= 5.0
        z_max += 5.0
    span = z_max - z_min
    pad = span * pad_ratio
    return ZScale(z_min - pad, z_max + pad, left, right)


def _label_slots(xs: Sequence[float], y_base: float, step: float = 16.0) -> List[float]:
    """Verteilt Labels vertikal, wenn X-Positionen nah beieinander liegen."""
    if not xs:
        return []
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ys = [y_base] * len(xs)
    last_x = None
    lane = 0
    for idx in order:
        x = xs[idx]
        if last_x is not None and abs(x - last_x) < 28:
            lane += 1
        else:
            lane = 0
        ys[idx] = y_base - lane * step
        last_x = x
    return ys


def _draw_dimension(
    canvas: tk.Canvas,
    scale: ZScale,
    z0: float,
    z1: float,
    y: float,
    label: str,
    *,
    color: str = "#57606a",
) -> None:
    x0 = scale.map_z(z0)
    x1 = scale.map_z(z1)
    if abs(x1 - x0) < 4:
        return
    canvas.create_line(x0, y, x1, y, fill=color, arrow=tk.BOTH, width=1)
    canvas.create_text((x0 + x1) / 2.0, y - 10, text=label, fill=color, font=("Segoe UI", 8))


def draw_bsf_tool(
    canvas: tk.Canvas,
    *,
    x: float,
    y: float,
    blade_state: str,
    hs_px: float = 18.0,
    al_px: float = 28.0,
) -> None:
    """Schematisches Werkzeug: Schaft, Vermess-Stirn, Messer."""
    # Schaft nach +Z (rechts)
    canvas.create_rectangle(x, y - 8, x + 70, y + 8, fill="#8b949e", outline="#1f2328", tags=("tool",))
    # Vermess-Stirnfläche
    canvas.create_line(x, y - 14, x, y + 14, fill="#cf222e", width=3, tags=("tool", "meas_face"))
    canvas.create_text(x - 4, y - 22, anchor="e", text="Vermess", fill="#cf222e", font=("Segoe UI", 7), tags=("tool",))
    # Hs-Markierung
    canvas.create_line(x, y + 18, x - hs_px, y + 18, fill="#8250df", arrow=tk.LAST, tags=("tool",))
    canvas.create_text(x - hs_px / 2, y + 28, text="Hs", fill="#8250df", font=("Segoe UI", 7), tags=("tool",))
    if blade_state == BLADE_DEPLOYED:
        # ausgeklappte Schneide nach oben/unten
        canvas.create_polygon(
            x - hs_px,
            y,
            x - hs_px - 10,
            y - 16,
            x - hs_px + 4,
            y - 8,
            fill="#1f883d",
            outline="#1f2328",
            tags=("tool", "blade"),
        )
        canvas.create_polygon(
            x - hs_px,
            y,
            x - hs_px - 10,
            y + 16,
            x - hs_px + 4,
            y + 8,
            fill="#1f883d",
            outline="#1f2328",
            tags=("tool", "blade"),
        )
        canvas.create_text(x - al_px, y - 34, text="AL", fill="#0969da", font=("Segoe UI", 7), tags=("tool",))
    else:
        # eingeklappt
        canvas.create_rectangle(
            x - hs_px - 4,
            y - 4,
            x - 2,
            y + 4,
            fill="#57606a",
            outline="#1f2328",
            tags=("tool", "blade"),
        )


def draw_bsf_geometry(
    canvas: tk.Canvas,
    snapshot: BSFGeometryHelpSnapshot,
    *,
    tool_z: Optional[float] = None,
    blade_state: str = BLADE_CLOSED,
    show_tool: bool = True,
    title: Optional[str] = None,
) -> Dict[str, float]:
    """Zeichnet Geometrie aus realen Z-Werten. Gibt Marker-X-Positionen zurueck."""
    canvas.delete("all")
    w = max(320, int(canvas.winfo_width() or 640))
    h = max(220, int(canvas.winfo_height() or 360))
    left, right = 40.0, w - 40.0
    y = h * 0.48

    values = collect_z_values(snapshot)
    scale = build_z_scale(values, left=left, right=right)
    markers: Dict[str, float] = {}

    header = title or "Werkzeug von +Z/rechts | Einfahren -Z/links | Rueckwaertssenken +Z"
    canvas.create_text(12, 12, anchor="w", text=header, font=("Segoe UI", 9), fill="#1f2328")
    canvas.create_text(12, 30, anchor="w", text="← -Z zur Werkzeugspitze          +Z zur Spindel →", fill="#57606a")

    if snapshot.a_z is None or snapshot.exit_edge_z is None or snapshot.entry_edge_z is None:
        canvas.create_rectangle(
            int(w * 0.28),
            y - 32,
            int(w * 0.72),
            y + 32,
            fill="#d0d7de",
            outline="#57606a",
            tags=("flange",),
        )
        canvas.create_text(
            w / 2,
            h / 2,
            text="Geometrie unvollstaendig\n" + "\n".join(snapshot.notes or ["Felder fehlen"]),
            fill="#cf222e",
            font=("Segoe UI", 11, "bold"),
            justify=tk.CENTER,
        )
        return markers

    entry = float(snapshot.entry_edge_z)
    exit_z = float(snapshot.exit_edge_z)
    target = float(snapshot.target_surface_z) if snapshot.target_surface_z is not None else exit_z
    x_entry = scale.map_z(entry)
    x_exit = scale.map_z(exit_z)
    x_target = scale.map_z(target)
    x0 = scale.map_z(0.0)

    # Werkstueckkoerper (Querschnitt)
    body_top = y - 46
    body_bot = y + 46
    x_left_body = min(x_exit, x_entry) - 8
    x_right_body = max(x_exit, x_entry) + 8
    canvas.create_rectangle(
        x_left_body,
        body_top,
        x_right_body,
        body_bot,
        fill="#c9d1d9",
        outline="#57606a",
        width=2,
        tags=("flange", "workpiece"),
    )
    # Durchgangsbohrung
    hole_h = 28
    canvas.create_rectangle(
        min(x_exit, x_entry),
        y - hole_h / 2,
        max(x_exit, x_entry),
        y + hole_h / 2,
        fill="#f6f8fa",
        outline="#57606a",
        tags=("hole",),
    )
    # Senkung (schematisch an Austrittsseite Richtung Ziel)
    sink_y0 = y - hole_h / 2
    canvas.create_polygon(
        x_exit,
        sink_y0,
        x_target,
        sink_y0 - 10,
        x_target,
        sink_y0 + hole_h + 10,
        x_exit,
        sink_y0 + hole_h,
        fill="#b6e3b6",
        outline="#1f883d",
        stipple="gray50",
    )

    # Z0-Linie
    canvas.create_line(x0, 48, x0, h - 70, fill="#1f2328", width=2, dash=(4, 2))
    canvas.create_text(x0 + 4, 52, anchor="nw", text="Z0 = 0,000", fill="#1f2328", font=("Segoe UI", 9, "bold"))

    # Flaechenmarker
    for z, label, color in (
        (entry, "Eintritt", "#0969da"),
        (exit_z, "Austritt/Senkseite", "#8250df"),
        (target, "Ziel-Senkflaeche", "#1f883d"),
    ):
        xz = scale.map_z(z)
        canvas.create_line(xz, body_top - 6, xz, body_bot + 6, fill=color, dash=(2, 2))
        canvas.create_text(xz, body_bot + 16, text=label, fill=color, font=("Segoe UI", 7))

    if snapshot.raw_surface_z is not None:
        xr = scale.map_z(float(snapshot.raw_surface_z))
        canvas.create_line(xr, body_top, xr, body_bot, fill="#bf8700", dash=(1, 2))
        canvas.create_text(xr, body_top - 10, text="Roh", fill="#bf8700", font=("Segoe UI", 7))

    # Prozesspositionen
    pos_defs = [
        ("A", snapshot.a_z, "Anfahrt vor Eintritt", "#1f883d"),
        ("X", snapshot.x_z, "Ausklappposition", "#0969da"),
        ("B", snapshot.b_z, "1 mm vor Eingriff", "#8250df"),
        ("C", snapshot.c_z, "Schneide greift", "#bf3989"),
        ("D", snapshot.d_z, "Fertigposition Vermessflaeche", "#cf222e"),
    ]
    xs = [scale.map_z(float(z)) for _, z, _, _ in pos_defs if z is not None]
    labels_y = _label_slots(xs, y_base=body_top - 18)
    yi = 0
    for letter, z, meaning, color in pos_defs:
        if z is None:
            continue
        xz = scale.map_z(float(z))
        markers[letter] = xz
        markers[f"{letter}_z"] = float(z)
        canvas.create_line(xz, body_top - 4, xz, body_bot + 4, fill=color, width=2)
        ly = labels_y[yi] if yi < len(labels_y) else body_top - 18
        yi += 1
        canvas.create_text(
            xz,
            ly,
            text=f"{letter}  {fmt_axis_z(z)}\n{meaning}",
            fill=color,
            font=("Segoe UI", 8, "bold"),
            justify=tk.CENTER,
        )

    # Dimensionen
    tool = snapshot.tool_profile
    if tool is not None and snapshot.x_z is not None:
        _draw_dimension(
            canvas,
            scale,
            float(snapshot.x_z),
            exit_z,
            body_bot + 34,
            f"AL+Sicherheit = {exit_z - float(snapshot.x_z):.3f}",
            color="#0969da",
        )
        hs = float(tool.measurement_face_to_cutting_edge_mm)
        if snapshot.d_z is not None and snapshot.target_surface_z is not None:
            _draw_dimension(
                canvas,
                scale,
                float(snapshot.d_z),
                float(snapshot.target_surface_z),
                body_bot + 52,
                f"Hs = {hs:.3f}",
                color="#8250df",
            )
    if snapshot.sink_depth is not None:
        _draw_dimension(
            canvas,
            scale,
            exit_z,
            target,
            body_top - 52,
            f"Senktiefe {snapshot.sink_depth:.3f}",
            color="#1f883d",
        )
    if snapshot.material_removal is not None and snapshot.raw_surface_z is not None:
        _draw_dimension(
            canvas,
            scale,
            float(snapshot.raw_surface_z),
            target,
            body_top - 68,
            f"Abtrag {snapshot.material_removal:.3f}",
            color="#bf8700",
        )

    # Safe-Z Visual
    if snapshot.required_safe_z is not None:
        xr = scale.map_z(float(snapshot.required_safe_z))
        canvas.create_line(xr, 48, xr, h - 60, fill="#bf8700", dash=(6, 3))
        canvas.create_text(xr, h - 48, text=f"Min-Safe {fmt_axis_z(snapshot.required_safe_z)}", fill="#bf8700", font=("Segoe UI", 8))
    if snapshot.safe_z is not None:
        xs = scale.map_z(float(snapshot.safe_z))
        markers["SAFE"] = xs
        color = "#1f883d" if snapshot.safe_status == STATUS_OK else "#cf222e"
        canvas.create_line(xs, 48, xs, h - 60, fill=color, width=2)
        if snapshot.safe_status == STATUS_TOO_LOW and snapshot.a_z is not None:
            msg = f"⚠ Safe-Z {fmt_axis_z(snapshot.safe_z)} liegt UNTER A {fmt_axis_z(snapshot.a_z)}"
        elif snapshot.safe_status == STATUS_OK:
            msg = f"✓ Safe-Z {fmt_axis_z(snapshot.safe_z)} liegt oberhalb aller Prozesspositionen"
        else:
            msg = f"Safe-Z {fmt_axis_z(snapshot.safe_z)}"
        canvas.create_text(w / 2, h - 18, text=msg, fill=color, font=("Segoe UI", 9, "bold"))

    if show_tool:
        tz = tool_z if tool_z is not None else snapshot.a_z
        if tz is not None:
            draw_bsf_tool(canvas, x=scale.map_z(float(tz)), y=y, blade_state=blade_state)
            markers["TOOL"] = scale.map_z(float(tz))

    markers["Z0"] = x0
    markers["ENTRY"] = x_entry
    markers["EXIT"] = x_exit
    markers["TARGET"] = x_target
    return markers
