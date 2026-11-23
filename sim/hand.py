"""A blackjack hand and the text its total bubble shows."""
from __future__ import annotations

from dataclasses import dataclass, field

from sim.cards import Card


@dataclass
class Hand:
    cards: list[Card] = field(default_factory=list)
    bet: float = 0
    from_split: bool = False
    doubled: bool = False
    finished: bool = False
    result: str | None = None  # "win", "lose", "push", "blackjack" once settled

    @property
    def hard_total(self) -> int:
        return sum(c.value for c in self.cards)

    @property
    def is_soft(self) -> bool:
        return any(c.rank == "A" for c in self.cards) and self.hard_total + 10 <= 21

    @property
    def total(self) -> int:
        return self.hard_total + 10 if self.is_soft else self.hard_total

    @property
    def is_blackjack(self) -> bool:
        return len(self.cards) == 2 and self.total == 21 and not self.from_split

    @property
    def is_bust(self) -> bool:
        return self.hard_total > 21

    @property
    def is_pair(self) -> bool:
        return len(self.cards) == 2 and self.cards[0].value == self.cards[1].value


def bubble_text(hand: Hand, finished: bool = False, active: bool = False) -> str:
    """What the on-screen bubble beside a hand shows. A soft total shows both values until
    the hand is finished and the turn has moved on."""
    if not hand.cards:
        return ""
    if hand.is_blackjack:
        return "BJ"
    if hand.is_bust:
        return str(hand.hard_total)      # shown in a red bubble on the live table
    if hand.is_soft and hand.total != 21 and (active or not (finished or hand.finished)):
        return f"{hand.hard_total}/{hand.total}"
    return str(hand.total)
