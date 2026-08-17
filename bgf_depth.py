"""BGF-Tiefenvalidierung: Gewindetiefe vs. Kernloch vs. Hersteller-Template.

Variable kuerzere Tiefen: AXIAL_TEMPLATE_SHIFT_MODEL (siehe bgf_variable_depth).
Keine Behauptung einer offiziellen CERATIZIT-Variable-Depth-Formel.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from bgf_variable_depth import compute_axial_template_shift


TEMPLATE_DEPTH_TOLERANCE = 1e-6
# Freigabegrenze: Werte innerhalb dieser Toleranz gelten als <= approved_max.
APPROVED_MAX_TOLERANCE = 1e-6


class DepthGateStatus(str, Enum):
    INVALID = "INVALID"
    TEMPLATE_OK = "TEMPLATE_OK"
    VARIABLE_DEPTH_AXIAL_SHIFT_OK = "VARIABLE_DEPTH_AXIAL_SHIFT_OK"
    VARIABLE_BLOCKED = "VARIABLE_BLOCKED"  # Legacy / tiefer als Template
    MAX_THREAD_DEPTH_UNVALIDATED = "MAX_THREAD_DEPTH_UNVALIDATED"
    THREAD_DEPTH_EXCEEDS_APPROVED_MAX = "THREAD_DEPTH_EXCEEDS_APPROVED_MAX"
    # Alias fuer aeltere Tests / Lesbarkeit
    MAX_EXCEEDED = "THREAD_DEPTH_EXCEEDS_APPROVED_MAX"
    CORE_HOLE_EXCEEDED = "CORE_HOLE_EXCEEDED"
    INVALID_SHIFTED_GEOMETRY = "INVALID_SHIFTED_GEOMETRY"


@dataclass(frozen=True)
class BGFDepthRequest:
    """Benutzeranforderung (Zeichnung)."""

    thread_depth: float
    core_hole_depth: Optional[float] = None


@dataclass(frozen=True)
class BGFDepthPolicy:
    """Werkzeug-/Freigabepolitik.

    approved_max_thread_depth: Software-Freigabegrenze (nicht zwingend physikalisches Maximum).
    None = Freigabegrenze noch nicht hinterlegt.
    axial_increment: Summe |IZ| der Hersteller-Pass-Helix (fuer deepest milling).
    """

    thread_size: str
    article_no: str
    template_thread_depth: float
    template_drill_depth: float
    template_mill_start_depth: float
    approved_max_thread_depth: Optional[float] = None
    axial_increment: float = 0.0
    # Legacy-Flag: bei True war frueher eine (nicht vorhandene) Herstellerformel gemeint.
    # DEPTH.4 nutzt AXIAL_TEMPLATE_SHIFT unabhaengig davon.
    variable_depth_rule_validated: bool = False

    @property
    def max_thread_depth(self) -> Optional[float]:
        """Kompatibilitaet: technische Alias-Property."""
        return self.approved_max_thread_depth


@dataclass
class BGFDepthEvaluation:
    ok_for_nc: bool
    status: DepthGateStatus
    messages: List[str] = field(default_factory=list)
    is_template: bool = False
    thread_end_z: Optional[float] = None
    template_nc_drill_z: Optional[float] = None
    template_nc_mill_start_z: Optional[float] = None
    nc_drill_depth: Optional[float] = None
    nc_mill_start_depth: Optional[float] = None
    nc_drill_z: Optional[float] = None
    nc_mill_start_z: Optional[float] = None
    deepest_milling_depth: Optional[float] = None
    drill_reserve: Optional[float] = None
    depth_delta: Optional[float] = None
    approved_max_thread_depth: Optional[float] = None
    max_thread_depth: Optional[float] = None  # Alias-Spiegelung
    within_approved_max: Optional[bool] = None
    status_text: str = ""
    status_level: str = "red"  # green | yellow | red
    depth_mode_label: str = ""


def is_template_thread_depth(requested: float, template: float, tol: float = TEMPLATE_DEPTH_TOLERANCE) -> bool:
    if not math.isfinite(requested) or not math.isfinite(template):
        return False
    return abs(requested - template) <= tol


def exceeds_approved_max(thread_depth: float, approved_max: float, tol: float = APPROVED_MAX_TOLERANCE) -> bool:
    """True wenn Gewindetiefe die Software-Freigabegrenze ueberschreitet."""
    return thread_depth > approved_max + tol


def thread_end_z(surface_z: float, thread_depth: float) -> float:
    """Geometrisch: Z_Gewindeende = surface_z - Gewindetiefe."""
    return surface_z - thread_depth


def policy_from_tool(
    thread_size: str,
    template_thread_depth: float,
    template_drill_depth: float,
    template_mill_start_depth: float,
    *,
    article_no: str = "",
    approved_max_thread_depth: Optional[float] = None,
    max_thread_depth: Optional[float] = None,
    axial_increment: float = 0.0,
    variable_depth_rule_validated: bool = False,
) -> BGFDepthPolicy:
    # max_thread_depth-Parameter nur fuer Rueckwaertskompatibilitaet der Tests
    approved = approved_max_thread_depth if approved_max_thread_depth is not None else max_thread_depth
    return BGFDepthPolicy(
        thread_size=thread_size,
        article_no=article_no,
        template_thread_depth=template_thread_depth,
        template_drill_depth=template_drill_depth,
        template_mill_start_depth=template_mill_start_depth,
        approved_max_thread_depth=approved,
        axial_increment=axial_increment,
        variable_depth_rule_validated=variable_depth_rule_validated,
    )


def _eval_base(
    *,
    ok_for_nc: bool,
    status: DepthGateStatus,
    messages: List[str],
    status_text: str,
    status_level: str,
    policy: BGFDepthPolicy,
    thread_end: Optional[float],
    tpl_drill_z: float,
    tpl_mill_z: float,
    is_template: bool = False,
    within_approved_max: Optional[bool] = None,
    nc_drill_depth: Optional[float] = None,
    nc_mill_start_depth: Optional[float] = None,
    nc_drill_z: Optional[float] = None,
    nc_mill_start_z: Optional[float] = None,
    deepest_milling_depth: Optional[float] = None,
    drill_reserve: Optional[float] = None,
    depth_delta: Optional[float] = None,
    depth_mode_label: str = "",
) -> BGFDepthEvaluation:
    return BGFDepthEvaluation(
        ok_for_nc=ok_for_nc,
        status=status,
        messages=messages,
        is_template=is_template,
        thread_end_z=thread_end,
        template_nc_drill_z=tpl_drill_z,
        template_nc_mill_start_z=tpl_mill_z,
        nc_drill_depth=nc_drill_depth,
        nc_mill_start_depth=nc_mill_start_depth,
        nc_drill_z=nc_drill_z,
        nc_mill_start_z=nc_mill_start_z,
        deepest_milling_depth=deepest_milling_depth,
        drill_reserve=drill_reserve,
        depth_delta=depth_delta,
        approved_max_thread_depth=policy.approved_max_thread_depth,
        max_thread_depth=policy.approved_max_thread_depth,
        within_approved_max=within_approved_max,
        status_text=status_text,
        status_level=status_level,
        depth_mode_label=depth_mode_label,
    )


def evaluate_bgf_depth(
    request: BGFDepthRequest,
    policy: BGFDepthPolicy,
    surface_z: float = 0.0,
) -> BGFDepthEvaluation:
    """Validiert Tiefen. Reihenfolge: numerisch → >0 → approved max → Kernloch → Template/Shift."""
    tpl_drill_z = surface_z - policy.template_drill_depth
    tpl_mill_z = surface_z - policy.template_mill_start_depth

    td = request.thread_depth
    if not isinstance(td, (int, float)) or not math.isfinite(float(td)):
        return _eval_base(
            ok_for_nc=False,
            status=DepthGateStatus.INVALID,
            messages=["Gewindetiefe muss eine endliche Zahl sein (kein NaN/Infinity)."],
            status_text="Ungueltige Tiefenkombination",
            status_level="red",
            policy=policy,
            thread_end=None,
            tpl_drill_z=tpl_drill_z,
            tpl_mill_z=tpl_mill_z,
        )

    td = float(td)
    if td <= 0:
        return _eval_base(
            ok_for_nc=False,
            status=DepthGateStatus.INVALID,
            messages=["Gewindetiefe muss groesser 0 sein."],
            status_text="Ungueltige Tiefenkombination",
            status_level="red",
            policy=policy,
            thread_end=None,
            tpl_drill_z=tpl_drill_z,
            tpl_mill_z=tpl_mill_z,
        )

    end_z = thread_end_z(surface_z, td)

    # Software-Freigabegrenze (vor Kernloch)
    if policy.approved_max_thread_depth is not None:
        mx = float(policy.approved_max_thread_depth)
        if exceeds_approved_max(td, mx):
            tool_label = f"{policy.thread_size}"
            if policy.article_no:
                tool_label += f" / Artikel {policy.article_no}"
            msg = (
                f"Die Gewindetiefe {td:.3f} mm ueberschreitet die aktuell freigegebene "
                f"maximale Gewindetiefe von {mx:.3f} mm fuer dieses Werkzeug ({tool_label}). "
                "Fuer groessere Gewindetiefen ist eine zusaetzliche Herstellerfreigabe "
                "bzw. Werkzeugdefinition erforderlich."
            )
            return _eval_base(
                ok_for_nc=False,
                status=DepthGateStatus.THREAD_DEPTH_EXCEEDS_APPROVED_MAX,
                messages=[msg],
                status_text="Gewindetiefe ueberschreitet Freigabegrenze",
                status_level="red",
                policy=policy,
                thread_end=end_z,
                tpl_drill_z=tpl_drill_z,
                tpl_mill_z=tpl_mill_z,
                within_approved_max=False,
            )

    within_max: Optional[bool]
    if policy.approved_max_thread_depth is None:
        within_max = None
    else:
        within_max = True

    # Kernloch-Sanity
    if request.core_hole_depth is not None:
        ch = request.core_hole_depth
        if not isinstance(ch, (int, float)) or not math.isfinite(float(ch)):
            return _eval_base(
                ok_for_nc=False,
                status=DepthGateStatus.INVALID,
                messages=["Kernlochtiefe Soll muss eine endliche Zahl sein."],
                status_text="Ungueltige Tiefenkombination",
                status_level="red",
                policy=policy,
                thread_end=end_z,
                tpl_drill_z=tpl_drill_z,
                tpl_mill_z=tpl_mill_z,
                within_approved_max=within_max,
            )
        ch = float(ch)
        if ch <= 0:
            return _eval_base(
                ok_for_nc=False,
                status=DepthGateStatus.INVALID,
                messages=["Kernlochtiefe Soll muss groesser 0 sein."],
                status_text="Ungueltige Tiefenkombination",
                status_level="red",
                policy=policy,
                thread_end=end_z,
                tpl_drill_z=tpl_drill_z,
                tpl_mill_z=tpl_mill_z,
                within_approved_max=within_max,
            )
        if td > ch:
            msg = (
                f"Die Gewindetiefe {td:.3f} mm ueberschreitet die angegebene "
                f"Kernlochtiefe {ch:.3f} mm."
            )
            return _eval_base(
                ok_for_nc=False,
                status=DepthGateStatus.CORE_HOLE_EXCEEDED,
                messages=[msg],
                status_text="Ungueltige Tiefenkombination",
                status_level="red",
                policy=policy,
                thread_end=end_z,
                tpl_drill_z=tpl_drill_z,
                tpl_mill_z=tpl_mill_z,
                within_approved_max=within_max,
            )

    # AXIAL_TEMPLATE_SHIFT_MODEL
    shift = compute_axial_template_shift(
        requested_thread_depth=td,
        template_thread_depth=policy.template_thread_depth,
        template_mill_start_depth=policy.template_mill_start_depth,
        template_drill_depth=policy.template_drill_depth,
        axial_increment=policy.axial_increment,
        template_tolerance=TEMPLATE_DEPTH_TOLERANCE,
    )

    if not shift.ok:
        status = (
            DepthGateStatus.VARIABLE_BLOCKED
            if shift.error and "ueber dem Hersteller-Template" in shift.error
            else DepthGateStatus.INVALID_SHIFTED_GEOMETRY
        )
        return _eval_base(
            ok_for_nc=False,
            status=status,
            messages=[shift.error or "Unplausible Shift-Geometrie."],
            status_text=(
                "Gewindetiefe ueber Hersteller-Template – NC blockiert"
                if status == DepthGateStatus.VARIABLE_BLOCKED
                else "Unplausible Shift-Geometrie – NC blockiert"
            ),
            status_level="red",
            policy=policy,
            thread_end=end_z,
            tpl_drill_z=tpl_drill_z,
            tpl_mill_z=tpl_mill_z,
            within_approved_max=within_max,
            depth_delta=shift.depth_delta if math.isfinite(shift.depth_delta) else None,
        )

    nc_drill_z = surface_z - shift.drill_depth
    nc_mill_z = surface_z - shift.mill_start_depth

    if shift.is_template:
        return _eval_base(
            ok_for_nc=True,
            status=DepthGateStatus.TEMPLATE_OK,
            messages=["Hersteller-Template – NC-Code freigegeben"],
            status_text="Hersteller-Template – NC-Code freigegeben",
            status_level="green",
            policy=policy,
            thread_end=end_z,
            tpl_drill_z=tpl_drill_z,
            tpl_mill_z=tpl_mill_z,
            is_template=True,
            within_approved_max=within_max if within_max is not None else True,
            nc_drill_depth=shift.drill_depth,
            nc_mill_start_depth=shift.mill_start_depth,
            nc_drill_z=nc_drill_z,
            nc_mill_start_z=nc_mill_z,
            deepest_milling_depth=shift.deepest_milling_depth,
            drill_reserve=shift.drill_reserve,
            depth_delta=0.0,
            depth_mode_label="CERATIZIT Hersteller-Template",
        )

    if policy.approved_max_thread_depth is None:
        msg = (
            f"Die gewuenschte Gewindetiefe {td:.3f} mm ist erfasst. "
            "Aktuell freigegebene max. Gewindetiefe fuer dieses Werkzeug noch nicht hinterlegt."
        )
        return _eval_base(
            ok_for_nc=False,
            status=DepthGateStatus.MAX_THREAD_DEPTH_UNVALIDATED,
            messages=[msg],
            status_text="Variable Gewindetiefe – Freigabegrenze noch nicht hinterlegt",
            status_level="yellow",
            policy=policy,
            thread_end=end_z,
            tpl_drill_z=tpl_drill_z,
            tpl_mill_z=tpl_mill_z,
            within_approved_max=None,
            depth_delta=shift.depth_delta,
            nc_drill_depth=shift.drill_depth,
            nc_mill_start_depth=shift.mill_start_depth,
        )

    return _eval_base(
        ok_for_nc=True,
        status=DepthGateStatus.VARIABLE_DEPTH_AXIAL_SHIFT_OK,
        messages=[
            "Variable Gewindetiefe – Axiale Template-Verschiebung – NC-Code freigegeben"
        ],
        status_text="Variable Gewindetiefe – Axiale Template-Verschiebung – NC-Code freigegeben",
        status_level="green",
        policy=policy,
        thread_end=end_z,
        tpl_drill_z=tpl_drill_z,
        tpl_mill_z=tpl_mill_z,
        is_template=False,
        within_approved_max=within_max,
        nc_drill_depth=shift.drill_depth,
        nc_mill_start_depth=shift.mill_start_depth,
        nc_drill_z=nc_drill_z,
        nc_mill_start_z=nc_mill_z,
        deepest_milling_depth=shift.deepest_milling_depth,
        drill_reserve=shift.drill_reserve,
        depth_delta=shift.depth_delta,
        depth_mode_label="Axiale Template-Verschiebung",
    )
