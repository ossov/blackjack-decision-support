"""The table: betting, dealing, insurance, each seat's turn, the dealer and settling.

The game runs as a generator that yields a Wait after every visible action. The server calls
tick() as time passes and step() to move on; tests call run_until(), which skips the waits.
Seat 1 is first base (the dealer's left, the viewer's right) and acts first.
"""
from __future__ import annotations

import json
import random
import time
from collections import Counter
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

from sim.cards import Card, Shoe, hilo
from sim.hand import Hand, bubble_text
from sim.rules import Rules, dealer_should_hit, legal_moves, settle
from sim.strategy import basic_strategy

CHIPS = [1000, 200, 50, 20, 10, 5, 2.5, 1]
DEAL_DELAY = 0.8
OTHER_DECISION_DELAY = 1.4
DEALER_DELAY = 1.0
ROUND_OVER_DELAY = 4.0
SPLIT_PAUSE = 1.5
SHUFFLE_DELAY = 6.0


@dataclass
class Wait:
    kind: str  # "delay", "betting", "decision", "insurance"
    remaining: float
    resolved: bool = False


@dataclass
class Seat:
    number: int
    name: str = ""
    occupied: bool = False
    is_player: bool = False
    bet: float = 0
    hands: list[Hand] = field(default_factory=list)
    insurance: float = 0
    splits_used: int = 0
    side_bets: dict = field(default_factory=dict)


