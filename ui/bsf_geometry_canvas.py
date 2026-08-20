"""BSF-Geometrie-Canvas: vertikale Z-Achse (+Z oben, -Z unten)."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

from ui.bsf_geometry_viewport import (
    DEFAULT_VIEW,
    VIEW_FULL_Z,
    VIEW_PROCESS_FOCUS,
    build_geometry_viewport,
)
from ui.bsf_safe_status import STATUS_OK, STATUS_TOO_LOW

if TYPE_CHECKING:
    from help_views.bsf_geometry_model import BSFGeometryHelpSnapshot

BLADE_CLOSED = "CLOSED"
BLADE_DEPLOYED = "DEPLOYED"
AXIS_ORIENTATION = "VERTICAL"
PLUS_Z_DIRECTION = "UP"


def _fmt_axis_z(value: Optional[float]) -> str:
    if value is None:
        return "—"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.4f}"


FONT_TITLE = ("Segoe UI", 11, "bold")
FONT_LABEL = ("Segoe UI", 9)
FONT_LABEL_B = ("Segoe UI", 9, "bold")
FONT_LEGEND = ("Segoe UI", 9)
FONT_DIM = ("Segoe UI", 8, "bold")
FONT_BADGE = ("Segoe UI", 8, "bold")


@dataclass(frozen=True)
class ZScale:
    """Kartesische Z-Skala: +Z nach oben (kleinere Canvas-Y)."""

    z_min: float
    z_max: float
    top: float
    bottom: float

    def map_z(self, z: float) -> float:
        if self.z_max <= self.z_min:
            return (self.top + self.bottom) / 2.0
        t = (z - self.z_min) / (self.z_max - self.z_min)
        return self.bottom - t * (self.bottom - self.top)

    def span_px(self) -> float:
        return self.bottom - self.top


def collect_z_values(snapshot: "BSFGeometryHelpSnapshot") -> List[float]:
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


def build_z_scale(
    values: Sequence[float],
    *,
    top: float,
    bottom: float,
    pad_ratio: float = 0.10,
    left: float | None = None,
    right: float | None = None,
) -> ZScale:
    """Baut die vertikale Skala. left/right bleiben als Alias fuer Tests ignoriert."""
    if left is not None and right is not None and top == 0 and bottom == 0:
        top, bottom = left, right
    if not values:
        return ZScale(-10.0, 10.0, top, bottom)
    z_min = min(values)
    z_max = max(values)
    if abs(z_max - z_min) < 1e-9:
        z_min -= 5.0
        z_max += 5.0
    span = z_max - z_min
    pad = span * pad_ratio
    return ZScale(z_min - pad, z_max + pad, top, bottom)


def _spread_ys(ys: Sequence[float], min_gap: float = 18.0) -> List[float]:
    if not ys:
        return []
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    out = [float(y) for y in ys]
    for k in range(1, len(order)):
        cur, prev = order[k], order[k - 1]
        if out[cur] < out[prev] + min_gap:
            out[cur] = out[prev] + min_gap
    return out


def _hline(
    canvas: tk.Canvas,
    y: float,
    x0: float,
    x1: float,
    *,
    color: str,
    width: int = 1,
    dash: Optional[Tuple[int, ...]] = None,
    tags: Tuple[str, ...] = (),
) -> None:
    canvas.create_line(x0, y, x1, y, fill=color, width=width, dash=dash, tags=tags)


def _z_in_viewport(z: float, scale: ZScale) -> bool:
    return scale.z_min <= z <= scale.z_max


def draw_bsf_tool(
    canvas: tk.Canvas,
    *,
    cx: float,
    y_face: float,
    blade_state: str,
    hs_px: float,
    al_px: float,
    x_dim: float,
) -> None:
    """Vertikales Werkzeug: Schaft nach +Z (oben), Stirn, Hs/AL nach -Z (unten)."""
    hs_px = max(14.0, hs_px)
    al_px = max(hs_px + 8.0, al_px)
    y_cut = y_face + hs_px
    y_al = y_face + al_px
    canvas.create_rectangle(
        cx - 10, y_face - 72, cx + 10, y_face,
        fill="#8b949e", outline="#1f2328", tags=("tool", "shaft"),
    )
    canvas.create_rectangle(
        cx - 16, y_face - 84, cx + 16, y_face - 70,
        fill="#6e7781", outline="#1f2328", tags=("tool",),
    )
    canvas.create_line(
        cx - 20, y_face, cx + 20, y_face,
        fill="#cf222e", width=3, tags=("tool", "meas_face"),
    )
    canvas.create_text(
        cx + 24, y_face, anchor="w", text="Vermess-Stirn",
        fill="#cf222e", font=FONT_DIM, tags=("tool",),
    )
    canvas.create_line(
        x_dim, y_face, x_dim, y_cut,
        fill="#8250df", width=2, arrow=tk.BOTH, tags=("tool", "dim_hs"),
    )
    canvas.create_text(
        x_dim + 6, (y_face + y_cut) / 2,
        anchor="w", text="Hs", fill="#8250df", font=FONT_DIM, tags=("dim_hs",),
    )
    canvas.create_line(
        x_dim + 22, y_face, x_dim + 22, y_al,
        fill="#0969da", width=2, arrow=tk.BOTH, tags=("tool", "dim_al"),
    )
    canvas.create_text(
        x_dim + 28, (y_face + y_al) / 2,
        anchor="w", text="AL", fill="#0969da", font=FONT_DIM, tags=("dim_al",),
    )
    if blade_state == BLADE_DEPLOYED:
        canvas.create_polygon(
            cx, y_cut, cx - 28, y_cut - 8, cx - 28, y_cut + 8,
            fill="#1f883d", outline="#1f2328", tags=("tool", "blade", "blade_deployed"),
        )
        canvas.create_polygon(
            cx, y_cut, cx + 28, y_cut - 8, cx + 28, y_cut + 8,
            fill="#1f883d", outline="#1f2328", tags=("tool", "blade", "blade_deployed"),
        )
    else:
        canvas.create_rectangle(
            cx - 5, y_face + 2, cx + 5, y_cut,
            fill="#57606a", outline="#1f2328", tags=("tool", "blade", "blade_closed"),
        )


def _draw_safe_annotation(
    canvas: tk.Canvas,
    *,
    w: float,
    top_y: float,
    snapshot: "BSFGeometryHelpSnapshot",
    markers: Dict[str, float],
) -> None:
    if snapshot.safe_z is None:
        return
    color = "#1f883d" if snapshot.safe_status == STATUS_OK else "#cf222e"
    safe_z = float(snapshot.safe_z)
    req = snapshot.required_safe_z
    margin = None
    if req is not None:
        margin = safe_z - float(req)
    lines = [f"Safe-Z  {_fmt_axis_z(safe_z)}"]
    if req is not None:
        lines.append(f"Min-Safe-Z  {_fmt_axis_z(req)}")
    if margin is not None:
        lines.append(f"Reserve  {margin:.3f} mm")
    badge_x = w * 0.58
    badge_y = top_y + 6
    text = "\n".join(lines)
    canvas.create_rectangle(
        badge_x - 8, badge_y - 4, badge_x + 168, badge_y + 14 + 14 * (len(lines) - 1),
        fill="#ffffff", outline=color, width=1, tags=("safe_annotation", "SAFE", "view_focus"),
    )
    canvas.create_text(
        badge_x, badge_y + 4, anchor="nw", text=text,
        fill=color, font=FONT_BADGE, justify=tk.LEFT, tags=("safe_annotation", "SAFE", "view_focus"),
    )
    canvas.create_line(
        badge_x + 84, badge_y + 14 + 14 * (len(lines) - 1),
        badge_x + 84, top_y + 28,
        fill=color, width=1, dash=(4, 2), arrow=tk.LAST,
        tags=("safe_annotation", "SAFE", "view_focus"),
    )
    canvas.create_text(
        badge_x + 84, top_y + 22, anchor="s", text="↑ oberhalb Prozess",
        fill=color, font=FONT_DIM, tags=("safe_annotation", "view_focus"),
    )
    markers["SAFE"] = badge_y
    markers["SAFE_z"] = safe_z
    if req is not None:
        markers["MIN_z"] = float(req)
        markers["MIN"] = badge_y + 8


def draw_bsf_geometry(
    canvas: tk.Canvas,
    snapshot: "BSFGeometryHelpSnapshot",
    *,
    tool_z: Optional[float] = None,
    blade_state: str = BLADE_CLOSED,
    show_tool: bool = True,
    title: Optional[str] = None,
    view_mode: str = DEFAULT_VIEW,
) -> Dict[str, float]:
    """Zeichnet vertikale Z-Geometrie. Marker-Werte sind Canvas-Y (+Z kleiner)."""
    canvas.delete("all")
    w = max(420, int(canvas.winfo_width() or 720))
    h = max(420, int(canvas.winfo_height() or 560))
    top, bottom = 72.0, h - 64.0
    viewport = build_geometry_viewport(snapshot, view_mode=view_mode)
    scale = ZScale(viewport.z_min, viewport.z_max, top, bottom)
    markers: Dict[str, float] = {
        "axis": 1.0,
        "PLUS_Z_UP": 1.0,
        "VIEW_MODE": 1.0 if view_mode == VIEW_PROCESS_FOCUS else 2.0,
    }
    view_tag = "view_focus" if view_mode == VIEW_PROCESS_FOCUS else "view_full"
    canvas.create_rectangle(0, 0, w, h, outline="", fill="#eef2f6", tags=(view_tag,))

    mode_label = "Prozessfokus" if view_mode == VIEW_PROCESS_FOCUS else "Gesamt-Z"
    header = title or f"Vertikale Z-Darstellung  ·  {mode_label}  ·  Werkzeug oben  ·  −Z Einfahren  ·  +Z Rueckwaertssenken"
    canvas.create_text(16, 14, anchor="w", text=header, font=FONT_TITLE, fill="#1f2328", tags=("title", view_tag))
    canvas.create_text(
        16, 34, anchor="w",
        text="+Z zur Spindel (oben)     −Z ins Werkstueck (unten)",
        font=FONT_LEGEND, fill="#57606a", tags=("axis_legend", view_tag),
    )

    ax = 36.0
    canvas.create_line(ax, bottom, ax, top, fill="#1f2328", width=2, arrow=tk.LAST, tags=("z_axis", "axis_plus", view_tag))
    canvas.create_text(ax + 10, top + 4, anchor="w", text="+Z", font=FONT_LABEL_B, tags=("axis_plus", view_tag))
    canvas.create_text(ax + 10, bottom - 4, anchor="w", text="−Z", font=FONT_LABEL_B, tags=("axis_minus", view_tag))

    if snapshot.a_z is None or snapshot.exit_edge_z is None or snapshot.entry_edge_z is None:
        canvas.create_rectangle(
            w * 0.28, h * 0.30, w * 0.58, h * 0.70,
            fill="#d0d7de", outline="#57606a", tags=("flange", view_tag),
        )
        canvas.create_text(
            w * 0.43, h / 2,
            text="Geometrie unvollstaendig\n" + "\n".join(snapshot.notes or ["Felder fehlen"]),
            fill="#cf222e", font=("Segoe UI", 12, "bold"), justify=tk.CENTER,
        )
        return markers

    entry = float(snapshot.entry_edge_z)
    exit_z = float(snapshot.exit_edge_z)
    target = float(snapshot.target_surface_z) if snapshot.target_surface_z is not None else exit_z
    y_entry = scale.map_z(entry)
    y_exit = scale.map_z(exit_z)
    y_target = scale.map_z(target)

    cx = w * 0.36
    body_half = min(120.0, w * 0.17)
    hole_half = 26.0
    x_l = cx - body_half
    x_r = cx + body_half
    y_body_top = min(y_entry, y_exit)
    y_body_bot = max(y_entry, y_exit)

    canvas.create_rectangle(
        x_l, y_body_top, cx - hole_half, y_body_bot,
        fill="#c9d1d9", outline="#57606a", width=2, tags=("flange", "workpiece", view_tag),
    )
    canvas.create_rectangle(
        cx + hole_half, y_body_top, x_r, y_body_bot,
        fill="#c9d1d9", outline="#57606a", width=2, tags=("flange", "workpiece", view_tag),
    )
    canvas.create_rectangle(
        cx - hole_half, y_body_top, cx + hole_half, y_body_bot,
        fill="#f6f8fa", outline="#8b949e", tags=("hole", view_tag),
    )
    flare = 18.0
    canvas.create_polygon(
        cx - hole_half, y_target,
        cx - hole_half - flare, y_exit,
        cx + hole_half + flare, y_exit,
        cx + hole_half, y_target,
        fill="#b6e3b6", outline="#1f883d", tags=("sink", view_tag),
    )

    y0 = scale.map_z(0.0)
    markers["Z0"] = y0
    if _z_in_viewport(0.0, scale):
        _hline(canvas, y0, 56, w - 32, color="#1f2328", width=2, dash=(6, 3), tags=("z0_line", view_tag))
        canvas.create_text(
            60, y0 - 10, anchor="w", text="Z0 = 0,000",
            fill="#1f2328", font=FONT_LABEL_B, tags=("z0_line", view_tag),
        )
    elif y0 > bottom:
        _hline(canvas, bottom - 2, 56, x_l - 12, color="#1f2328", width=2, tags=("z0_line", view_tag))
        canvas.create_text(
            60, bottom - 14, anchor="w", text="Z0 = 0,000  ↓ unterhalb",
            fill="#57606a", font=FONT_DIM, tags=("z0_line", view_tag),
        )
    else:
        _hline(canvas, top + 2, 56, x_l - 12, color="#1f2328", width=2, tags=("z0_line", view_tag))
        canvas.create_text(
            60, top + 8, anchor="w", text="Z0 = 0,000  ↑ oberhalb",
            fill="#57606a", font=FONT_DIM, tags=("z0_line", view_tag),
        )

    levels_left: List[Tuple[float, str, str, str]] = []
    if snapshot.raw_surface_z is not None:
        levels_left.append((float(snapshot.raw_surface_z), "Rohflaeche", "#bf8700", "raw"))
    levels_left.append((entry, "Eintrittskante", "#0969da", "entry"))
    levels_left.append((exit_z, "Austrittskante", "#8250df", "exit"))
    levels_left.append((target, "Ziel-Senkflaeche", "#1f883d", "target"))

    x_left_lab = 58.0
    left_items = [(z, label, color, tag) for z, label, color, tag in levels_left if _z_in_viewport(z, scale)]
    left_ys = _spread_ys([scale.map_z(z) for z, *_ in left_items], min_gap=22)
    for (z, label, color, tag), ly in zip(left_items, left_ys):
        y = scale.map_z(z)
        _hline(canvas, y, x_l - 10, x_r + 10, color=color, dash=(3, 2), tags=(tag, "level", view_tag))
        canvas.create_text(
            x_left_lab, ly, anchor="w",
            text=f"{label}  {_fmt_axis_z(z)}",
            fill=color, font=FONT_LABEL, tags=(tag, view_tag),
        )
        if abs(ly - y) > 2:
            canvas.create_line(x_l - 10, y, x_left_lab + 2, ly, fill=color, width=1, tags=(tag, "leader", view_tag))
        markers[tag.upper()] = y

    pos_defs = [
        ("A", snapshot.a_z, "Anfahrt", "#1f883d"),
        ("X", snapshot.x_z, "Ausklappen", "#0969da"),
        ("B", snapshot.b_z, "1. Schnitt", "#8250df"),
        ("C", snapshot.c_z, "Volleingriff", "#bf3989"),
        ("D", snapshot.d_z, "Vermessflaeche", "#cf222e"),
    ]
    right_src = [(float(z), letter, meaning, color) for letter, z, meaning, color in pos_defs if z is not None]
    right_src = [(z, letter, meaning, color) for z, letter, meaning, color in right_src if _z_in_viewport(z, scale)]

    if view_mode == VIEW_FULL_Z:
        if snapshot.required_safe_z is not None:
            right_src.append((float(snapshot.required_safe_z), "MIN", "Min-Safe-Z", "#bf8700"))
        if snapshot.safe_z is not None:
            sc = "#1f883d" if snapshot.safe_status == STATUS_OK else "#cf222e"
            right_src.append((float(snapshot.safe_z), "SAFE", "Safe-Z", sc))
    elif viewport.include_safe_in_scale and not viewport.safe_annotation_only:
        if snapshot.required_safe_z is not None and _z_in_viewport(float(snapshot.required_safe_z), scale):
            right_src.append((float(snapshot.required_safe_z), "MIN", "Min-Safe-Z", "#bf8700"))
        if snapshot.safe_z is not None and _z_in_viewport(float(snapshot.safe_z), scale):
            sc = "#1f883d" if snapshot.safe_status == STATUS_OK else "#cf222e"
            right_src.append((float(snapshot.safe_z), "SAFE", "Safe-Z", sc))

    right_ys = _spread_ys([scale.map_z(z) for z, *_ in right_src], min_gap=20)
    x_right_lab = min(w - 24, x_r + 28)
    for (z, letter, meaning, color), ly in zip(right_src, right_ys):
        y = scale.map_z(z)
        width = 2 if letter in {"A", "X", "D", "SAFE"} else 1
        dash = (5, 3) if letter in {"MIN", "SAFE"} else None
        _hline(canvas, y, x_l - 6, x_r + 14, color=color, width=width, dash=dash, tags=(letter, "level", view_tag))
        canvas.create_text(
            x_right_lab, ly, anchor="w",
            text=f"{letter}  {_fmt_axis_z(z)}",
            fill=color, font=FONT_LABEL_B, tags=(letter, view_tag),
        )
        canvas.create_text(
            x_right_lab, ly + 12, anchor="w",
            text=meaning, fill=color, font=FONT_DIM, tags=(letter, "level_caption", view_tag),
        )
        if abs(ly - y) > 2:
            canvas.create_line(x_r + 14, y, x_right_lab - 2, ly, fill=color, width=1, tags=(letter, "leader", view_tag))
        markers[letter] = y
        markers[f"{letter}_z"] = z

    if view_mode == VIEW_PROCESS_FOCUS and viewport.safe_annotation_only:
        _draw_safe_annotation(canvas, w=w, top_y=top, snapshot=snapshot, markers=markers)
    elif snapshot.safe_z is not None and "SAFE" not in markers:
        markers["SAFE_z"] = float(snapshot.safe_z)
        if snapshot.required_safe_z is not None:
            markers["MIN_z"] = float(snapshot.required_safe_z)

    mid = (y_entry + y_exit) / 2.0
    canvas.create_line(
        x_l - 28, y_entry + 10, x_l - 28, y_exit - 10,
        fill="#57606a", arrow=tk.LAST, width=2, tags=("dir_enter", "dir_enter_line", view_tag),
    )
    canvas.create_text(
        x_l - 32, mid, anchor="e", text="Einfahren\n−Z",
        fill="#57606a", font=FONT_DIM, justify=tk.RIGHT, tags=("dir_enter", view_tag),
    )
    canvas.create_line(
        x_r + 10, y_exit - 8, x_r + 10, y_target,
        fill="#1f883d", arrow=tk.LAST, width=2, tags=("dir_sink", "dir_sink_line", view_tag),
    )
    canvas.create_text(
        x_r + 14, (y_exit + y_target) / 2 - 12, anchor="w", text="Rueckwaertssenken +Z",
        fill="#1f883d", font=FONT_DIM, tags=("dir_sink", view_tag),
    )

    if snapshot.safe_z is not None and view_mode == VIEW_FULL_Z:
        color = "#1f883d" if snapshot.safe_status == STATUS_OK else "#cf222e"
        if snapshot.safe_status == STATUS_TOO_LOW and snapshot.a_z is not None:
            msg = f"Safe-Z {_fmt_axis_z(snapshot.safe_z)} liegt UNTER A {_fmt_axis_z(snapshot.a_z)}"
        elif snapshot.safe_status == STATUS_OK:
            margin = None
            if snapshot.required_safe_z is not None:
                margin = float(snapshot.safe_z) - float(snapshot.required_safe_z)
            extra = f"  (Reserve {margin:.3f} mm)" if margin is not None else ""
            msg = f"Safe-Z {_fmt_axis_z(snapshot.safe_z)} oberhalb Prozess{extra}"
        else:
            msg = f"Safe-Z {_fmt_axis_z(snapshot.safe_z)}"
        canvas.create_text(w / 2, h - 42, text=msg, fill=color, font=FONT_LABEL_B, tags=("safe_msg", view_tag))

    canvas.create_text(
        16, h - 18, anchor="w",
        text="Legende: A/X/B/C/D farbig  ·  Hs/AL am Werkzeug  ·  Safe-Z kompakt im Prozessfokus",
        fill="#57606a", font=FONT_LEGEND, tags=("legend", view_tag),
    )

    if show_tool:
        tz = tool_z if tool_z is not None else snapshot.a_z
        if tz is not None and _z_in_viewport(float(tz), scale):
            y_face = scale.map_z(float(tz))
            hs = 8.55
            al = 20.25
            if snapshot.tool_profile is not None:
                hs = float(snapshot.tool_profile.measurement_face_to_cutting_edge_mm)
                if snapshot.tool_profile.deployment_length_al_mm:
                    al = float(snapshot.tool_profile.deployment_length_al_mm)
            hs_px = abs(scale.map_z(float(tz)) - scale.map_z(float(tz) - hs))
            al_px = abs(scale.map_z(float(tz)) - scale.map_z(float(tz) - al))
            draw_bsf_tool(
                canvas, cx=cx, y_face=y_face, blade_state=blade_state,
                hs_px=hs_px, al_px=al_px, x_dim=x_r + 6,
            )
            markers["TOOL"] = y_face

    markers["PROCESS_SPAN_PX"] = abs(scale.map_z(float(snapshot.a_z or 0)) - scale.map_z(float(snapshot.x_z or 0)))
    markers["VIEWPORT_Z_MIN"] = viewport.z_min
    markers["VIEWPORT_Z_MAX"] = viewport.z_max
    return markers


__all__ = [
    "AXIS_ORIENTATION",
    "BLADE_CLOSED",
    "BLADE_DEPLOYED",
    "PLUS_Z_DIRECTION",
    "VIEW_FULL_Z",
    "VIEW_PROCESS_FOCUS",
    "ZScale",
    "build_z_scale",
    "collect_z_values",
    "draw_bsf_geometry",
    "draw_bsf_tool",
]
