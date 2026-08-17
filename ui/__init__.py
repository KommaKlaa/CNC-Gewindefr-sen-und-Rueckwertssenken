"""UI-Hilfen und Panels fuer den NC-Generator.

BSF.GEOM.1: Schwertfelder liegen im Panel ``HEULE BSF Werkzeug``
(blade_thickness, blade_measurement_reference).
Domain/NC: ``bsf_blade.py``.
"""

from .scrollable import ScrollableFrame
from .constants import (
    MODE_BGF,
    MODE_BSF,
    POSITION_LABELS_BGF,
    POSITION_LABELS_BSF,
)

__all__ = [
    "ScrollableFrame",
    "MODE_BGF",
    "MODE_BSF",
    "POSITION_LABELS_BGF",
    "POSITION_LABELS_BSF",
]