class History:
    """The simulator history: one JSON object per line (JSON Lines)."""

    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **data) -> None:
        if not self.path:
            return
        record = {"event": event, "time": round(time.time(), 3), **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


class Table:
    def __init__(self, shoe: Shoe | None = None, seed: int = 0, rules: Rules | None = None,
                 player_seat: int = 4, balance: float = 1000, other_players: bool = True,
                 auto_bet: float | None = None, auto_play: bool = False,
                 history_path: str | Path | None = None, **rule_overrides):
        self.rules = rules or Rules()
        for key, value in rule_overrides.items():
            if not hasattr(self.rules, key):
                raise TypeError(f"unknown rule {key!r}")
            setattr(self.rules, key, value)
        self.shoe = shoe or Shoe(seed=seed, decks=self.rules.decks, penetration=self.rules.penetration)
        self.rng = random.Random((self.shoe.seed or 0) + 7919)
        self.player_seat = player_seat
        self.balance = balance
        self.other_players = other_players
        self.auto_bet = auto_bet
        self.auto_play = auto_play
        self.seats = [Seat(n) for n in range(1, self.rules.seats + 1)]
        me = self.seats[player_seat - 1]
        me.occupied, me.is_player, me.name = True, True, "You"
        self.dealer = Hand()
        self.hole_hidden = True
        self.discard_count = 0
        self.round_no = 0
        self.phase = "starting"
        self.active: tuple[int, int] | None = None
        self.message = ""
        self.wait: Wait | None = None
        self.history = History(history_path)
        self.history_path = Path(history_path) if history_path else None
        self.start_balance = balance
        self.shoe_no = 1
        self._new_count()
        self.history.write("session_start", seed=self.shoe.seed, player_seat=player_seat,
                           balance=balance, rules=self.rules.__dict__)
        self._gen = self._game()
        self._resume()

    # ----- driving the game -------------------------------------------------------------

    def tick(self, dt: float) -> None:
        if self.wait is not None:
            self.wait.remaining -= dt

    def step(self, force: bool = False) -> bool:
        """Move the game on if it is not waiting for anyone. Returns False if nothing happened."""
        w = self.wait
        if w is None:
            self._resume()
            return True
        if w.kind in ("decision", "insurance") and not w.resolved:
            if w.remaining > 0:
                return False
            self._timeout(w)
        elif not (w.resolved or force or w.remaining <= 0):
            return False
        self._resume()
        return True

    def run_until(self, *phases: str, max_steps: int = 100000) -> str:
        for _ in range(max_steps):
            if self.phase in phases:
                return self.phase
            if not self.step(force=True):
                raise RuntimeError(f"waiting for the player during {self.phase!r}")
        raise RuntimeError("run_until did not finish")

    def _resume(self) -> None:
        self.wait = next(self._gen)

    def _timeout(self, w: Wait) -> None:
        if w.kind == "decision" and self.active:
            seat_no, idx = self.active
            self._apply(self.seats[seat_no - 1], idx, "stand", source="timer")
        elif w.kind == "insurance":
            self.history.write("insurance", round=self.round_no, seat=self.player_seat,
                               take=False, source="timer")
        w.resolved = True

    # ----- actions from the page's buttons or the Engine --------------------------------

    def act(self, action: str, source: str = "button", **kw) -> None:
        me = self.seats[self.player_seat - 1]
        w = self.wait
        if action in ("bet", "undo", "clear", "double_bet", "deal"):
            if self.phase != "betting" or w is None or w.kind != "betting" or w.resolved:
                raise ValueError("betting is closed")
            if action == "bet":
                amount = float(kw.get("amount", 0))
                if amount <= 0 or amount > self.balance or me.bet + amount > self.rules.max_bet:
                    raise ValueError("bet not allowed")
                me.bet += amount
                self.balance -= amount
                me.side_bets.setdefault("_chips", []).append(amount)
            elif action == "undo":
                chips = me.side_bets.get("_chips", [])
                if chips:
                    amount = chips.pop()
                    me.bet -= amount
                    self.balance += amount
            elif action == "clear":
                self.balance += me.bet
                me.bet = 0
                me.side_bets["_chips"] = []
            elif action == "double_bet":
                if me.bet == 0 or me.bet > self.balance:
                    raise ValueError("bet not allowed")
                self.balance -= me.bet
                me.side_bets.setdefault("_chips", []).append(me.bet)
                me.bet *= 2
            elif action == "deal":
                if me.bet < self.rules.min_bet:
                    raise ValueError(f"minimum bet is {self.rules.min_bet:g}")
                w.resolved = True
            return
        if action == "insurance":
            if self.phase != "insurance" or w is None or w.kind != "insurance" or w.resolved:
                raise ValueError("insurance is not offered")
            take = bool(kw.get("take"))
            if take:
                me.insurance = me.bet / 2
                self.balance -= me.insurance
            self.history.write("insurance", round=self.round_no, seat=self.player_seat,
                               take=take, source=source)
            w.resolved = True
            return
        if action in ("hit", "stand", "double", "split"):
            if (self.phase != "player_turn" or w is None or w.kind != "decision" or w.resolved
                    or not self.active or self.active[0] != self.player_seat):
                raise ValueError("it is not your turn")
            idx = self.active[1]
            hand = me.hands[idx]
            if action not in legal_moves(hand, self.rules, me.splits_used):
                raise ValueError(f"{action} is not allowed now")
            if action in ("double", "split") and hand.bet > self.balance:
                raise ValueError("not enough balance")
            self._apply(me, idx, action, source)
            if hand.finished:
                w.resolved = True
            else:
                w.remaining = self.rules.decision_seconds
            return
        raise ValueError(f"unknown action {action!r}")

    # ----- the game -----------------------------------------------------------------------

    def _game(self):
        while True:
            yield from self._betting()
            if not any(s.bet > 0 for s in self.seats):
                continue
            yield from self._round()

    def _betting(self):
        # Clear the last round into the discard tray, then shuffle if the cut card came out.
        cards = len(self.dealer.cards) + sum(len(h.cards) for s in self.seats for h in s.hands)
        if cards:
            self.discard_count += cards
        for s in self.seats:
            s.hands, s.bet, s.insurance, s.splits_used = [], 0, 0, 0
            s.side_bets = {}
        self.dealer, self.hole_hidden, self.active = Hand(), True, None
        if self.shoe.cut_card_out:
            self.phase = "shuffle"
            self.message = "SHUFFLING"
            self.write_shoe_report(complete=True)
            self.shoe_no += 1
            self.shoe = self.shoe.reshuffled()
            self._new_count()
            self.discard_count = 0
            self.history.write("shuffle", seed=self.shoe.seed, cut_index=self.shoe.cut_index)
            yield Wait("delay", SHUFFLE_DELAY)
        self.round_no += 1
        self.phase = "betting"
        self.message = "PLACE YOUR BETS"
        self._seat_other_players()
        me = self.seats[self.player_seat - 1]
        if self.auto_bet:
            amount = min(self.auto_bet, self.balance)
            me.bet, self.balance = amount, self.balance - amount
            me.side_bets["_chips"] = [amount]
        w = Wait("betting", self.rules.bet_seconds)
        yield w
        self.message = "BETS CLOSED"
        if 0 < me.bet < self.rules.min_bet:
            self.balance += me.bet
            me.bet = 0
        bets = {s.number: s.bet for s in self.seats if s.bet > 0}
        self.history.write("round_start", round=self.round_no, bets=bets, balance=self.balance,
                           **self._count_fields())
        if bets:
            self._round_entry = {"round": self.round_no, "start_running_count": self.running,
                                 "start_true_count": self.true_count, "player_bet": me.bet,
                                 "seats_playing": len(bets), "balance_before": self.balance + me.bet,
                                 "cards_before": self.cards_seen}

    def _seat_other_players(self) -> None:
        others = [s for s in self.seats if not s.is_player]
        if not self.other_players:
            return
        if self.round_no == 1 or not any(s.occupied for s in others):
            count = self.rng.randint(3, 6)
            for s in self.rng.sample(others, count):
                s.occupied, s.name = True, f"Player{self.rng.randint(1000000, 99999999)}"
        else:  # now and then someone leaves or sits down
            s = self.rng.choice(others)
            if self.rng.random() < 0.15:
                if s.occupied and sum(o.occupied for o in others) > 1:
                    s.occupied, s.name = False, ""
                elif not s.occupied:
                    s.occupied, s.name = True, f"Player{self.rng.randint(1000000, 99999999)}"
        for s in others:
            if s.occupied:
                s.bet = self.rng.choice([10, 10, 20, 25, 30, 50, 100, 135])

    def _round(self):
        playing = [s for s in self.seats if s.bet > 0]
        for s in playing:
            s.hands = [Hand(bet=s.bet)]
        # Two passes: each seat from first base, then the dealer (up card, then hole card).
        self.phase = "dealing"
        self.message = ""
        for pass_no in (0, 1):
            for s in playing:
                self._deal_to(s, 0)
                yield Wait("delay", DEAL_DELAY)
            card = self.shoe.draw()
            self.dealer.cards.append(card)
            self._record_card(card, "dealer", 0, 0, face_up=pass_no == 0)
            yield Wait("delay", DEAL_DELAY)
        for s in playing:
            if s.hands[0].is_blackjack:
                s.hands[0].finished = True

        up = self.dealer.cards[0]
        if up.rank == "A":
            self.phase = "insurance"
            self.message = "INSURANCE?"
            me = self.seats[self.player_seat - 1]
            if me.bet > 0 and not self.auto_play:
                yield Wait("insurance", self.rules.insurance_seconds)
            elif me.bet > 0:
                self.history.write("insurance", round=self.round_no, seat=self.player_seat,
                                   take=False, source="auto")
                yield Wait("delay", DEALER_DELAY)
            self.message = ""
        peek = up.value == 1 or (up.value == 10 and self.rules.peek_on_ten)
        if self.rules.dealer_peeks and peek and self.dealer.is_blackjack:
            self.phase = "dealer_turn"
            yield from self._reveal()
            yield from self._settle(playing)
            return

        self.phase = "player_turn"
        for s in playing:
            i = 0
            while i < len(s.hands):
                hand = s.hands[i]
                self.active = (s.number, i)
                if len(hand.cards) == 1:  # second hand of a split gets its card now
                    yield Wait("delay", SPLIT_PAUSE)  # the dealer moves across to the next hand first
                    self._deal_to(s, i)
                    yield Wait("delay", DEAL_DELAY)
                    if hand.cards[0].rank == "A" and self.rules.split_aces_one_card:
                        hand.finished = True
                while not hand.finished:
                    if not legal_moves(hand, self.rules, s.splits_used):
                        hand.finished = True
                        break
                    if s.is_player and not self.auto_play:
                        yield Wait("decision", self.rules.decision_seconds)
                    else:
                        move = basic_strategy(
                            hand, up,
                            can_double="double" in legal_moves(hand, self.rules, s.splits_used),
                            can_split="split" in legal_moves(hand, self.rules, s.splits_used))
                        if move == "split" and s.is_player and hand.bet > self.balance:
                            move = "hit"
                        yield Wait("delay", OTHER_DECISION_DELAY)
                        self._apply(s, i, move, "auto" if s.is_player else "other_player")
                        yield Wait("delay", DEAL_DELAY if move != "stand" else 0.2)
                i += 1
        self.active = None

        self.phase = "dealer_turn"
        yield from self._reveal()
        live = [h for s in playing for h in s.hands if not h.is_bust and not h.is_blackjack]
        while live and dealer_should_hit(self.dealer, self.rules):
            card = self.shoe.draw()
            self.dealer.cards.append(card)
            self._record_card(card, "dealer", 0, 0, face_up=True)
            yield Wait("delay", DEALER_DELAY)
        yield from self._settle(playing)

    def _reveal(self):
        self.hole_hidden = False
        hole = self.dealer.cards[1]
        self._count(hole, "dealer", 0, 0)
        self.history.write("hole_reveal", round=self.round_no, rank=hole.rank, suit=hole.suit,
                           **self._count_fields())
        yield Wait("delay", DEALER_DELAY)

    def _settle(self, playing):
        self.dealer.finished = True
        for s in playing:
            if s.insurance and self.dealer.is_blackjack and s.is_player:
                self.balance += s.insurance * (1 + self.rules.insurance_pays)
            for i, h in enumerate(s.hands):
                h.finished = True
                net = settle(h, self.dealer, self.rules)
                h.result = ("blackjack" if h.is_blackjack and net > 0 else
                            "win" if net > 0 else "push" if net == 0 else "lose")
                if s.is_player:
                    stake = h.bet * (2 if h.doubled else 1)
                    self.balance += stake + net
                self.history.write("settle", round=self.round_no, seat=s.number, hand=i,
                                   net=net, result=h.result)
        self.history.write("round_end", round=self.round_no, balance=self.balance,
                           dealer_total=self.dealer.total, cut_card_out=self.shoe.cut_card_out,
                           **self._count_fields())
        me = self.seats[self.player_seat - 1]
        entry = getattr(self, "_round_entry", None) or {"round": self.round_no}
        entry.update(end_running_count=self.running, end_true_count=self.true_count,
                     cards_in_round=self.cards_seen - entry.get("cards_before", self.cards_seen),
                     dealer_total="BJ" if self.dealer.is_blackjack else self.dealer.total,
                     player_results=[h.result for h in me.hands],
                     player_net=round(self.balance - entry.get("balance_before", self.balance), 2))
        entry.pop("cards_before", None)
        entry.pop("balance_before", None)
        self.round_log.append(entry)
        self._round_entry = None
        self.phase = "round_over"
        yield Wait("delay", ROUND_OVER_DELAY)

    def _deal_to(self, seat: Seat, idx: int) -> Card:
        card = self.shoe.draw()
        seat.hands[idx].cards.append(card)
        self._record_card(card, "seat", seat.number, idx, face_up=True)
        if self.shoe.cut_card_out and self.shoe.position == self.shoe.cut_index:
            self.history.write("cut_card_out", round=self.round_no, shoe_index=self.shoe.position)
        return card

    def _apply(self, seat: Seat, idx: int, move: str, source: str) -> None:
        hand = seat.hands[idx]
        self.history.write("move", round=self.round_no, seat=seat.number, hand=idx, move=move,
                           source=source)
        if move == "stand":
            hand.finished = True
        elif move == "hit":
            self._deal_to(seat, idx)
            if hand.is_bust or hand.total == 21:
                hand.finished = True
        elif move == "double":
            if seat.is_player:
                self.balance -= hand.bet
            hand.doubled = True
            self._deal_to(seat, idx)
            hand.finished = True
        elif move == "split":
            if seat.is_player:
                self.balance -= hand.bet
            second = Hand([hand.cards.pop()], bet=hand.bet, from_split=True)
            hand.from_split = True
            seat.hands.insert(idx + 1, second)
            seat.splits_used += 1
            self._deal_to(seat, idx)
            if hand.cards[0].rank == "A" and self.rules.split_aces_one_card:
                hand.finished = True
            elif hand.total == 21:
                hand.finished = True

    # ----- the true count (face-up cards only, as a player would see them) ----------------

    def _new_count(self) -> None:
        self.running = 0
        self.cards_seen = 0
        self.rank_counts: Counter = Counter()
        self.last_card: dict | None = None
        self.max_true = self.min_true = 0.0
        self.round_log: list[dict] = []
        self._round_entry = None
        self.shoe_seed = self.shoe.seed
        self.shoe_started = datetime.now().isoformat(timespec="seconds")
        self.shoe_start_balance = self.balance

    @property
    def decks_left(self) -> float:
        return max(self.shoe.remaining, 1) / 52

    @property
    def true_count(self) -> float:
        return round(self.running / self.decks_left, 2)

    def _count(self, card: Card, to: str, seat: int, hand: int) -> None:
        self.running += hilo(card)
        self.cards_seen += 1
        self.rank_counts[card.rank] += 1
        self.last_card = {"rank": card.rank, "suit": card.suit, "to": to, "seat": seat, "hand": hand}
        self.max_true = max(self.max_true, self.true_count)
        self.min_true = min(self.min_true, self.true_count)

    def _count_fields(self) -> dict:
        return {"running_count": self.running, "true_count": self.true_count,
                "decks_left": round(self.decks_left, 2)}

    def _record_card(self, card: Card, to: str, seat: int, hand: int, face_up: bool) -> None:
        if face_up:
            self._count(card, to, seat, hand)
        self.history.write("card", round=self.round_no, to=to, seat=seat, hand=hand,
                           rank=card.rank, suit=card.suit, face_up=face_up,
                           shoe_index=self.shoe.position - 1, **self._count_fields())

    def write_shoe_report(self, complete: bool) -> Path | None:
        """One JSON file per shoe: the counts, the rounds and the player's results."""
        if not self.history_path or (not self.cards_seen and not self.round_log):
            return None
        expected = sum(hilo(Card(r, "S")) * n for r, n in self.rank_counts.items())
        all_seen = self.cards_seen == self.shoe.position
        check = "ok" if expected == self.running and (all_seen or not complete) else "mismatch"
        results = Counter(r for e in self.round_log for r in e.get("player_results", []))
        low = sum(n for r, n in self.rank_counts.items() if Card(r, "S").value in range(2, 7))
        high = sum(n for r, n in self.rank_counts.items() if Card(r, "S").value in (1, 10))
        report = {
            "shoe": self.shoe_no, "seed": self.shoe_seed, "complete": complete,
            "started": self.shoe_started, "ended": datetime.now().isoformat(timespec="seconds"),
            "decks": self.rules.decks, "total_cards": len(self.shoe.cards),
            "cut_index": self.shoe.cut_index, "cards_dealt": self.shoe.position,
            "cards_seen": self.cards_seen,
            "penetration": round(self.shoe.position / len(self.shoe.cards), 3),
            "rounds": len(self.round_log),
            "final_running_count": self.running, "final_true_count": self.true_count,
            "decks_left_at_end": round(self.decks_left, 2),
            "highest_true_count": self.max_true, "lowest_true_count": self.min_true,
            "rank_counts": dict(sorted(self.rank_counts.items())),
            "hilo_groups": {"low_2_to_6": low, "neutral_7_to_9": self.cards_seen - low - high,
                            "high_10_and_ace": high},
            "count_check": check,
            "player": {"seat": self.player_seat, "balance_start": self.shoe_start_balance,
                       "balance_end": self.balance,
                       "net": round(self.balance - self.shoe_start_balance, 2),
                       "hands": dict(results)},
            "round_log": self.round_log,
        }
        path = self.history_path.with_name(f"{self.history_path.stem}-shoe{self.shoe_no:02d}.json")
        path.write_text(json.dumps(report, indent=2) + "\n")
        self.history.write("shoe_report", shoe=self.shoe_no, path=path.name, complete=complete)
        return path

    def finish(self) -> Path | None:
        """Call when the simulator stops: writes a report for the shoe in progress."""
        return self.write_shoe_report(complete=False)

    # ----- what the page draws ------------------------------------------------------------

    def snapshot(self) -> dict:
        me = self.seats[self.player_seat - 1]
        legal: list[str] = []
        if (self.phase == "player_turn" and self.active and self.active[0] == self.player_seat
                and self.wait and self.wait.kind == "decision" and not self.wait.resolved):
            hand = me.hands[self.active[1]]
            legal = legal_moves(hand, self.rules, me.splits_used)
            if hand.bet > self.balance:
                legal = [m for m in legal if m not in ("double", "split")]
        dealer_shown = Hand(self.dealer.cards[:1]) if self.hole_hidden else self.dealer
        timer = None
        if self.wait and self.wait.kind in ("betting", "decision", "insurance") and not self.wait.resolved:
            timer = max(0.0, round(self.wait.remaining, 1))
        return {
            "phase": self.phase,
            "message": self.message,
            "round": self.round_no,
            "timer": timer,
            "wait": self.wait.kind if self.wait else None,
            "balance": round(self.balance, 2),
            "player_seat": self.player_seat,
            "legal_moves": legal,
            "insurance_offered": self.phase == "insurance" and bool(self.wait and self.wait.kind == "insurance" and not self.wait.resolved),
            "active": list(self.active) if self.active else None,
            "seats": [self._seat_dict(s) for s in self.seats],
            "dealer": {
                "cards": [c.to_dict() for c in self.dealer.cards],
                "hole_hidden": self.hole_hidden,
                "bubble": bubble_text(dealer_shown, finished=self.dealer.finished),
            },
            "shoe": {
                "total": len(self.shoe.cards),
                "dealt": self.shoe.position,
                "remaining": self.shoe.remaining,
                "cut_index": self.shoe.cut_index,
                "cut_card_out": self.shoe.cut_card_out,
            },
            "discard": {"count": self.discard_count},
            "truth": {"running_count": self.running, "true_count": self.true_count,
                      "decks_left": round(self.decks_left, 2), "cards_seen": self.cards_seen,
                      "last_card": self.last_card, "shoe": self.shoe_no},
            "min_bet": self.rules.min_bet,
            "max_bet": self.rules.max_bet,
        }

    def _seat_dict(self, s: Seat) -> dict:
        return {
            "seat": s.number,
            "name": s.name,
            "occupied": s.occupied,
            "is_player": s.is_player,
            "bet": s.bet,
            "chips": chip_stack(s.bet),
            "insurance": s.insurance,
            "hands": [{
                "cards": [c.to_dict() for c in h.cards],
                "bubble": bubble_text(h, active=self.active == (s.number, i)),
                "bust": h.is_bust,
                "bet": h.bet,
                "doubled": h.doubled,
                "result": h.result,
                "active": self.active == (s.number, i),
            } for i, h in enumerate(s.hands)],
        }


def chip_stack(amount: float) -> list[float]:
    chips = []
    for c in CHIPS:
        while amount >= c - 1e-9 and len(chips) < 6:
            chips.append(c)
            amount -= c
    return chips
