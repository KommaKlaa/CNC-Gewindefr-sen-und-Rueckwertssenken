"""HEULE BSF Schwertgeometrie (PHASE BSF.GEOM.1).

Physische Bewegungsrichtung der bestehenden BSF-Sequenz
======================================================
Vertikale Spindel, Maschinen-+Z zur Spindel, -Z zur Werkzeugspitze / Tisch.

Ablauf (Source ``get_bsf_sequence`` + Werkstueck-Z):

1. Werkzeug taucht mit geschlossenem Messer durch die Bohrung
   auf ``z_clearance`` (negativer als die Bund-Unterseite).
2. Unterhalb des Bundes: Spindel ein, Messer aktivieren.
3. Senkbewegung auf ``z_sink_finish``.
   Bei Z0 = Unterkante Bund: z_clearance = -clearance, z_sink_finish = +sink_depth.
   Die Senkbewegung laeuft damit in **+Z (zur Spindel / zum Bund)**.
4. Zurueck auf z_clearance, Messer schliessen, aus der Bohrung.

FINISH_EDGE
-----------
Die fertige Senkflaeche entsteht an der Kante, die beim Vorschub **nach oben
(zur Spindel)** zuerst das Werkstueck trifft:

    FINISH_EDGE = SPINDLE_SIDE_EDGE  (spindelseitige Schwertkante / Oberkante)

Verifiziert aus:
- bestehender Z-Formel (Senkflaeche positiver als Freifahrt)
- Sequenzkommentar „Durch den Bund tauchen“ / „Senken auf Fertigmass“
- vorhandener Prozessbeschreibung: Senkbewegung im Vorschub nach oben

Vorzeichentabelle (Offset wird auf Werkstueck-Z der Werkzeugreferenz addiert)
--------------------------------------------------------------------------
programmed_z = workpiece_z + offset

FINISH EDGE              MEASURED EDGE             OFFSET
SPINDLE_SIDE_EDGE        SPINDLE_SIDE_EDGE         0
SPINDLE_SIDE_EDGE        TOOL_TIP_SIDE_EDGE        -thickness

(Die umgekehrte Finish-Kante ist fuer HEULE-BSF-Rueckwaertssenken nicht aktiv.)

Z-Werte
-------
Betroffen (gleiche Werkzeugreferenz, physische Schneidenlage invariant):
  z_sink_finish  YES
  z_clearance    YES
  z_app          YES (folgt z_sink_finish in der Sequenz)

Nicht betroffen:
  safe_z         NO  (Bediener-Sicherheitsabstand ueber dem Teil)
  end_safe_z     NO
  hardcoded Z+1  NO  (bestehende Spindel-Ein-Position, kein Schwertbezug)

Freifahrtiefe ``clearance`` bleibt ein Werkstueck-/Prozessmass. Der Offset
verschiebt nur die programmierte Werkzeugreferenz, damit die reale Schwertlage
bei geaenderter Vermesskante gleich bleibt.

Z0 Unterkante/Oberkante Bund ist workpiece_z_reference – getrennt von
blade_measurement_reference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class BladeMeasurementReference(Enum):
    SPINDLE_SIDE_EDGE = "spindle_side"
    TOOL_TIP_SIDE_EDGE = "tool_tip_side"


# Technologisch fest: Rueckwaertssenken, Vorschub zur Spindel.
FINISH_EDGE = BladeMeasurementReference.SPINDLE_SIDE_EDGE

MEASUREMENT_LABELS = {
    BladeMeasurementReference.SPINDLE_SIDE_EDGE: (
        "Spindelseitige Schwertkante (Oberkante)"
    ),
    BladeMeasurementReference.TOOL_TIP_SIDE_EDGE: (
        "Werkzeugspitzenseitige Schwertkante (Unterkante)"
    ),
}

MEASUREMENT_NC_COMMENTS = {
    BladeMeasurementReference.SPINDLE_SIDE_EDGE: "SPINDELSEITIGER SCHWERTKANTE",
    BladeMeasurementReference.TOOL_TIP_SIDE_EDGE: "WERKZEUGSPITZENSEITIGER SCHWERTKANTE",
}

MEASUREMENT_PLACEHOLDER = "--- bitte waehlen ---"


class BSFBladeError(ValueError):
    pass


@dataclass(frozen=True)
class BSFBladeGeometry:
    thickness: float
    measurement_reference: BladeMeasurementReference
    finish_edge: BladeMeasurementReference = FINISH_EDGE


def validate_blade_thickness(value: float) -> Optional[str]:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "Schwertdicke muss numerisch sein."
    if not math.isfinite(value):
        return "Schwertdicke darf nicht NaN/Infinity sein."
    if value <= 0:
        return "Schwertdicke muss groesser 0 sein."
    return None


def parse_blade_thickness(text: str) -> Tuple[bool, Optional[float], Optional[str]]:
    raw = (text or "").strip()
    if raw == "":
        return False, None, "Schwertdicke axial fehlt."
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        return False, None, "Schwertdicke muss numerisch sein."
    err = validate_blade_thickness(value)
    if err:
        return False, None, err
    return True, value, None


def parse_measurement_reference(label: str) -> Tuple[bool, Optional[BladeMeasurementReference], Optional[str]]:
    raw = (label or "").strip()
    if raw == "" or raw == MEASUREMENT_PLACEHOLDER:
        return False, None, "Vermessreferenz der Werkzeuglaenge fehlt."
    for enum_val, text in MEASUREMENT_LABELS.items():
        if raw == text or raw == enum_val.value or raw == enum_val.name:
            return True, enum_val, None
    return False, None, "Unbekannte Vermessreferenz."


def blade_reference_offset(
    thickness: float,
    measurement_reference: BladeMeasurementReference,
    finish_edge: BladeMeasurementReference = FINISH_EDGE,
) -> float:
    """Axialer Offset: programmed_z = workpiece_z + offset.

    +Z zur Spindel. Fertigkante = spindelseitige Schwertkante.
    Gegenueberliegende Vermesskante liegt um ``thickness`` in -Z;
    die programmierte Referenz muss um -thickness verschoben werden,
    damit die reale Fertigkante am Werkstueckmass bleibt.
    """
    err = validate_blade_thickness(thickness)
    if err:
        raise BSFBladeError(err)
    if not isinstance(measurement_reference, BladeMeasurementReference):
        raise BSFBladeError("Unbekannte Vermessreferenz.")
    if not isinstance(finish_edge, BladeMeasurementReference):
        raise BSFBladeError("Unbekannte Fertigkante.")
    if measurement_reference == finish_edge:
        return 0.0
    if (
        finish_edge is BladeMeasurementReference.SPINDLE_SIDE_EDGE
        and measurement_reference is BladeMeasurementReference.TOOL_TIP_SIDE_EDGE
    ):
        return -float(thickness)
    # Umgekehrte Finish-Kante waere +thickness; fuer HEULE BSF nicht aktiv.
    raise BSFBladeError(
        "Kombination Finish-Kante / Vermessreferenz ist fuer HEULE BSF nicht definiert."
    )


def calculate_workpiece_bsf_z(
    bund_thickness: float,
    sink_depth: float,
    clearance: float,
    *,
    z0_is_flange_bottom: bool,
) -> dict:
    """Reine Werkstueck-Z ohne Schwertkorrektur (bestehende Formeln)."""
    if z0_is_flange_bottom:
        z_clearance = -abs(clearance)
        z_sink_finish = abs(sink_depth)
    else:
        z_clearance = -(abs(bund_thickness) + abs(clearance))
        z_sink_finish = -(abs(bund_thickness) - abs(sink_depth))
    return {"z_sink_finish": z_sink_finish, "z_clearance": z_clearance}


def apply_blade_offset(workpiece_z: dict, offset: float) -> dict:
    """Verschiebt Werkzeugreferenz-Z; safe_z bleibt aussen unberuehrt."""
    return {
        "z_sink_finish": workpiece_z["z_sink_finish"] + offset,
        "z_clearance": workpiece_z["z_clearance"] + offset,
    }


def physical_finish_edge_z(programmed_sink_finish: float, offset: float) -> float:
    """Reale Fertigkante aus programmierter Werkzeugreferenz zurueckrechnen."""
    return programmed_sink_finish - offset


def build_bsf_blade_geometry(thickness: float, measurement_reference: BladeMeasurementReference) -> BSFBladeGeometry:
    err = validate_blade_thickness(thickness)
    if err:
        raise BSFBladeError(err)
    if not isinstance(measurement_reference, BladeMeasurementReference):
        raise BSFBladeError("Unbekannte Vermessreferenz.")
    return BSFBladeGeometry(thickness=float(thickness), measurement_reference=measurement_reference)
