"""Card values, Hi-Lo tags and bubble parsing.

The engine never deals with suits. A card is just its blackjack value:
1 (ace) through 10 (10/J/Q/K). That is all the bubble can tell us, and
all Hi-Lo and basic strategy need.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ACE = 1
TEN = 10
CARD_VALUES = tuple(range(1, 11))  # 1 = ace, 10 = any ten-value card

_NAMES = {1: "A", 10: "T"}


def card_name(value: int) -> str:
    return _NAMES.get(value, str(value))


def parse_card(text: str | int) -> int:
    """'A', 'K', '10', 7 -> card value 1..10. Raises ValueError otherwise."""
    if isinstance(text, int):
        if text in CARD_VALUES:
            return text
        if text == 11:
            return ACE
        raise ValueError(f"not a card value: {text}")
    t = str(text).strip().upper()
    if t in ("A", "ACE", "1", "11"):
        return ACE
    if t in ("T", "10", "J", "Q", "K", "10/J/Q/K"):
        return TEN
    if t.isdigit() and 2 <= int(t) <= 9:
        return int(t)
    raise ValueError(f"not a card: {text!r}")


def hilo(value: int) -> int:
    """Hi-Lo tag: 2-6 = +1, 7-9 = 0, tens and aces = -1."""
    if 2 <= value <= 6:
        return 1
    if value in (ACE, TEN):
        return -1
    return 0


@dataclass(frozen=True)
class Bubble:
    """What a total bubble says.

    kind:  'total' | 'bj' | 'bust'
    low:   hard total with every ace counted as 1 (None for bj/bust)
    soft:  True when the bubble showed two totals, e.g. '6/16'
    """
    kind: str
    low: int | None = None
    soft: bool = False

    @property
    def best(self) -> int | None:
        if self.kind == "bj":
            return 21
        if self.low is None:
            return None
        return self.low + 10 if self.soft else self.low

    def __str__(self) -> str:
        if self.kind == "bj":
            return "BJ"
        if self.kind == "bust":
            return "BUST"
        return f"{self.low}/{self.low + 10}" if self.soft else str(self.low)


_SOFT = re.compile(r"^(\d{1,2})\s*/\s*(\d{1,2})$")


def parse_bubble(text: str | None) -> Bubble | None:
    """Parse a bubble string read by Recognition.

    Returns None when the text is missing or is not something a bubble can
    show, so the caller treats it as 'unreadable' rather than guessing.
    """
    if text is None:
        return None
    t = str(text).strip().upper().replace(" ", "")
    if not t:
        return None
    if t in ("BJ", "BLACKJACK"):
        return Bubble("bj")
    if t in ("BUST", "BUSTED"):
        return Bubble("bust")
    m = _SOFT.match(t)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if hi - lo != 10 or not (1 <= lo <= 11) or hi > 21:
            return None
        return Bubble("total", lo, True)
    if t.isdigit():
        v = int(t)
        if 2 <= v <= 21:
            return Bubble("total", v, False)
        if v == 1:  # some tables show a lone ace as '1'
            return Bubble("total", 1, True)
    return None
