"""CNC-Programmierer (Projektfeld) – getrennt vom Software-Autor.

Keine Ableitung aus APP_AUTHOR. Keine CNC-Bewegungslogik.
"""

from __future__ import annotations

from typing import Optional

MAX_PROGRAMMER_LENGTH = 50


class ProgrammerError(Exception):
    """Ungueltige Programmierer-Eingabe (GUI/JSON)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def normalize_programmer(value: Optional[str]) -> str:
    """Liefert bereinigten Programmierertext oder ''.

    Leer nach Trim ist erlaubt. Zeilenumbrueche, Steuerzeichen und
    Semikolon werden blockiert (keine NC-Zeilen-Injection).
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ProgrammerError("Programmierer muss Text sein.")
    text = value.strip()
    if not text:
        return ""
    if len(text) > MAX_PROGRAMMER_LENGTH:
        raise ProgrammerError(
            f"Programmierer darf hoechstens {MAX_PROGRAMMER_LENGTH} Zeichen haben."
        )
    if any(ch in "\r\n" for ch in text):
        raise ProgrammerError(
            "Programmierer darf keine Zeilenumbrueche enthalten."
        )
    if ";" in text:
        raise ProgrammerError(
            "Programmierer darf kein Semikolon enthalten."
        )
    if any(ord(ch) < 32 for ch in text):
        raise ProgrammerError(
            "Programmierer darf keine Steuerzeichen enthalten."
        )
    return text


def programmer_comment_line(normalized: str) -> Optional[str]:
    """NC-Kommentarzeile oder None, wenn kein Programmierer gesetzt ist."""
    if not normalized:
        return None
    return f"; PROGRAMMIERER: {normalized}"
