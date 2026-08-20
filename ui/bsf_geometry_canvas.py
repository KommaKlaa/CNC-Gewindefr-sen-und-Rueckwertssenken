"""BSF-Geometrie-Canvas: vertikale Z-Achse (+Z oben, -Z unten)."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

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
    """Schiebt Labels auseinander, wenn Niveaus zu nah beieinander liegen."""
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
    # Schaft nach oben (+Z)
    canvas.create_rectangle(
        cx - 10, y_face - 72, cx + 10, y_face,
        fill="#8b949e", outline="#1f2328", tags=("tool", "shaft"),
    )
    canvas.create_rectangle(
        cx - 16, y_face - 84, cx + 16, y_face - 70,
        fill="#6e7781", outline="#1f2328", tags=("tool",),
    )
    # Vermess-Stirn
    canvas.create_line(
        cx - 20, y_face, cx + 20, y_face,
        fill="#cf222e", width=3, tags=("tool", "meas_face"),
    )
    canvas.create_text(
        cx + 24, y_face, anchor="w", text="Vermess-Stirn",
        fill="#cf222e", font=FONT_DIM, tags=("tool",),
    )
    # Hs vertikal
    canvas.create_line(
        x_dim, y_face, x_dim, y_cut,
        fill="#8250df", width=2, arrow=tk.BOTH, tags=("tool", "dim_hs"),
    )
    canvas.create_text(
        x_dim + 6, (y_face + y_cut) / 2,
        anchor="w", text="Hs", fill="#8250df", font=FONT_DIM, tags=("dim_hs",),
    )
    # AL vertikal
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


def draw_bsf_geometry(
    canvas: tk.Canvas,
    snapshot: BSFGeometryHelpSnapshot,
    *,
    tool_z: Optional[float] = None,
    blade_state: str = BLADE_CLOSED,
    show_tool: bool = True,
    title: Optional[str] = None,
) -> Dict[str, float]:
    """Zeichnet vertikale Z-Geometrie. Marker-Werte sind Canvas-Y (+Z kleiner)."""
    canvas.delete("all")
    w = max(420, int(canvas.winfo_width() or 720))
    h = max(420, int(canvas.winfo_height() or 560))
    top, bottom = 56.0, h - 78.0
    values = collect_z_values(snapshot)
    scale = build_z_scale(values, top=top, bottom=bottom)
    markers: Dict[str, float] = {
        "axis": 1.0,  # VERTICAL flag for numeric tests via PLUS_Z
    }
    markers["PLUS_Z_UP"] = 1.0

    header = title or "Vertikale Z-Darstellung  ·  Werkzeug oben  ·  Einfahren −Z  ·  Rueckwaertssenken +Z"
    canvas.create_text(16, 14, anchor="w", text=header, font=FONT_TITLE, fill="#1f2328", tags=("title",))
    canvas.create_text(
        16, 34, anchor="w",
        text="+Z zur Spindel (oben)     −Z ins Werkstueck (unten)",
        font=FONT_LEGEND, fill="#57606a", tags=("axis_legend",),
    )

    # Achspfeil links
    ax = 28.0
    canvas.create_line(ax, bottom, ax, top, fill="#1f2328", width=2, arrow=tk.LAST, tags=("z_axis", "axis_plus"))
    canvas.create_text(ax + 10, top + 4, anchor="w", text="+Z", font=FONT_LABEL_B, tags=("axis_plus",))
    canvas.create_text(ax + 10, bottom - 4, anchor="w", text="−Z", font=FONT_LABEL_B, tags=("axis_minus",))

    if snapshot.a_z is None or snapshot.exit_edge_z is None or snapshot.entry_edge_z is None:
        canvas.create_rectangle(
            w * 0.32, h * 0.32, w * 0.62, h * 0.68,
            fill="#d0d7de", outline="#57606a", tags=("flange",),
        )
        canvas.create_text(
            w / 2, h / 2,
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
    y0 = scale.map_z(0.0)

    cx = w * 0.40
    body_half = min(88.0, w * 0.14)
    hole_half = 22.0
    x_l = cx - body_half
    x_r = cx + body_half
    y_body_top = min(y_entry, y_exit)
    y_body_bot = max(y_entry, y_exit)

    # Werkstueck: zwei Waende, Bohrung frei
    canvas.create_rectangle(
        x_l, y_body_top, cx - hole_half, y_body_bot,
        fill="#c9d1d9", outline="#57606a", width=2, tags=("flange", "workpiece"),
    )
    canvas.create_rectangle(
        cx + hole_half, y_body_top, x_r, y_body_bot,
        fill="#c9d1d9", outline="#57606a", width=2, tags=("flange", "workpiece"),
    )
    canvas.create_rectangle(
        cx - hole_half, y_body_top, cx + hole_half, y_body_bot,
        fill="#f6f8fa", outline="#8b949e", tags=("hole",),
    )
    # Rueckwaertssenkung an der Austrittsseite Richtung +Z
    flare = 16.0
    canvas.create_polygon(
        cx - hole_half, y_target,
        cx - hole_half - flare, y_exit,
        cx + hole_half + flare, y_exit,
        cx + hole_half, y_target,
        fill="#b6e3b6", outline="#1f883d", tags=("sink",),
    )

    # Z0 horizontale Bezugslinie
    _hline(
        canvas, y0, 48, w - 24,
        color="#1f2328", width=2, dash=(6, 3), tags=("z0_line",),
    )
    canvas.create_text(
        w - 28, y0 - 12, anchor="e", text="Z0 = 0,000",
        fill="#1f2328", font=FONT_LABEL_B, tags=("z0_line",),
    )

    levels_left: List[Tuple[float, str, str, str]] = []
    if snapshot.raw_surface_z is not None:
        levels_left.append((float(snapshot.raw_surface_z), "Rohflaeche / Ist-Z", "#bf8700", "raw"))
    levels_left.append((entry, "Eintrittskante", "#0969da", "entry"))
    levels_left.append((exit_z, "Austrittskante / Senkseite", "#8250df", "exit"))
    levels_left.append((target, "Ziel-Senkflaeche (Schneide)", "#1f883d", "target"))

    x_left_lab = 52.0
    left_ys = _spread_ys([scale.map_z(z) for z, *_ in levels_left], min_gap=20)
    for (z, label, color, tag), ly in zip(levels_left, left_ys):
        y = scale.map_z(z)
        _hline(canvas, y, x_l - 8, x_r + 8, color=color, dash=(3, 2), tags=(tag, "level"))
        canvas.create_text(
            x_left_lab, ly, anchor="w",
            text=f"{label}  {_fmt_axis_z(z)}",
            fill=color, font=FONT_LABEL, tags=(tag,),
        )
        if abs(ly - y) > 2:
            canvas.create_line(x_l - 8, y, x_left_lab + 4, ly, fill=color, width=1)
        markers[tag.upper()] = y

    pos_defs = [
        ("A", snapshot.a_z, "Anfahrt vor Eintritt", "#1f883d"),
        ("X", snapshot.x_z, "Ausklapp-/Freigabeposition", "#0969da"),
        ("B", snapshot.b_z, "erste Schnittposition", "#8250df"),
        ("C", snapshot.c_z, "voller Eingriff / Ueberdeckung", "#bf3989"),
        ("D", snapshot.d_z, "Zielposition Vermessflaeche", "#cf222e"),
    ]
    right_src = [(float(z), letter, meaning, color) for letter, z, meaning, color in pos_defs if z is not None]
    if snapshot.required_safe_z is not None:
        right_src.append((float(snapshot.required_safe_z), "MIN", "Min-Safe-Z", "#bf8700"))
    if snapshot.safe_z is not None:
        right_src.append((float(snapshot.safe_z), "SAFE", "Sicherheits-Z", "#1f883d" if snapshot.safe_status == STATUS_OK else "#cf222e"))
    if snapshot.d_z is not None and snapshot.target_surface_z is not None:
        right_src.append((float(snapshot.target_surface_z), "EDGE", "reale Schneide = D + Hs", "#1a7f37"))

    right_ys = _spread_ys([scale.map_z(z) for z, *_ in right_src], min_gap=19)
    x_right_lab = x_r + 18
    for (z, letter, meaning, color), ly in zip(right_src, right_ys):
        y = scale.map_z(z)
        width = 2 if letter in {"A", "X", "D", "SAFE"} else 1
        dash = (5, 3) if letter in {"MIN", "SAFE"} else None
        _hline(canvas, y, x_l - 4, x_r + 12, color=color, width=width, dash=dash, tags=(letter, "level"))
        canvas.create_text(
            x_right_lab, ly, anchor="w",
            text=f"{letter}  {_fmt_axis_z(z)}  {meaning}",
            fill=color, font=FONT_LABEL_B, tags=(letter,),
        )
        if abs(ly - y) > 2:
            canvas.create_line(x_r + 12, y, x_right_lab, ly, fill=color, width=1)
        markers[letter] = y
        markers[f"{letter}_z"] = z

    # Prozessrichtung
    mid = (y_entry + y_exit) / 2.0
    canvas.create_line(
        cx - body_half - 22, y_entry + 8, cx - body_half - 22, y_exit - 8,
        fill="#57606a", arrow=tk.LAST, width=2, tags=("dir_enter", "dir_enter_line"),
    )
    canvas.create_text(
        cx - body_half - 26, mid, anchor="e", text="Einfahren\n−Z",
        fill="#57606a", font=FONT_DIM, justify=tk.RIGHT, tags=("dir_enter",),
    )
    canvas.create_line(
        cx + body_half + 8, y_exit - 6, cx + body_half + 8, y_target,
        fill="#1f883d", arrow=tk.LAST, width=2, tags=("dir_sink", "dir_sink_line"),
    )
    canvas.create_text(
        cx + 8, (y_exit + y_target) / 2 - 14, text="Rueckwaertssenken +Z",
        fill="#1f883d", font=FONT_DIM, tags=("dir_sink",),
    )

    # Safe-Z Hinweis
    if snapshot.safe_z is not None:
        color = "#1f883d" if snapshot.safe_status == STATUS_OK else "#cf222e"
        if snapshot.safe_status == STATUS_TOO_LOW and snapshot.a_z is not None:
            msg = f"⚠ Safe-Z {_fmt_axis_z(snapshot.safe_z)} liegt UNTER A {_fmt_axis_z(snapshot.a_z)}"
        elif snapshot.safe_status == STATUS_OK:
            margin = None
            if snapshot.required_safe_z is not None:
                margin = float(snapshot.safe_z) - float(snapshot.required_safe_z)
            extra = f"  (Reserve {margin:.3f} mm)" if margin is not None else ""
            msg = f"✓ Safe-Z {_fmt_axis_z(snapshot.safe_z)} oberhalb aller Prozesspositionen{extra}"
        else:
            msg = f"Safe-Z {_fmt_axis_z(snapshot.safe_z)}"
        canvas.create_text(w / 2, h - 48, text=msg, fill=color, font=FONT_LABEL_B, tags=("safe_msg",))

    canvas.create_text(
        16, h - 22, anchor="w",
        text="Legende: +Z zur Spindel  ·  −Z ins Werkstueck  ·  Werkzeug faehrt von oben ein  ·  Rueckwaertssenken in +Z",
        fill="#57606a", font=FONT_LEGEND, tags=("legend",),
    )

    if show_tool:
        tz = tool_z if tool_z is not None else snapshot.a_z
        if tz is not None:
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
                hs_px=hs_px, al_px=al_px, x_dim=cx + body_half + 4,
            )
            markers["TOOL"] = y_face

    markers["Z0"] = y0
    markers["ENTRY"] = y_entry
    markers["EXIT"] = y_exit
    markers["TARGET"] = y_target
    return markers
