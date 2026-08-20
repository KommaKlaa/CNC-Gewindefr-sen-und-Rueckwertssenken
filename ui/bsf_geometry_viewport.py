"""Viewport-Berechnung fuer die BSF-Hilfsgrafik (UI only, keine NC-Logik)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from help_views.bsf_geometry_model import BSFGeometryHelpSnapshot

VIEW_PROCESS_FOCUS = "PROCESS_FOCUS"
VIEW_FULL_Z = "FULL_Z"
DEFAULT_VIEW = VIEW_PROCESS_FOCUS

# Safe-Z wird im Prozessfokus nicht in die Skala gezogen (nur Annotation).
SAFE_FOCUS_ANNOTATION_ONLY = True


@dataclass(frozen=True)
class GeometryViewport:
    z_min: float
    z_max: float
    mode: str
    include_safe_in_scale: bool
    safe_annotation_only: bool


def _finite_values(values) -> List[float]:
    out: List[float] = []
    for v in values:
        if v is None:
            continue
        out.append(float(v))
    return out


def compute_process_focus_z_range(snapshot: "BSFGeometryHelpSnapshot") -> Tuple[float, float]:
    """Fokus auf Bearbeitungsbereich ohne dominierendes Safe-Z."""
    z_min_candidates = _finite_values(
        [
            snapshot.x_z,
            snapshot.b_z,
            snapshot.c_z,
            snapshot.d_z,
            snapshot.target_surface_z,
            snapshot.exit_edge_z,
            snapshot.raw_surface_z,
            snapshot.entry_edge_z,
        ]
    )
    z_max_candidates = _finite_values(
        [
            snapshot.a_z,
            snapshot.entry_edge_z,
            snapshot.raw_surface_z,
            snapshot.target_surface_z,
            snapshot.d_z,
        ]
    )
    if not z_min_candidates or not z_max_candidates:
        return -10.0, 10.0
    z_min = min(z_min_candidates)
    z_max = max(z_max_candidates)
    span = max(z_max - z_min, 1.0)
    pad = max(4.0, span * 0.10)
    return z_min - pad, z_max + pad


def compute_full_z_range(snapshot: "BSFGeometryHelpSnapshot") -> Tuple[float, float]:
    """Gesamt-Z inkl. Safe-Z, End-Safe, Z0."""
    vals = _finite_values(
        [
            0.0,
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
        ]
    )
    if not vals:
        return -10.0, 10.0
    z_min, z_max = min(vals), max(vals)
    if abs(z_max - z_min) < 1e-9:
        z_min -= 5.0
        z_max += 5.0
    span = z_max - z_min
    pad = max(4.0, span * 0.08)
    return z_min - pad, z_max + pad


def build_geometry_viewport(
    snapshot: "BSFGeometryHelpSnapshot",
    *,
    view_mode: str = DEFAULT_VIEW,
) -> GeometryViewport:
    if view_mode == VIEW_FULL_Z:
        z_min, z_max = compute_full_z_range(snapshot)
        return GeometryViewport(
            z_min=z_min,
            z_max=z_max,
            mode=VIEW_FULL_Z,
            include_safe_in_scale=True,
            safe_annotation_only=False,
        )
    z_min, z_max = compute_process_focus_z_range(snapshot)
    span = max(z_max - z_min, 1.0)
    pad = max(3.0, span * 0.06)
    return GeometryViewport(
        z_min=z_min - pad * 0.3,
        z_max=z_max + pad * 0.5,
        mode=VIEW_PROCESS_FOCUS,
        include_safe_in_scale=False,
        safe_annotation_only=True,
    )
