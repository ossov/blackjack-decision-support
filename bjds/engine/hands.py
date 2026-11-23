"""Hand tracking and card inference from bubble totals.

Rule from the spec: new card = new bubble total - old bubble total, with
every ace counted as 1. Card pictures (once Recognition has them) are used
when the bubble can't settle it: BUST, BJ, or two cards landing at once.
When nothing gives a valid card, the card is marked uncertain (None) -
the engine never guesses.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .cards import ACE, TEN, Bubble, card_name


@dataclass
class Inference:
    cards: list[int | None]      # new cards; None = uncertain
    source: str                  # 'bubble' | 'picture' | 'rule' | 'none'
    note: str = ""
    accept_bubble: bool = True   # False: keep the old bubble (misread)


@dataclass
class HandState:
    hand_id: str
    seat: int | None = None          # None for the dealer
    cards: list[int | None] = field(default_factory=list)
    low: int | None = 0              # hard total, aces = 1 (None if unknown)
    soft: bool = False               # an ace that can still count 11
    bubble: Bubble | None = None
    from_split: bool = False
    split_aces: bool = False
    doubled: bool = False
    stood: bool = False
    bet: float | None = None

    @property
    def n_cards(self) -> int:
        return len(self.cards)

    @property
    def best(self) -> int | None:
        if self.bubble is not None and self.bubble.kind == "bj":
            return 21
        if self.low is None:
            return None
        return self.low + 10 if self.soft and self.low + 10 <= 21 else self.low

    @property
    def busted(self) -> bool:
        return (self.bubble is not None and self.bubble.kind == "bust") or (
            self.low is not None and self.low > 21)

    @property
    def blackjack(self) -> bool:
        return self.bubble is not None and self.bubble.kind == "bj"

    @property
    def finished(self) -> bool:
        if self.stood or self.busted or self.blackjack:
            return True
        if self.doubled and self.n_cards >= 3:
            return True
        if self.split_aces and self.n_cards >= 2:
            return True
        return self.best is not None and self.best >= 21

    @property
    def pair_value(self) -> int | None:
        if self.n_cards == 2 and self.cards[0] is not None \
                and self.cards[0] == self.cards[1]:
            return self.cards[0]
        return None

    @property
    def uncertain(self) -> int:
        return sum(c is None for c in self.cards)

    def to_dict(self) -> dict:
        return {
            "hand_id": self.hand_id, "seat": self.seat,
            "cards": [card_name(c) if c else "?" for c in self.cards],
            "total": str(self.bubble) if self.bubble else None,
            "best": self.best, "finished": self.finished,
            "doubled": self.doubled, "from_split": self.from_split,
        }

    # ------------------------------------------------------------------
    def apply(self, bubble: Bubble | None, pictures: list[int]) -> Inference:
        """Update the hand from a new bubble (and any card pictures)."""
        # A lone ace may be shown as '11' instead of '1/11'.
        if (bubble is not None and bubble.kind == "total" and not bubble.soft
                and bubble.low == 11 and (self.n_cards == 0 or self.cards == [ACE])):
            bubble = Bubble("total", 1, True)
        # Soft 21 is shown as plain '21' (not '11/21'). Read it as soft when
        # hard 21 can't be one card but soft 21 can (needs an ace in hand
        # or the new card being the ace).
        if (bubble is not None and bubble.kind == "total" and not bubble.soft
                and bubble.low == 21 and self.low is not None and self.n_cards > 0):
            d_soft = 11 - self.low
            if self.soft and self.low == 11:      # same soft 21 as before
                bubble = Bubble("total", 11, True)
            elif 21 - self.low > 10 and 1 <= d_soft <= 10 and (self.soft or d_soft == 1):
                bubble = Bubble("total", 11, True)
        inf = infer_new_cards(self, bubble, pictures)
        if not inf.cards and (bubble is None or bubble == self.bubble):
            return inf
        if not inf.accept_bubble:
            if not inf.cards:
                return inf
            bubble = None  # bubble misread: keep old total, add the picture cards
        self.cards.extend(inf.cards)
        if bubble is not None:
            self.bubble = bubble
            if bubble.kind == "total":
                self.low, self.soft = bubble.low, bubble.soft
            elif bubble.kind == "bj":
                self.low, self.soft = 11, True
            else:  # bust: the shown total, or the sum of the cards if they are all known
                known = all(c is not None for c in self.cards)
                self.low = bubble.low if bubble.low is not None else (sum(self.cards) if known else None)
                self.soft = False
        else:  # unreadable bubble, cards came from pictures
            if self.low is not None and all(c is not None for c in inf.cards):
                self.low += sum(inf.cards)
                self.soft = self.soft or ACE in inf.cards
                if self.soft and self.low + 10 > 21:
                    self.soft = False
            else:
                self.low = None
        return inf

    def split_off(self, new_id: str) -> "HandState":
        """Split this two-card hand; returns the new second hand."""
        first, second = self.cards[0], self.cards[1]
        child = HandState(new_id, self.seat, [second], from_split=True,
                          bet=self.bet)
        for h, c in ((self, first), (child, second)):
            h.cards = [c]
            h.from_split = True
            h.low = c
            h.soft = c == ACE
            h.split_aces = c == ACE
            h.bubble = None if c is None else Bubble("total", c, c == ACE)
        return child


def infer_new_cards(hand: HandState, new: Bubble | None,
                    pictures: list[int]) -> Inference:
    old_low = hand.low
    pictures = list(pictures or [])

    # 1. Bubble unreadable: only pictures can tell us anything.
    if new is None:
        if pictures:
            return Inference(pictures, "picture", "bubble unreadable, used card pictures")
        return Inference([], "none")

    if new == hand.bubble and not pictures:
        return Inference([], "none")

    # Baseline unknown (earlier uncertain cards): accept the bubble as is.
    if old_low is None:
        if pictures:
            return Inference(pictures, "picture", "hand total was unknown")
        return Inference([], "none", "hand total was unknown; bubble taken as new baseline")

    # 2. Blackjack: the second of two cards.
    if new.kind == "bj":
        missing = 2 - hand.n_cards
        if missing <= 0:
            return Inference([], "none", "BJ shown on a hand that already had 2+ cards",
                             accept_bubble=False)
        if pictures and len(pictures) == missing and _is_bj(hand.cards + pictures):
            return Inference(pictures, "picture", "BJ, card read from picture")
        if missing == 1 and hand.cards[0] in (ACE, TEN):
            other = TEN if hand.cards[0] == ACE else ACE
            return Inference([other], "rule", "BJ: the other card must complete 21")
        return Inference([None] * missing, "none", "BJ but the card can't be worked out")

    # 3. Bust: the card must take the hard total past 21.
    if new.kind == "bust" and new.low is not None:     # the total is shown: the card is exact
        delta = new.low - old_low
        if 1 <= delta <= 10 and new.low > 21:
            if pictures and (len(pictures) != 1 or pictures[0] != delta):
                return Inference([delta], "bubble", f"bust total says {card_name(delta)}; "
                                 f"pictures {[card_name(p) for p in pictures]} disagree")
            return Inference([delta], "bubble", "")
        return Inference([None], "none", f"bust total {new.low} does not fit old total {old_low}")
    if new.kind == "bust":
        possible = [v for v in range(1, 11) if old_low + v > 21]
        if pictures:
            if len(pictures) == 1 and pictures[0] in possible:
                return Inference(pictures, "picture", "BUST, card read from picture")
            if len(pictures) > 1:
                return Inference(pictures, "picture", "BUST, several cards from pictures")
            return Inference([None], "none",
                             f"BUST but picture {card_name(pictures[0])} can't bust {old_low}")
        if len(possible) == 1:
            return Inference(possible, "rule",
                             f"BUST from {old_low}: only {card_name(possible[0])} busts it")
        return Inference([None], "none",
                         f"BUST from {old_low}: could be any of "
                         + ", ".join(card_name(v) for v in possible))

    # 4. Normal total: new minus old.
    delta = new.low - old_low
    if delta <= 0:
        if pictures:
            return Inference(pictures, "picture",
                             f"bubble {new} does not fit old total {old_low}; used card pictures",
                             accept_bubble=False)
        return Inference([], "none", f"bubble {new} is not above old total {old_low}; ignored",
                         accept_bubble=False)

    conflict = ""
    if pictures:
        if sum(pictures) == delta:
            src = "bubble" if len(pictures) == 1 else "picture"
            return Inference(pictures, src)
        # The bubble comes first; the pictures are only a backup.
        conflict = (f"pictures {[card_name(p) for p in pictures]} don't add up to "
                    f"+{delta}; used the bubble")

    if delta > 10:
        return Inference([None, None], "none",
                         f"total went up by {delta}: two or more cards landed at once")
    became_soft = new.soft and not hand.soft
    if became_soft and delta != 1:
        return Inference([None, None], "none",
                         f"hand turned soft but went up by {delta}: more than one card")
    if delta == 1 and not new.soft and new.low + 10 <= 21:
        return Inference([None], "none", "total went up by 1 but the bubble isn't soft")
    return Inference([delta], "bubble", conflict)


def _is_bj(cards: list[int | None]) -> bool:
    return len(cards) == 2 and sorted(c or 0 for c in cards) == [ACE, TEN]
