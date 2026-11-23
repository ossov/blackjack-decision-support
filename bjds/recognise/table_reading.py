"""Turn the bubbles found in a frame into the table reading the Engine takes.

Format: contracts/table_reading.example.json. A bubble's text is passed on only once it has been
read the same in two frames in a row, so a half-drawn or misread frame never reaches the Engine.
"""
from __future__ import annotations

import time

from bjds.recognise.bubbles import Bubble


def hand_id(seat: int, hand: int) -> str:
    return f"seat{seat}" + ("b" * hand)


class TableReader:
    def __init__(self, confirm_frames: int = 2):
        self.confirm = confirm_frames
        self._last: dict[tuple[int, int], tuple[str | None, int]] = {}   # key -> (text, times seen)
        self._trusted: dict[tuple[int, int], str | None] = {}

    def _steady(self, key: tuple[int, int], text: str | None) -> tuple[str | None, bool]:
        """(value to pass on, whether this hand has ever been read)."""
        prev, n = self._last.get(key, (None, 0))
        n = n + 1 if text == prev else 1
        self._last[key] = (text, n)
        if text is not None and n >= self.confirm:
            self._trusted[key] = text
        trusted = self._trusted.get(key)
        # while a value is changing, the old one is out of date: pass on "not known yet"
        return (trusted if trusted == text else None), key in self._trusted

    def reading(self, bubbles: list[Bubble]) -> dict:
        seen = {(b.seat, b.hand) for b in bubbles}
        for key in list(self._last):                  # a bubble that vanished starts afresh
            if key not in seen:
                self._last.pop(key, None)
                self._trusted.pop(key, None)
        hands, dealer, active = [], {"bubble": None, "new_cards": []}, None
        for b in sorted(bubbles, key=lambda b: (b.seat, b.hand)):
            text, ever_read = self._steady((b.seat, b.hand), b.text)
            if b.kind == "active":     # which hand is being played, even before its value is confirmed
                active = hand_id(b.seat, b.hand)
            if not ever_read:          # never read yet: not reported, so a stray blob is not a hand
                continue
            if b.seat == 0:
                dealer = {"bubble": text, "new_cards": []}
                continue
            entry = {"hand_id": hand_id(b.seat, b.hand), "seat": b.seat, "bubble": text, "new_cards": []}
            if b.hand:
                entry["split_of"] = hand_id(b.seat, b.hand - 1)
            hands.append(entry)
        stage = "betting" if not bubbles else ("player_turn" if active else "dealing")
        return {"stage": stage, "active_hand": active, "hands": hands, "dealer": dealer,
                "discard_tray_height": None, "cut_card_out": False, "timestamp": round(time.time(), 2)}
