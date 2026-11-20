"""Hi-Lo running count and true count."""
from __future__ import annotations

import math

from .cards import hilo


class HiLoCounter:
    def __init__(self, decks: int, tray_height_per_deck: float = 1.0,
                 decks_left_step: float = 0.5):
        self.decks = decks
        self.tray_height_per_deck = tray_height_per_deck
        self.step = decks_left_step
        self.reset()

    def reset(self) -> None:
        """New shoe: everything back to zero."""
        self.running = 0
        self.cards_seen = 0
        self.tray_height: float | None = None
        self.cards_on_table = 0  # seen this round, not yet in the tray

    def add(self, value: int) -> None:
        self.running += hilo(value)
        self.cards_seen += 1
        self.cards_on_table += 1

    def new_round(self) -> None:
        # Last round's cards are now in the discard tray.
        self.cards_on_table = 0

    def set_tray_height(self, height: float | None) -> None:
        if height is not None and height >= 0:
            self.tray_height = height

    def decks_left(self) -> float:
        """Decks still in the shoe.

        From the discard tray height when Recognition reports it, otherwise
        from the cards the engine has seen. Cards still on the table this
        round are taken off too, then rounded to the nearest half deck.
        """
        if self.tray_height is not None:
            played = self.tray_height / self.tray_height_per_deck
            played += self.cards_on_table / 52
        else:
            played = self.cards_seen / 52
        left = self.decks - played
        if self.step:
            left = round(left / self.step) * self.step
        return max(left, self.step or 0.5)

    def true_count(self) -> float:
        return self.running / self.decks_left()

    def true_count_floor(self) -> int:
        return math.floor(self.true_count())
