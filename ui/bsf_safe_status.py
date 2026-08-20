"""Live-Statusmodell fuer BSF Verfahr-/Sicherheitspruefung (kein Popup)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from bsf_workpiece_geometry import BSFHeuleProcessPositions, required_bsf_safe_z

STATUS_OK = "OK"
STATUS_TOO_LOW = "TOO_LOW"
STATUS_INCOMPLETE = "INCOMPLETE"

DEFAULT_SAFE_Z_RESERVE_MM = 5.0


@dataclass(frozen=True)
class BSFSafeZStatus:
    status: str
    required_safe_z: Optional[float]
    safe_z: Optional[float]
    end_safe_z: Optional[float]
    deficit_mm: Optional[float]
    headline: str
    detail: str

    @property
    def is_ok(self) -> bool:
        return self.status == STATUS_OK


def fmt_axis_z(value: Optional[float], *, decimals: int = 3) -> str:
    if value is None:
        return "—"
    return f"Z{value:+.{decimals}f}"


def evaluate_bsf_safe_z_status(
    *,
    heule_pos: Optional[BSFHeuleProcessPositions],
    safe_z: Optional[float],
    end_safe_z: Optional[float],
) -> BSFSafeZStatus:
    if heule_pos is None:
        return BSFSafeZStatus(
            status=STATUS_INCOMPLETE,
            required_safe_z=None,
            safe_z=safe_z,
            end_safe_z=end_safe_z,
            deficit_mm=None,
            headline="— Geometrie noch unvollstaendig",
            detail="A/X/B/C/D koennen noch nicht berechnet werden.",
        )
    required = required_bsf_safe_z(heule_pos)
    if (
        safe_z is None
        or end_safe_z is None
        or not math.isfinite(safe_z)
        or not math.isfinite(end_safe_z)
    ):
        return BSFSafeZStatus(
            status=STATUS_INCOMPLETE,
            required_safe_z=required,
            safe_z=safe_z,
            end_safe_z=end_safe_z,
            deficit_mm=None,
            headline="— Geometrie noch unvollstaendig",
            detail="Sicherheits-Z bzw. End-Sicherheits-Z fehlt oder ist ungueltig.",
        )
    lowest = min(safe_z, end_safe_z)
    if lowest < required:
        deficit = required - lowest
        return BSFSafeZStatus(
            status=STATUS_TOO_LOW,
            required_safe_z=required,
            safe_z=safe_z,
            end_safe_z=end_safe_z,
            deficit_mm=deficit,
            headline="⚠ Sicherheits-Z zu niedrig",
            detail=(
                f"Sicherheits-Z liegt {deficit:.3f} mm unter dem erforderlichen Mindestwert."
            ),
        )
    return BSFSafeZStatus(
        status=STATUS_OK,
        required_safe_z=required,
        safe_z=safe_z,
        end_safe_z=end_safe_z,
        deficit_mm=0.0,
        headline="✓ Sicherheits-Z ausreichend",
        detail="Sicherheits-Z und End-Sicherheits-Z liegen oberhalb aller Prozesspositionen.",
    )


def apply_minimum_plus_reserve(
    *,
    required_safe_z: float,
    reserve_mm: float,
    current_end_safe_z: Optional[float],
) -> tuple[float, float]:
    """Berechnet neue safe_z / end_safe_z fuer den Komfortbutton."""
    if not math.isfinite(required_safe_z):
        raise ValueError("required_safe_z muss endlich sein.")
    if not math.isfinite(reserve_mm) or reserve_mm < 0:
        raise ValueError("Sicherheitsreserve muss >= 0 sein.")
    new_safe = required_safe_z + reserve_mm
    end_base = current_end_safe_z if current_end_safe_z is not None and math.isfinite(current_end_safe_z) else new_safe
    new_end = max(end_base, new_safe)
    return new_safe, new_end
