"""Erzeugt die freigegebene BSF-Geometrie-Referenzgrafik (App-Asset, kein HEULE-Original).

Einmal ausfuehren:
    python build_tools/render_bsf_geometry_reference.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "help" / "bsf_heule_geometry_reference.png"

# Referenzbeispiel (Erklaergrafik, nicht Live-GUI)
REF = {
    "z0": 0.0,
    "entry": 0.0,
    "exit": -30.0,
    "target": -22.0,
    "sink_depth": 8.0,
    "tool": "BSF-C-1000/050-10.5-23",
    "hs": 8.550,
    "al": 20.250,
    "a": 5.0,
    "x": -55.25,
    "b": -39.55,
    "c": -38.30,
    "d": -30.55,
}

COLORS = {
    "A": "#1f883d",
    "X": "#0969da",
    "B": "#8250df",
    "C": "#bf3989",
    "D": "#cf222e",
    "Z0": "#1f2328",
    "target": "#1f883d",
    "entry": "#0969da",
    "exit": "#8250df",
}


def _font(size: int, bold: bool = False):
    names = ["segoeui.ttf", "Segoe UI.ttf", "arial.ttf", "DejaVuSans.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _map_z(z: float, z_min: float, z_max: float, y_top: float, y_bot: float) -> float:
    if z_max <= z_min:
        return (y_top + y_bot) / 2
    t = (z - z_min) / (z_max - z_min)
    return y_bot - t * (y_bot - y_top)


def render_reference_image() -> Image.Image:
    w, h = 1280, 1680
    img = Image.new("RGB", (w, h), "#f6f8fa")
    draw = ImageDraw.Draw(img)
    title_f = _font(22, bold=True)
    label_f = _font(15)
    small_f = _font(13)
    dim_f = _font(12, bold=True)

    draw.text((36, 24), "BSF Senkgeometrie – Referenzdarstellung", fill="#1f2328", font=title_f)
    draw.text(
        (36, 56),
        "+Z zur Spindel (oben)    −Z ins Werkstueck (unten)    Werkzeug oben",
        fill="#57606a",
        font=small_f,
    )

    z_vals = [REF["a"], REF["x"], REF["b"], REF["c"], REF["d"], REF["entry"], REF["exit"], REF["target"], REF["z0"]]
    z_min = min(z_vals) - 8.0
    z_max = max(z_vals) + 10.0
    y_top, y_bot = 120.0, h - 220.0
    ax = 72.0

    def mz(z: float) -> float:
        return _map_z(z, z_min, z_max, y_top, y_bot)

    # Z-Achse
    draw.line((ax, y_bot, ax, y_top), fill="#1f2328", width=3)
    draw.polygon([(ax, y_top - 14), (ax - 8, y_top + 2), (ax + 8, y_top + 2)], fill="#1f2328")
    draw.text((ax + 14, y_top - 6), "+Z", fill="#1f2328", font=dim_f)
    draw.text((ax + 14, y_bot - 18), "−Z", fill="#1f2328", font=dim_f)

    cx = w * 0.46
    body_half = 130
    hole_half = 38
    x_l = cx - body_half
    x_r = cx + body_half
    y_entry = mz(REF["entry"])
    y_exit = mz(REF["exit"])
    y_target = mz(REF["target"])
    y_body_top = min(y_entry, y_exit)
    y_body_bot = max(y_entry, y_exit)

    # Werkstueck
    draw.rectangle((x_l, y_body_top, cx - hole_half, y_body_bot), fill="#c9d1d9", outline="#57606a", width=2)
    draw.rectangle((cx + hole_half, y_body_top, x_r, y_body_bot), fill="#c9d1d9", outline="#57606a", width=2)
    draw.rectangle((cx - hole_half, y_body_top, cx + hole_half, y_body_bot), fill="#ffffff", outline="#8b949e", width=1)
    flare = 22
    draw.polygon(
        [
            (cx - hole_half, y_target),
            (cx - hole_half - flare, y_exit),
            (cx + hole_half + flare, y_exit),
            (cx + hole_half, y_target),
        ],
        fill="#b6e3b6",
        outline="#1f883d",
    )

    def hline(y: float, color: str, x0: float | None = None, x1: float | None = None, width: int = 2, dash: bool = False):
        x0 = x_l - 12 if x0 is None else x0
        x1 = x_r + 12 if x1 is None else x1
        if dash:
            step = 8
            x = x0
            while x < x1:
                x2 = min(x1, x + step)
                draw.line((x, y, x2, y), fill=color, width=width)
                x += step * 2
        else:
            draw.line((x0, y, x1, y), fill=color, width=width)

    def label_left(y: float, z: float, text: str, color: str):
        draw.line((x_l - 12, y, 130, y), fill=color, width=1)
        draw.text((132, y - 10), f"{text}  {z:+.3f}", fill=color, font=label_f)

    def label_right(y: float, z: float, letter: str, meaning: str, color: str):
        lx = x_r + 36
        draw.line((x_r + 12, y, lx, y), fill=color, width=1)
        draw.text((lx + 4, y - 14), f"{letter}  {z:+.3f}", fill=color, font=label_f)
        draw.text((lx + 4, y + 2), meaning, fill=color, font=small_f)

    # Z0
    y0 = mz(REF["z0"])
    hline(y0, COLORS["Z0"], x0=100, x1=w - 80, width=2, dash=True)
    draw.text((100, y0 - 28), "Z0 = 0,000  (obere Werkstueckflaeche)", fill=COLORS["Z0"], font=label_f)

    label_left(mz(REF["entry"]), REF["entry"], "Eintrittskante", COLORS["entry"])
    label_left(mz(REF["exit"]), REF["exit"], "Austrittskante", COLORS["exit"])
    label_left(mz(REF["target"]), REF["target"], "Ziel-Senkflaeche", COLORS["target"])

    label_right(mz(REF["a"]), REF["a"], "A", "Anfahrt vor Eintritt", COLORS["A"])
    label_right(mz(REF["x"]), REF["x"], "X", "Ausklapp-/Freigabeposition", COLORS["X"])
    label_right(mz(REF["b"]), REF["b"], "B", "erste Schnittposition", COLORS["B"])
    label_right(mz(REF["c"]), REF["c"], "C", "voller Eingriff", COLORS["C"])
    label_right(mz(REF["d"]), REF["d"], "D", "Vermessflaeche", COLORS["D"])

    # Werkzeug bei A
    y_face = mz(REF["a"])
    hs_px = abs(mz(REF["a"]) - mz(REF["a"] - REF["hs"]))
    al_px = abs(mz(REF["a"]) - mz(REF["a"] - REF["al"]))
    draw.rectangle((cx - 14, y_face - 88, cx + 14, y_face), fill="#8b949e", outline="#1f2328", width=1)
    draw.rectangle((cx - 22, y_face - 102, cx + 22, y_face - 86), fill="#6e7781", outline="#1f2328", width=1)
    draw.line((cx - 28, y_face, cx + 28, y_face), fill="#cf222e", width=3)
    draw.text((cx + 32, y_face - 8), "Vermess-Stirn", fill="#cf222e", font=dim_f)
    x_dim = x_r + 8
    y_cut = y_face + hs_px
    y_al = y_face + al_px
    draw.line((x_dim, y_face, x_dim, y_cut), fill="#8250df", width=2)
    draw.text((x_dim + 6, (y_face + y_cut) / 2 - 8), "Hs", fill="#8250df", font=dim_f)
    draw.line((x_dim + 28, y_face, x_dim + 28, y_al), fill="#0969da", width=2)
    draw.text((x_dim + 34, (y_face + y_al) / 2 - 8), "AL", fill="#0969da", font=dim_f)
    draw.polygon([(cx, y_cut), (cx - 30, y_cut - 10), (cx - 30, y_cut + 10)], fill="#1f883d", outline="#1f2328")
    draw.polygon([(cx, y_cut), (cx + 30, y_cut - 10), (cx + 30, y_cut + 10)], fill="#1f883d", outline="#1f2328")

    # Richtungspfeile
    mid = (y_entry + y_exit) / 2
    draw.line((x_l - 34, y_entry + 12, x_l - 34, y_exit - 12), fill="#57606a", width=2)
    draw.polygon([(x_l - 34, y_exit - 12), (x_l - 42, y_exit + 2), (x_l - 26, y_exit + 2)], fill="#57606a")
    draw.text((x_l - 78, mid - 16), "Einfahren\n−Z", fill="#57606a", font=dim_f)
    draw.line((x_r + 16, y_exit - 10, x_r + 16, y_target), fill="#1f883d", width=2)
    draw.polygon([(x_r + 16, y_target), (x_r + 8, y_target + 14), (x_r + 24, y_target + 14)], fill="#1f883d")
    draw.text((x_r + 24, (y_exit + y_target) / 2 - 10), "Rueckwaertssenken +Z", fill="#1f883d", font=dim_f)

    # Infobox rechts oben
    box_x, box_y = w - 340, 110
    lines = [
        f"Werkzeug: {REF['tool']}",
        f"Hs = {REF['hs']:.3f} mm",
        f"AL = {REF['al']:.3f} mm",
        f"Senktiefe = {REF['sink_depth']:.3f} mm",
    ]
    draw.rectangle((box_x - 8, box_y - 8, w - 28, box_y + 8 + 22 * len(lines)), outline="#57606a", width=1, fill="#ffffff")
    for i, line in enumerate(lines):
        draw.text((box_x, box_y + i * 22), line, fill="#1f2328", font=small_f)

    # Fussnoten im Bild (kurz; ausfuehrlicher Text kommt in der GUI)
    draw.text(
        (36, h - 180),
        "Beispielwerte zur Prozesserklaerung (HEULE-artiger Aufbau).",
        fill="#57606a",
        font=small_f,
    )
    draw.text(
        (36, h - 150),
        "Grafik nach HEULE-Prozessreferenz, fuer die Anwendung schematisch aufbereitet.",
        fill="#57606a",
        font=small_f,
    )
    return img


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image = render_reference_image()
    image.save(OUT, format="PNG", optimize=True)
    print(f"Written {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
