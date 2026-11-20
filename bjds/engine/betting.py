"""Bet size from the true count and the bankroll.

Uses a fraction of the Kelly bet: the player's edge rises about 0.5% per
true count from roughly -0.5% at 0, and Kelly bets edge / variance of the
bankroll. Below a positive edge the table minimum is bet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .rules import EngineSettings
from .strategy import format_count


@dataclass
class BetAdvice:
    amount: float
    true_count: float
    edge: float
    reason: str

    def to_dict(self) -> dict:
        return {"amount": self.amount, "true_count": round(self.true_count, 2),
                "edge": round(self.edge, 4), "reason": self.reason}


def recommend_bet(true_count: float, bankroll: float,
                  s: EngineSettings) -> BetAdvice:
    r = s.rules
    tc = math.floor(true_count)
    edge = s.base_edge + s.edge_per_true_count * tc
    if bankroll < r.min_bet:
        return BetAdvice(0.0, true_count, edge,
                         f"bankroll ${bankroll:.2f} is below the ${r.min_bet:g} table minimum")
    if edge <= 0:
        amount = r.min_bet
        why = "no edge, bet the table minimum"
    else:
        amount = bankroll * s.kelly_fraction * edge / s.variance
        amount = math.floor(amount / r.chip_size) * r.chip_size
        amount = max(r.min_bet, min(amount, r.max_bet, bankroll))
        why = f"edge about {edge * 100:.1f}%"
    return BetAdvice(amount, true_count, edge,
                     f"bet ${amount:g}, count is {format_count(true_count)}, {why}")
