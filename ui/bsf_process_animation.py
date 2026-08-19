"""Schematische BSF-Prozessanimation (9 Schritte)."""

from __future__ import annotations

import tkinter as tk
from typing import Callable, List


PROCESS_STEPS: List[str] = [
    "1. A – Anfahren",
    "2. durch die Bohrung nach X",
    "3. Messer aktivieren",
    "4. an Senkbereich annaehern",
    "5. Schneide greift",
    "6. Rueckwaertssenken bis D / Fertigmaß",
    "7. zurueck nach X",
    "8. Messer schliessen / Spindel stoppen",
    "9. zurueck nach A / aus Werkstueck",
]


class BSFProcessAnimator:
    def __init__(self, canvas: tk.Canvas, step_var: tk.StringVar, *, on_redraw: Callable[[int], None]) -> None:
        self.canvas = canvas
        self.step_var = step_var
        self.on_redraw = on_redraw
        self.step_index = 0
        self.playing = False
        self._after_id = None
        self._update()

    def close(self) -> None:
        self.playing = False
        if self._after_id is not None:
            try:
                self.canvas.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

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
        self._after_id = self.canvas.after(850, self._tick)

    def _update(self) -> None:
        self.step_var.set(PROCESS_STEPS[self.step_index])
        self.on_redraw(self.step_index)
