"""Weltkoordinaten ↔ Canvas-Transformation fuer BGF-Positionsvorschau.

Maschinen: +X rechts, +Y oben.
Tkinter Canvas: +Y nach unten → invertieren.

Auto-Fit darf erst mit realer Canvasgroesse berechnet werden.
Ein Fit auf 1×1 (oder dem alten Fallback 100×100) erzeugt einen Mini-Massstab;
wenn das Fenster danach waechst und der Massstab beibehalten wird, liegen
alle Punkte als Knäuel um den Ursprung.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


Point = Tuple[float, float]

# Unterhalb dieser Pixelgroesse ist das Canvas noch nicht layoutet.
MIN_FIT_CANVAS_PX = 50.0


@dataclass
class ViewTransform:
    """Affine Abbildung world → canvas mit Zoom/Pan.

    screen_x = offset_x + world_x * scale
    screen_y = offset_y - world_y * scale
    Zoom 1.00x bedeutet: scale == Auto-Fit-Basisscale (nicht 1 px/mm).
    """

    scale: float
    offset_x: float  # canvas origin of world 0
    offset_y: float
    canvas_w: float
    canvas_h: float

    def world_to_canvas(self, x: float, y: float) -> Point:
        cx = self.offset_x + x * self.scale
        cy = self.offset_y - y * self.scale  # Y invertiert
        return cx, cy

    def canvas_to_world(self, cx: float, cy: float) -> Point:
        x = (cx - self.offset_x) / self.scale
        y = (self.offset_y - cy) / self.scale
        return x, y

    def zoom_at(self, factor: float, pivot_cx: float, pivot_cy: float) -> "ViewTransform":
        wx, wy = self.canvas_to_world(pivot_cx, pivot_cy)
        new_scale = self.scale * factor
        new_scale = max(1e-6, min(new_scale, 1e6))
        new_ox = pivot_cx - wx * new_scale
        new_oy = pivot_cy + wy * new_scale
        return ViewTransform(new_scale, new_ox, new_oy, self.canvas_w, self.canvas_h)

    def pan(self, dx_canvas: float, dy_canvas: float) -> "ViewTransform":
        return ViewTransform(
            self.scale,
            self.offset_x + dx_canvas,
            self.offset_y + dy_canvas,
            self.canvas_w,
            self.canvas_h,
        )

    def with_canvas_size(self, canvas_w: float, canvas_h: float) -> "ViewTransform":
        """Gleiche Weltansicht, neue Canvasgroesse (Mitte halten). Kein Re-Fit."""
        dx = (canvas_w - self.canvas_w) / 2.0
        dy = (canvas_h - self.canvas_h) / 2.0
        return ViewTransform(
            self.scale,
            self.offset_x + dx,
            self.offset_y + dy,
            canvas_w,
            canvas_h,
        )


def canvas_is_ready_for_fit(canvas_w: float, canvas_h: float) -> bool:
    return canvas_w > MIN_FIT_CANVAS_PX and canvas_h > MIN_FIT_CANVAS_PX


def compute_bounds(points: Sequence[Point]) -> Tuple[float, float, float, float]:
    if not points:
        return -1.0, 1.0, -1.0, 1.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), max(xs), min(ys), max(ys)


def fit_transform(
    points: Sequence[Point],
    canvas_w: float,
    canvas_h: float,
    *,
    padding_ratio: float = 0.10,
    min_padding_px: float = 40.0,
) -> ViewTransform:
    """Passt nur XY-Positionen ins Canvas ein. Ursprung nicht in die Bounding-Box zwingen."""
    if not canvas_is_ready_for_fit(canvas_w, canvas_h):
        # Kein Fake-Fit auf 1×1 / 100×100 – Aufrufer muss warten.
        return ViewTransform(1.0, canvas_w / 2.0, canvas_h / 2.0, canvas_w, canvas_h)

    if not points:
        return ViewTransform(1.0, canvas_w / 2.0, canvas_h / 2.0, canvas_w, canvas_h)

    min_x, max_x, min_y, max_y = compute_bounds(points)
    span_x = max_x - min_x
    span_y = max_y - min_y

    if span_x <= 1e-12:
        span_x = max(abs(min_x) * 0.2, 10.0)
        mid = (min_x + max_x) / 2.0
        min_x = mid - span_x / 2.0
        max_x = mid + span_x / 2.0
    if span_y <= 1e-12:
        span_y = max(abs(min_y) * 0.2, 10.0)
        mid = (min_y + max_y) / 2.0
        min_y = mid - span_y / 2.0
        max_y = mid + span_y / 2.0

    pad_x = max(span_x * padding_ratio, span_x * 0.01)
    pad_y = max(span_y * padding_ratio, span_y * 0.01)
    min_x -= pad_x
    max_x += pad_x
    min_y -= pad_y
    max_y += pad_y
    span_x = max_x - min_x
    span_y = max_y - min_y

    usable_w = max(canvas_w - 2 * min_padding_px, 1.0)
    usable_h = max(canvas_h - 2 * min_padding_px, 1.0)
    scale = min(usable_w / span_x, usable_h / span_y)

    mid_x = (min_x + max_x) / 2.0
    mid_y = (min_y + max_y) / 2.0
    offset_x = canvas_w / 2.0 - mid_x * scale
    offset_y = canvas_h / 2.0 + mid_y * scale
    return ViewTransform(scale, offset_x, offset_y, canvas_w, canvas_h)


def resolve_view_after_resize(
    points: Sequence[Point],
    canvas_w: float,
    canvas_h: float,
    current: Optional[ViewTransform],
    *,
    user_view_changed: bool,
) -> Optional[ViewTransform]:
    """Nach Canvas-Resize: Fit wenn noch keine User-Ansicht, sonst Massstab halten.

    Returns None wenn das Canvas noch nicht layoutet ist (Fit aufschieben).
    """
    if not canvas_is_ready_for_fit(canvas_w, canvas_h):
        return None
    if current is None or not user_view_changed:
        return fit_transform(points, canvas_w, canvas_h)
    return current.with_canvas_size(canvas_w, canvas_h)
