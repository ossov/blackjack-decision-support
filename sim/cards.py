"""Cards, the 8-deck shoe and the Hi-Lo count value of each card."""
from __future__ import annotations

import random
from dataclasses import dataclass

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["S", "H", "D", "C"]


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    @property
    def value(self) -> int:
        """Blackjack value with an ace counted as 1."""
        if self.rank == "A":
            return 1
        if self.rank in ("10", "J", "Q", "K"):
            return 10
        return int(self.rank)

    @property
    def label(self) -> str:
        """The card-value class used by the card detector: 2-9, 10 (10/J/Q/K) or A."""
        return "A" if self.rank == "A" else str(self.value)

    def to_dict(self) -> dict:
        return {"rank": self.rank, "suit": self.suit}


def hilo(card: Card) -> int:
    v = card.value
    if 2 <= v <= 6:
        return 1
    if v in (1, 10):
        return -1
    return 0


class Shoe:
    """A shuffled shoe with a cut card. The same seed always gives the same shoe."""

    def __init__(self, seed: int = 0, decks: int = 8, penetration: float = 0.5):
        self.seed = seed
        self.decks = decks
        self.penetration = penetration
        self.cards = [Card(r, s) for _ in range(decks) for s in SUITS for r in RANKS]
        random.Random(seed).shuffle(self.cards)
        self.position = 0
        self.cut_index = round(len(self.cards) * penetration)

    @classmethod
    def stacked(cls, ranks: list[str], suit: str = "S") -> "Shoe":
        """A shoe that deals exactly these ranks in order (for tests and scripted demos)."""
        shoe = cls.__new__(cls)
        shoe.seed = None
        shoe.decks = 0
        shoe.penetration = 1.0
        shoe.cards = [Card(r, suit) for r in ranks]
        shoe.position = 0
        shoe.cut_index = len(shoe.cards) + 1
        return shoe

    def draw(self) -> Card:
        if self.position >= len(self.cards):
            raise RuntimeError("the shoe is empty")
        card = self.cards[self.position]
        self.position += 1
        return card

    @property
    def cut_card_out(self) -> bool:
        return self.position >= self.cut_index

    @property
    def remaining(self) -> int:
        return len(self.cards) - self.position

    def reshuffled(self) -> "Shoe":
        """A new shoe for the next shuffle, still reproducible from the first seed."""
        if self.seed is None:
            return self
        return Shoe(seed=self.seed * 1000 + 1, decks=self.decks, penetration=self.penetration)
