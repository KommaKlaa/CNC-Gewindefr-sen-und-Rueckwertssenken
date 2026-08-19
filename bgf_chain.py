"""CALL-PGM-sichere BGF-Programmstruktur.

Das lokale Bearbeitungs-Unterprogramm LBL 100 darf nach dem Hauptlauf
nicht linear betreten werden. M30/M2 wuerden in einem per CALL PGM
aufgerufenen Child den Ruecksprung in die Verkettung verhindern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

# Reserviertes internes End-Label. Darf nicht als Bearbeitungs- oder Schleifenlabel
# verwendet werden. LBL 1 = Teilkreis-Schleife, LBL 100 = Bearbeitung, LBL 0 = Sub-Ende.
BGF_CHAIN_END_LABEL = 999
BGF_MACHINING_SUB_LABEL = 100

_FN12_RE = re.compile(r"^FN 12: IF \+Q2 LT \+(\d+) GOTO LBL 1\b")
_Q2_INIT_RE = re.compile(r"^Q2 = \+0\b")
_Q2_INC_RE = re.compile(r"^Q2 = Q2 \+ 1\b")
_END_Z_RE = re.compile(r"^L Z[+-]\d+\.\d+ R0 FMAX$")
_CALL_100_RE = re.compile(r"^CALL LBL 100\b")
_GOTO_100_RE = re.compile(r"GOTO LBL 100\b")
_M30_RE = re.compile(r"\bM30\b")
_M2_RE = re.compile(r"\bM2\b")


def skip_over_local_subprogram_line(end_label: int = BGF_CHAIN_END_LABEL) -> str:
    return f"FN 9: IF +0 EQU +0 GOTO LBL {end_label}"


def chain_end_label_line(end_label: int = BGF_CHAIN_END_LABEL) -> str:
    return f"LBL {end_label}"


def _code_lines(code: str) -> List[str]:
    return [ln.rstrip() for ln in code.replace("\r\n", "\n").split("\n")]


def _exec_text(line: str) -> str:
    return line.split(";", 1)[0].strip()


def _is_blank_or_comment(line: str) -> bool:
    text = line.strip()
    return not text or text.startswith(";")


def has_program_end_m_code(code: str) -> tuple[bool, bool]:
    has_m30 = False
    has_m2 = False
    for line in _code_lines(code):
        if _M30_RE.search(line):
            has_m30 = True
        if _M2_RE.search(line):
            has_m2 = True
    return has_m30, has_m2


@dataclass(frozen=True)
class BgfPartCircleFlow:
    q2_starts_at_zero: bool
    call_before_q2_increment: bool
    q2_increment_once_per_iteration: bool
    fn12_lt_count: Optional[int]
    skip_after_loop: bool
    end_z_without_m30: bool
    lbl100_only_via_call: bool
    linear_fallthrough: bool
    end_label_after_lbl0: bool
    end_pgm_after_end_label: bool
    has_m30: bool
    has_m2: bool
    simulated_machining_count: Optional[int]
    extra_final_machining: bool
    call_pgm_safe_return: bool
    end_pgm_reachable: bool

    @property
    def ok(self) -> bool:
        count = self.fn12_lt_count
        return bool(
            self.q2_starts_at_zero
            and self.call_before_q2_increment
            and self.q2_increment_once_per_iteration
            and count is not None
            and self.skip_after_loop
            and self.end_z_without_m30
            and self.lbl100_only_via_call
            and not self.linear_fallthrough
            and self.end_label_after_lbl0
            and self.end_pgm_after_end_label
            and not self.has_m30
            and not self.has_m2
            and self.simulated_machining_count == count
            and not self.extra_final_machining
            and self.call_pgm_safe_return
            and self.end_pgm_reachable
        )


def analyze_bgf_part_circle_nc(code: str) -> BgfPartCircleFlow:
    lines = _code_lines(code)
    has_m30, has_m2 = has_program_end_m_code(code)

    q2_starts = False
    fn12_i: Optional[int] = None
    fn12_count: Optional[int] = None
    lbl1_i: Optional[int] = None
    lbl100_i: Optional[int] = None
    lbl0_i: Optional[int] = None
    lbl999_i: Optional[int] = None
    skip_i: Optional[int] = None
    end_pgm_i: Optional[int] = None
    skip_line = skip_over_local_subprogram_line()
    end_label = chain_end_label_line()

    for i, raw in enumerate(lines):
        text = _exec_text(raw)
        if _Q2_INIT_RE.match(text):
            q2_starts = True
        if re.match(r"^LBL 1(?:\s|$)", text):
            lbl1_i = i
        match = _FN12_RE.match(text)
        if match:
            fn12_i = i
            fn12_count = int(match.group(1))
        if re.match(r"^LBL 100(?:\s|$)", text):
            lbl100_i = i
        if text == "LBL 0":
            lbl0_i = i
        if text == end_label:
            lbl999_i = i
        if text == skip_line:
            skip_i = i
        if text.startswith("END PGM "):
            end_pgm_i = i

    call_before = False
    q2_once = False
    if lbl1_i is not None and fn12_i is not None and fn12_i > lbl1_i:
        loop = lines[lbl1_i : fn12_i + 1]
        call_idxs = [j for j, ln in enumerate(loop) if _CALL_100_RE.match(_exec_text(ln))]
        inc_idxs = [j for j, ln in enumerate(loop) if _Q2_INC_RE.match(_exec_text(ln))]
        q2_once = len(inc_idxs) == 1
        call_before = bool(call_idxs and inc_idxs and call_idxs[0] < inc_idxs[0])

    goto_100 = any(_GOTO_100_RE.search(ln) for ln in lines)
    lbl100_only_via_call = (
        lbl100_i is not None
        and not goto_100
        and any(_CALL_100_RE.match(_exec_text(ln)) for ln in lines)
    )

    end_z_ok = False
    skip_after_loop = False
    if fn12_i is not None:
        after_exec = [ln for ln in lines[fn12_i + 1 :] if not _is_blank_or_comment(ln)]
        if after_exec:
            first = _exec_text(after_exec[0])
            end_z_ok = bool(_END_Z_RE.match(first)) and "M30" not in after_exec[0] and "M2" not in after_exec[0]
        if len(after_exec) >= 2:
            skip_after_loop = _exec_text(after_exec[1]) == skip_line

    linear_fallthrough = not (
        fn12_i is not None
        and skip_i is not None
        and lbl100_i is not None
        and fn12_i < skip_i < lbl100_i
        and skip_after_loop
    )
    extra_final = linear_fallthrough
    simulated = None
    if fn12_count is not None:
        simulated = fn12_count + (1 if extra_final else 0)

    end_label_after_lbl0 = (
        lbl100_i is not None
        and lbl0_i is not None
        and lbl999_i is not None
        and lbl100_i < lbl0_i < lbl999_i
    )
    end_pgm_after = (
        lbl999_i is not None
        and end_pgm_i is not None
        and end_pgm_i > lbl999_i
    )
    if end_pgm_after and lbl999_i is not None and end_pgm_i is not None:
        between = [ln for ln in lines[lbl999_i + 1 : end_pgm_i] if not _is_blank_or_comment(ln)]
        end_pgm_after = not between

    end_pgm_reachable = skip_after_loop and end_pgm_after and not has_m30 and not has_m2
    call_pgm_safe = end_pgm_reachable and not linear_fallthrough and lbl100_only_via_call

    return BgfPartCircleFlow(
        q2_starts_at_zero=q2_starts,
        call_before_q2_increment=call_before,
        q2_increment_once_per_iteration=q2_once,
        fn12_lt_count=fn12_count,
        skip_after_loop=skip_after_loop,
        end_z_without_m30=end_z_ok,
        lbl100_only_via_call=lbl100_only_via_call,
        linear_fallthrough=linear_fallthrough,
        end_label_after_lbl0=end_label_after_lbl0,
        end_pgm_after_end_label=end_pgm_after,
        has_m30=has_m30,
        has_m2=has_m2,
        simulated_machining_count=simulated,
        extra_final_machining=extra_final,
        call_pgm_safe_return=call_pgm_safe,
        end_pgm_reachable=end_pgm_reachable,
    )


def require_bgf_part_circle_chain_safe(code: str, expected_count: int) -> BgfPartCircleFlow:
    flow = analyze_bgf_part_circle_nc(code)
    if flow.fn12_lt_count != expected_count:
        raise RuntimeError(
            f"BGF Teilkreis: FN 12 count={flow.fn12_lt_count}, erwartet {expected_count}."
        )
    if flow.simulated_machining_count != expected_count:
        raise RuntimeError(
            f"BGF Teilkreis: Control-Flow count={flow.simulated_machining_count}, "
            f"erwartet {expected_count}."
        )
    if not flow.ok:
        raise RuntimeError(f"BGF Teilkreis: CALL-PGM-Struktur ungueltig: {flow}")
    return flow
