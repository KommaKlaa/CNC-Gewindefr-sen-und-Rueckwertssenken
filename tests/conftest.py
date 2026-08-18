"""Pytest-Konfiguration: GUI-Tests ohne Pflicht-Sicherheitsdialog."""

from __future__ import annotations

import os

os.environ.setdefault("NC_GENERATOR_SKIP_SAFETY_NOTICE", "1")
