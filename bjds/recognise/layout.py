"""Where things are on screen, from the layout file shared with the simulator.

Layout positions are in "layout units" (the 1920x1080 table crop measured from the team's
recording). A captured frame is the whole 16:9 video picture; `to_frame` converts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[2] / "config" / "layout_sim.json"
FRAME = (1920, 1080)


@dataclass
class Layout:
    data: dict
    frame: tuple[int, int] = FRAME

    @classmethod
    def load(cls, path: str | Path = DEFAULT, frame: tuple[int, int] = FRAME) -> "Layout":
        return cls(json.loads(Path(path).read_text()), frame)

    @property
    def origin(self) -> tuple[float, float]:
        return tuple(self.data["video"]["origin"])

    @property
    def k(self) -> float:
        """Frame pixels per layout unit."""
        return self.frame[1] / self.data["video"]["size"][1]

    def to_frame(self, x: float, y: float) -> tuple[float, float]:
        ox, oy = self.origin
        return (x - ox) * self.k, (y - oy) * self.k

    def bubble_spots(self) -> dict[int, tuple[float, float]]:
        """Expected bubble centre per seat in frame pixels; seat 0 is the dealer."""
        spots = {int(n): self.to_frame(*s["bubble"]) for n, s in self.data["seats"].items()}
        spots[0] = self.to_frame(*self.data["dealer"]["bubble"])
        return spots

    @property
    def split_offset(self) -> float:
        return self.data.get("split_offset", 70) * self.k

    @property
    def active_lift(self) -> float:
        """How much higher the bubble of the hand being played sits."""
        return self.data.get("active_bubble_lift", 0) * self.k

    @property
    def bubble_height(self) -> float:
        return 41 * self.k
