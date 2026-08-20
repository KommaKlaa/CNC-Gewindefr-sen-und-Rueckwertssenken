"""BSF-Prozessanimation: 9 Schritte, Blade-Zustaende, Maschinenstatus."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Callable, List, Optional

from help_views.bsf_geometry_model import BSFGeometryHelpSnapshot
from ui.bsf_geometry_canvas import BLADE_CLOSED, BLADE_DEPLOYED, VIEW_PROCESS_FOCUS, draw_bsf_geometry


PROCESS_STEPS: List[str] = [
    "1. A – Anfahren",
    "2. geschlossen durch Bohrung nach X",
    "3. an X Druck/IK aus + Aktivierungsdrehzahl",
    "4. zurueck Richtung B",
    "5. C – Schneide greift",
    "6. D – Rueckwaertssenken fertig",
    "7. zurueck nach X",
    "8. M5 + Druck/IK ein + Messer einfahren",
    "9. zurueck ueber A / aus Werkstueck",
]


@dataclass(frozen=True)
class ProcessMachineStatus:
    spindle: str
    pressure_ik: str
    blade: str
    position: str
    tool_z: Optional[float]
    blade_state: str


def machine_status_for_step(step_index: int, snapshot: BSFGeometryHelpSnapshot) -> ProcessMachineStatus:
    a = snapshot.a_z
    x = snapshot.x_z
    b = snapshot.b_z
    c = snapshot.c_z
    d = snapshot.d_z
    mapping = {
        0: ("AUS", "EIN", "GESCHLOSSEN", "A", a, BLADE_CLOSED),
        1: ("AUS", "EIN", "GESCHLOSSEN", "X", x, BLADE_CLOSED),
        2: ("AKTIVIERUNG", "AUS", "AUSGEKLAPPT", "X", x, BLADE_DEPLOYED),
        3: ("ARBEIT", "AUS", "AUSGEKLAPPT", "B", b, BLADE_DEPLOYED),
        4: ("ARBEIT", "AUS", "AUSGEKLAPPT", "C", c, BLADE_DEPLOYED),
        5: ("ARBEIT", "AUS", "AUSGEKLAPPT", "D", d, BLADE_DEPLOYED),
        6: ("ARBEIT", "AUS", "AUSGEKLAPPT", "X", x, BLADE_DEPLOYED),
        7: ("AUS", "EIN", "GESCHLOSSEN", "X", x, BLADE_CLOSED),
        8: ("AUS", "EIN", "GESCHLOSSEN", "A", a, BLADE_CLOSED),
    }
    spindle, pressure, blade, pos, tool_z, blade_state = mapping.get(
        step_index, ("AUS", "EIN", "GESCHLOSSEN", "A", a, BLADE_CLOSED)
    )
    return ProcessMachineStatus(
        spindle=spindle,
        pressure_ik=pressure,
        blade=blade,
        position=pos,
        tool_z=tool_z,
        blade_state=blade_state,
    )


class BSFProcessAnimator:
    def __init__(
        self,
        canvas: tk.Canvas,
        step_var: tk.StringVar,
        *,
        on_redraw: Callable[[int], None],
        status_callback: Optional[Callable[[ProcessMachineStatus], None]] = None,
    ) -> None:
        self.canvas = canvas
        self.step_var = step_var
        self.on_redraw = on_redraw
        self.status_callback = status_callback
        self.step_index = 0
        self.playing = False
        self._after_id = None
        self._motion_after = None
        self._update()

    def close(self) -> None:
        self.playing = False
        for attr in ("_after_id", "_motion_after"):
            aid = getattr(self, attr, None)
            if aid is not None:
                try:
                    self.canvas.after_cancel(aid)
                except tk.TclError:
                    pass
                setattr(self, attr, None)

    def first(self) -> None:
        self.step_index = 0
        self._update()

    def last(self) -> None:
        self.step_index = len(PROCESS_STEPS) - 1
        self._update()

    def prev(self) -> None:
        self.step_index = max(0, self.step_index - 1)
        self._update()

    def next(self) -> None:
        self.step_index = min(len(PROCESS_STEPS) - 1, self.step_index + 1)
        self._update()

    def toggle_play(self) -> None:
        self.playing = not self.playing
        if self.playing:
            self._tick()

    def _tick(self) -> None:
        if not self.playing:
            return
        if self.step_index < len(PROCESS_STEPS) - 1:
            self.step_index += 1
        else:
            self.step_index = 0
        self._update()
        self._after_id = self.canvas.after(900, self._tick)

    def _update(self) -> None:
        self.step_var.set(PROCESS_STEPS[self.step_index])
        self.on_redraw(self.step_index)


def draw_process_frame(
    canvas: tk.Canvas,
    snapshot: BSFGeometryHelpSnapshot,
    step_index: int,
) -> ProcessMachineStatus:
    status = machine_status_for_step(step_index, snapshot)
    draw_bsf_geometry(
        canvas,
        snapshot,
        tool_z=status.tool_z,
        blade_state=status.blade_state,
        show_tool=True,
        title=f"Schritt {PROCESS_STEPS[step_index]}",
        view_mode=VIEW_PROCESS_FOCUS,
    )
    return status
