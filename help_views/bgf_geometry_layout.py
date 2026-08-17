"""Fenster-Layoutzonen fuer die CERATIZIT-BGF-Hilfsgrafik (ohne Domainlogik)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def overlaps(self, other: "Rect", *, gap: float = 0.0) -> bool:
        return not (
            self.right + gap <= other.x
            or other.right + gap <= self.x
            or self.bottom + gap <= other.y
            or other.bottom + gap <= self.y
        )


@dataclass(frozen=True)
class BGFHelpWindowLayout:
    window: Rect
    header: Rect
    status: Rect
    main_cross_section: Rect
    depth_detail: Rect
    info_panel: Rect


def compute_bgf_help_layout(width: float, height: float) -> BGFHelpWindowLayout:
    """Relative Aufteilung: Hauptschnitt ~68 %, rechte Spalte ~32 %."""
    width = max(float(width), 640.0)
    height = max(float(height), 480.0)
    pad = 8.0
    gap = 8.0
    header_h = 40.0
    status_h = 32.0

    header = Rect(pad, pad, width - 2 * pad, header_h)
    status = Rect(pad, header.bottom + 4.0, width - 2 * pad, status_h)
    body_top = status.bottom + gap
    body_h = max(120.0, height - body_top - pad)
    body_w = max(200.0, width - 2 * pad)

    main_w = body_w * 0.68
    right_w = max(160.0, body_w - main_w - gap)
    main = Rect(pad, body_top, main_w, body_h)
    detail_h = body_h * 0.48
    detail = Rect(main.right + gap, body_top, right_w, detail_h)
    info_h = max(80.0, body_h - detail_h - gap)
    info = Rect(detail.x, detail.bottom + gap, right_w, info_h)

    return BGFHelpWindowLayout(
        window=Rect(0.0, 0.0, width, height),
        header=header,
        status=status,
        main_cross_section=main,
        depth_detail=detail,
        info_panel=info,
    )
