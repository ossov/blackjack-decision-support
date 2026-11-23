"""Table rules, legal moves, the dealer's rule and settling a hand."""
from __future__ import annotations

from dataclasses import dataclass

from sim.hand import Hand


@dataclass
class Rules:
    decks: int = 8
    penetration: float = 0.5
    dealer_hits_soft_17: bool = False
    blackjack_pays: float = 1.5
    double_after_split: bool = False
    max_splits: int = 1
    split_aces_one_card: bool = True
    insurance_pays: float = 2.0
    dealer_peeks: bool = True          # checks the face-down card for blackjack...
    peek_on_ten: bool = False          # ...only when showing an ace (confirmed on the live table)
    min_bet: float = 10
    max_bet: float = 5000
    seats: int = 7
    bet_seconds: float = 15
    decision_seconds: float = 10
    insurance_seconds: float = 8


def legal_moves(hand: Hand, rules: Rules, splits_used: int) -> list[str]:
    if hand.finished or hand.is_bust or hand.total >= 21:
        return []
    moves = ["hit", "stand"]
    if len(hand.cards) == 2 and (not hand.from_split or rules.double_after_split):
        moves.append("double")
    if hand.is_pair and splits_used < rules.max_splits:
        moves.append("split")
    return moves


def dealer_should_hit(hand: Hand, rules: Rules) -> bool:
    if hand.total < 17:
        return True
    return hand.total == 17 and hand.is_soft and rules.dealer_hits_soft_17


def settle(hand: Hand, dealer: Hand, rules: Rules) -> float:
    """Net win (+) or loss (-) for a hand, already counting a doubled bet."""
    stake = hand.bet * (2 if hand.doubled else 1)
    if hand.is_bust:
        return -stake
    if hand.is_blackjack and not dealer.is_blackjack:
        return hand.bet * rules.blackjack_pays
    if dealer.is_blackjack:
        return 0 if hand.is_blackjack else -stake
    if dealer.is_bust or hand.total > dealer.total:
        return stake
    if hand.total == dealer.total:
        return 0
    return -stake
