"""BSF-Programmende-Modus: CHAIN_CALL_PGM vs. STANDALONE_M30.

Analoge Struktur zu bgf_chain.py, aber BSF-spezifisch und ohne
Abhaengigkeit von BGF-Modulen.

BSF_END_LABEL = 999
  - LBL 1   : Schleifenbeginn Teilkreis
  - LBL 100 : Bearbeitungs-Unterprogramm (Teilkreis)
  - LBL 0   : Unterprogramm-Ende
  - LBL 999 : Endblock (Sprungziel nach Schleife / Teilkreis-Chain-Guard)
  Kein Konflikt mit bestehenden Labels 1, 0, 100.
"""
from __future__ import annotations

import re

BSF_END_MODE_CHAIN = "CHAIN_CALL_PGM"
BSF_END_MODE_STANDALONE = "STANDALONE_M30"
BSF_END_MODE_VALUES = (BSF_END_MODE_CHAIN, BSF_END_MODE_STANDALONE)

# Label, das als Sprungziel fuer den Endblock verwendet wird (Teilkreis-Modus)
BSF_END_LABEL = 999

# GUI-Texte
_LABEL_CHAIN = "Verkettung / CALL PGM"
_LABEL_STANDALONE = "Einzelprogramm / M30"

_LABEL_MAP = {
    BSF_END_MODE_CHAIN: _LABEL_CHAIN,
    BSF_END_MODE_STANDALONE: _LABEL_STANDALONE,
}
_REVERSE_MAP = {v: k for k, v in _LABEL_MAP.items()}

BSF_END_MODE_HELP = (
    "Verkettung / CALL PGM: Fuer Programme, die aus einem Hauptprogramm "
    "ueber CALL PGM aufgerufen werden.\n"
    "Einzelprogramm / M30: Fuer Programme, die direkt gestartet werden "
    "und mit M30 enden."
)


def bsf_end_mode_label(mode: str) -> str:
    """Kanonischer Wert -> GUI-Label."""
    if mode not in _LABEL_MAP:
        raise ValueError(f"Ungueltiger BSF-Endmodus: {mode!r}")
    return _LABEL_MAP[mode]


def bsf_end_mode_from_label(label: str) -> str:
    """GUI-Label -> kanonischer Wert. ValueError bei unbekanntem Label."""
    result = _REVERSE_MAP.get((label or "").strip())
    if result is None:
        raise ValueError(f"Unbekanntes BSF-Endmodus-Label: {label!r}")
    return result


def validate_bsf_end_mode(mode: str) -> str:
    """Gibt mode zurueck wenn gueltig, sonst ValueError."""
    if mode not in BSF_END_MODE_VALUES:
        raise ValueError(f"Ungueltiger BSF-Endmodus: {mode!r}")
    return mode


def bsf_end_mode_comment(mode: str) -> str:
    """NC-Kommentarzeile fuer den Programmkopf."""
    if mode == BSF_END_MODE_CHAIN:
        return "; PROGRAMMENDE: VERKETTUNG / CALL PGM"
    if mode == BSF_END_MODE_STANDALONE:
        return "; PROGRAMMENDE: EINZELPROGRAMM / M30"
    raise ValueError(f"Ungueltiger BSF-Endmodus: {mode!r}")


def final_bsf_end_lines(end_safe_z: float, mode: str, fmt_axis) -> list[str]:
    """Erzeugt die finalen End-Zeilen (LBL 999-Block) fuer den gewaehlten Modus.

    Teilkreis: wird nach dem Sprung 'FN 9: IF 0 EQU 0 GOTO LBL 999' aufgerufen.
    Einzelposition / Koordinatenliste: direkt am Ende (kein LBL 999 noetig, aber
    konsistent verwenden fuer Teilkreis-Modus; fuer die anderen Modi direkt einhaengen).
    """
    z_line = f"L {fmt_axis('Z', end_safe_z)} R0 FMAX"
    if mode == BSF_END_MODE_CHAIN:
        return [z_line]
    if mode == BSF_END_MODE_STANDALONE:
        return [f"{z_line} M30"]
    raise ValueError(f"Ungueltiger BSF-Endmodus: {mode!r}")


def _exec_text(line: str) -> str:
    """Entfernt Kommentarteil (nach ; ) aus einer NC-Zeile."""
    return line.split(";", 1)[0]


def m30_exec_count(code: str) -> int:
    """Zaehlt ausfuehrbare M30-Vorkommen (nicht in Kommentaren)."""
    count = 0
    for line in code.splitlines():
        if re.search(r"\bM30\b", _exec_text(line)):
            count += 1
    return count


def analyze_bsf_part_circle_nc(code: str) -> dict:
    """Statische Control-Flow-Analyse einer BSF-Teilkreis-NC-Ausgabe.

    Gibt ein Dict mit:
      lbl1_i, fn12_i, fn9_guard_i, lbl100_i, lbl0_i, lbl999_i, end_pgm_i,
      m30_count, fallthrough, end_pgm_reachable
    """
    lines = [l.rstrip() for l in code.splitlines()]

    def find(pattern, start=0):
        for i in range(start, len(lines)):
            if re.search(pattern, lines[i]):
                return i
        return None

    lbl1_i = find(r"^LBL 1\b", 0)
    fn12_i = find(r"FN 12:.*GOTO LBL 1", 0)
    fn9_guard_i = find(r"FN 9:.*GOTO LBL 999", 0) if fn12_i is not None else None
    lbl100_i = find(r"^LBL 100\b")
    lbl0_i = find(r"^LBL 0$")
    lbl999_i = find(r"^LBL 999\b")
    end_pgm_i = find(r"^END PGM\b")

    m30_count = m30_exec_count(code)

    # Fallthrough-Pruefung: Gibt es nach FN12 einen Guard (FN9 oder M30) vor LBL100?
    if fn12_i is not None and lbl100_i is not None:
        between = lines[fn12_i + 1: lbl100_i]
        has_guard = any(
            re.search(r"FN 9:", l) or re.search(r"\bM30\b", _exec_text(l))
            for l in between
        )
        fallthrough = not has_guard
    else:
        fallthrough = None

    # END PGM erreichbar: nur wenn kein M30 zwischen letztem LBL0 und END PGM
    if lbl0_i is not None and end_pgm_i is not None:
        between_end = lines[lbl0_i + 1: end_pgm_i]
        m30_before_end = any(re.search(r"\bM30\b", _exec_text(l)) for l in between_end)
        end_pgm_reachable = not m30_before_end
    else:
        end_pgm_reachable = None

    return {
        "lbl1_i": lbl1_i,
        "fn12_i": fn12_i,
        "fn9_guard_i": fn9_guard_i,
        "lbl100_i": lbl100_i,
        "lbl0_i": lbl0_i,
        "lbl999_i": lbl999_i,
        "end_pgm_i": end_pgm_i,
        "m30_count": m30_count,
        "fallthrough": fallthrough,
        "end_pgm_reachable": end_pgm_reachable,
    }
