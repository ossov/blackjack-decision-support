"""Which moves are allowed right now."""
from __future__ import annotations

from .hands import HandState
from .rules import TableRules
from .strategy import Move


def legal_moves(hand: HandState, splits_done: int, rules: TableRules) -> list[Move]:
    """Moves allowed for this hand, in H S D P order.

    splits_done: how many times this seat has already split this round.
    """
    if hand.finished or hand.n_cards < 2:
        return []
    moves = [Move.HIT, Move.STAND]
    if hand.n_cards == 2 and not hand.doubled and _double_ok(hand, rules):
        moves.append(Move.DOUBLE)
    if hand.pair_value is not None and splits_done < rules.max_splits:
        moves.append(Move.SPLIT)
    return moves


def _double_ok(hand: HandState, rules: TableRules) -> bool:
    if hand.from_split and not rules.double_after_split:
        return False
    if rules.double_on == "any2":
        return True
    if hand.low is None or hand.soft:
        return False
    allowed = range(9, 12) if rules.double_on == "9-11" else range(10, 12)
    return hand.low in allowed


def why_illegal(move: Move, hand: HandState, splits_done: int,
                rules: TableRules) -> str:
    """Plain reason a move isn't allowed (for the App / log)."""
    if hand.finished:
        return "this hand is already finished"
    if hand.n_cards < 2:
        return "the hand needs two cards first"
    if move == Move.DOUBLE:
        if hand.n_cards != 2:
            return f"no double on {hand.n_cards} cards"
        if hand.from_split and not rules.double_after_split:
            return "no double after a split at this table"
        return "double is not allowed on this total"
    if move == Move.SPLIT:
        if hand.n_cards != 2:
            return f"no split on {hand.n_cards} cards"
        if splits_done >= rules.max_splits:
            return "no more splits allowed"
        if hand.uncertain:
            return "can't confirm the pair: a card is uncertain"
        return "no split on a non-pair"
    return "move not allowed"
