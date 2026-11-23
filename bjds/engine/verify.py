"""Real table only: check the next cards to confirm the player made the move
they said they made."""
from __future__ import annotations

from dataclasses import dataclass

from .strategy import Move


@dataclass
class PendingCheck:
    hand_id: str
    seat: int
    move: Move
    n_cards: int
    seat_hands: int
    dealer_cards: int
    bet: float | None

    def check(self, engine) -> dict | None:
        """Returns {'status': 'confirmed'|'mismatch', ...} or None (still waiting)."""
        hand = engine.hands.get(self.hand_id)
        if hand is None:
            return None
        added = hand.n_cards - self.n_cards
        new_hands = engine.seat_hand_count(self.seat) - self.seat_hands
        dealer_acted = engine.dealer.n_cards > self.dealer_cards
        stage = engine.stage
        m = self.move

        def out(status, why):
            return {"status": status, "hand_id": self.hand_id,
                    "said": m.value, "detail": why}

        if m == Move.SPLIT:
            if new_hands > 0:
                return out("confirmed", "a second hand appeared")
            if added > 0:
                return out("mismatch", "a card was dealt but no split appeared")
            return None
        if new_hands > 0:
            return out("mismatch", "the hand was split")
        if m in (Move.HIT, Move.DOUBLE):
            if added >= 1:
                if hand.bet is not None and self.bet:
                    doubled = hand.bet >= 1.9 * self.bet
                    if m == Move.DOUBLE and not doubled:
                        return out("mismatch", "one card dealt but the bet did not double (looks like hit)")
                    if m == Move.HIT and doubled:
                        return out("mismatch", "the bet doubled (looks like double)")
                return out("confirmed", "one card dealt to the hand")
            if dealer_acted or stage in ("dealer_turn", "round_over"):
                return out("mismatch", "no card dealt to the hand (looks like stand)")
            return None
        # stand
        if added > 0:
            return out("mismatch", "a card was dealt to the hand (looks like hit)")
        if dealer_acted or stage in ("dealer_turn", "round_over") or (
                engine.active_hand_id and engine.active_hand_id != self.hand_id):
            return out("confirmed", "play moved on without a card")
        return None
