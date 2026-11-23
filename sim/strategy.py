"""Basic strategy (8 decks, dealer stands on soft 17, no double after split) for the other seats.

This is only for the computer players at the table. The project's Engine has its own tables.
"""
from __future__ import annotations

from sim.cards import Card
from sim.hand import Hand


def basic_strategy(hand: Hand, upcard: Card, can_double: bool = True, can_split: bool = True) -> str:
    up = 11 if upcard.rank == "A" else upcard.value
    if can_split and hand.is_pair:
        move = _pair(hand.cards[0].value, up)
        if move == "split":
            return "split"
    if hand.is_soft and len(hand.cards) >= 2:
        move = _soft(hand.total, up)
    else:
        move = _hard(hand.total, up)
    if move == "double" and not can_double:
        return "stand" if hand.is_soft and hand.total == 18 else "hit"
    if move == "double" and len(hand.cards) != 2:
        return "stand" if hand.is_soft and hand.total == 18 else "hit"
    return move


def _pair(v: int, up: int) -> str:
    if v in (1, 8):
        return "split"
    if v == 9:
        return "split" if up in (2, 3, 4, 5, 6, 8, 9) else "no"
    if v == 7:
        return "split" if 2 <= up <= 7 else "no"
    if v == 6:
        return "split" if 3 <= up <= 6 else "no"
    if v in (2, 3):
        return "split" if 4 <= up <= 7 else "no"
    return "no"


def _soft(total: int, up: int) -> str:
    if total >= 19:
        return "stand"
    if total == 18:
        if 3 <= up <= 6:
            return "double"
        return "stand" if up in (2, 7, 8) else "hit"
    if total == 17:
        return "double" if 3 <= up <= 6 else "hit"
    if total in (15, 16):
        return "double" if 4 <= up <= 6 else "hit"
    if total in (13, 14):
        return "double" if 5 <= up <= 6 else "hit"
    return "hit"


def _hard(total: int, up: int) -> str:
    if total >= 17:
        return "stand"
    if 13 <= total <= 16:
        return "stand" if 2 <= up <= 6 else "hit"
    if total == 12:
        return "stand" if 4 <= up <= 6 else "hit"
    if total == 11:
        return "double" if up != 11 else "hit"
    if total == 10:
        return "double" if up <= 9 else "hit"
    if total == 9:
        return "double" if 3 <= up <= 6 else "hit"
    return "hit"
