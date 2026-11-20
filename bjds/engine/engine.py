"""The Engine: table readings in, recommendations and moves out."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .betting import recommend_bet
from .cards import ACE, card_name, parse_bubble, parse_card
from .count import HiLoCounter
from .hands import HandState
from .legal import legal_moves, why_illegal
from .messages import EngineOutput, HandReading, MoveResult, TableReading
from .rules import EngineSettings
from .session_log import SessionLog
from .strategy import Move, Strategy, format_count
from .verify import PendingCheck

_MOVE_ALIASES = {"h": "hit", "s": "stand", "d": "double", "p": "split"}


class Engine:
    def __init__(self, settings: EngineSettings | None = None,
                 log_path: str | Path | None = None, real_table: bool = False):
        self.settings = settings or EngineSettings()
        self.rules = self.settings.rules
        self.strategy = Strategy(self.rules)
        self.counter = HiLoCounter(self.rules.decks,
                                   self.settings.tray_height_per_deck,
                                   self.settings.decks_left_step)
        self.log = SessionLog(log_path)
        self.real_table = real_table
        self.bankroll = self.settings.bankroll
        self.round_no = 0
        self.stage: str | None = None
        self.shuffle_pending = False
        self.active_hand_id: str | None = None
        self.pending_check: PendingCheck | None = None
        self._last_advice: dict[str, str] = {}
        self._reset_table()
        self.log.write("session_start", bankroll=self.bankroll,
                       settings=self.settings.to_dict(), real_table=real_table)

    # ------------------------------------------------------------------ state
    def _reset_table(self) -> None:
        self.hands: dict[str, HandState] = {}
        self.dealer = HandState("dealer")
        self.splits_done: dict[int, int] = {}
        self.pending_check = None
        self._last_advice = {}

    @property
    def player_seat(self) -> int:
        return self.settings.player_seat

    @property
    def dealer_up(self) -> int | None:
        return self.dealer.cards[0] if self.dealer.cards else None

    def player_hands(self) -> list[HandState]:
        return [h for h in self.hands.values() if h.seat == self.player_seat]

    def seat_hand_count(self, seat: int) -> int:
        return sum(1 for h in self.hands.values() if h.seat == seat)

    def current_player_hand(self) -> HandState | None:
        if self.active_hand_id in self.hands:
            h = self.hands[self.active_hand_id]
            if h.seat == self.player_seat and not h.finished:
                return h
        for h in self.player_hands():
            if not h.finished and h.n_cards >= 2:
                return h
        return None

    def set_bankroll(self, amount: float) -> None:
        self.bankroll = float(amount)
        self.log.write("bankroll", amount=self.bankroll)

    # ----------------------------------------------------------- main input
    def process(self, reading: TableReading | dict) -> EngineOutput:
        if isinstance(reading, dict):
            raw = reading
            reading = TableReading.from_dict(reading)
        else:
            raw = asdict(reading)
        if self.settings.log_readings:
            self.log.write("table_reading", reading=raw)
        notes: list[str] = []
        new_cards: list[dict] = []

        if reading.stage == "betting" and self.stage != "betting":
            self._new_round(notes)
        self.stage = reading.stage
        self.active_hand_id = reading.active_hand

        self._check_tray(reading.discard_tray_height, notes)
        if reading.cut_card_out and not self.shuffle_pending:
            self.shuffle_pending = True
            notes.append("cut card is out: shuffle after this round")
            self.log.write("cut_card_out", round=self.round_no)

        # Pass 1: new hands (and splits) before any totals are applied.
        for hr in reading.hands:
            if hr.hand_id not in self.hands:
                self._add_hand(hr, notes)
        # Pass 2: totals -> cards -> count.
        for hr in reading.hands:
            self._update(self.hands[hr.hand_id], hr, new_cards, notes)
        if reading.dealer is not None:
            self._update(self.dealer, reading.dealer, new_cards, notes)

        verification = None
        if self.pending_check is not None:
            verification = self.pending_check.check(self)
            if verification:
                self.log.write("move_check", **verification)
                self.pending_check = None

        out = EngineOutput(
            stage=self.stage, round=self.round_no,
            running_count=self.counter.running,
            true_count=self.counter.true_count(),
            decks_left=self.counter.decks_left(),
            new_cards=new_cards,
            uncertain_cards=sum(h.uncertain for h in self.hands.values()) + self.dealer.uncertain,
            hands=[h.to_dict() for h in self.hands.values()],
            dealer=self.dealer.to_dict(),
            verification=verification, notes=notes,
        )
        self._recommend(out)
        return out

    def _new_round(self, notes: list[str]) -> None:
        if self.shuffle_pending:
            self._shuffle("cut card came out last round", notes)
        self._reset_table()
        self.counter.new_round()
        self.round_no += 1
        self.log.write("round_start", round=self.round_no,
                       running_count=self.counter.running,
                       true_count=round(self.counter.true_count(), 2),
                       bankroll=self.bankroll)

    def _shuffle(self, why: str, notes: list[str]) -> None:
        self.counter.reset()
        self.shuffle_pending = False
        notes.append(f"shuffle: count reset ({why})")
        self.log.write("shuffle", reason=why, round=self.round_no)

    def _check_tray(self, height: float | None, notes: list[str]) -> None:
        if height is None:
            return
        per_deck = self.settings.tray_height_per_deck
        old = self.counter.tray_height
        if old is not None and old >= per_deck and height < 0.25 * per_deck:
            self._shuffle("discard tray emptied", notes)
        self.counter.set_tray_height(height)

    def _add_hand(self, hr: HandReading, notes: list[str]) -> None:
        parent = self.hands.get(hr.split_of) if hr.split_of else self._split_parent(hr.seat)
        if parent is not None and parent.n_cards == 2:
            child = parent.split_off(hr.hand_id)
            self.splits_done[parent.seat] = self.splits_done.get(parent.seat, 0) + 1
            # keep play order: the new hand goes right after its parent
            items = list(self.hands.items())
            i = [k for k, _ in items].index(parent.hand_id) + 1
            items.insert(i, (child.hand_id, child))
            self.hands = dict(items)
            notes.append(f"{parent.hand_id} split into {parent.hand_id} and {child.hand_id}")
            self.log.write("split", parent=parent.hand_id, child=child.hand_id)
        else:
            self.hands[hr.hand_id] = HandState(hr.hand_id, hr.seat)

    def _split_parent(self, seat: int | None) -> HandState | None:
        if seat is None:
            return None
        cands = [h for h in self.hands.values() if h.seat == seat and h.n_cards == 2
                 and (h.pair_value is not None or h.uncertain)]
        return cands[0] if len(cands) == 1 else None

    def _update(self, hand: HandState, hr: HandReading,
                new_cards: list[dict], notes: list[str]) -> None:
        if hr.bet is not None:
            hand.bet = hr.bet
        bubble = parse_bubble(hr.bubble)
        if hr.bubble is not None and bubble is None:
            notes.append(f"{hand.hand_id}: can't read bubble {hr.bubble!r}")
        pictures = []
        for c in hr.new_cards or []:
            try:
                pictures.append(parse_card(c))
            except ValueError:
                notes.append(f"{hand.hand_id}: bad card picture {c!r}")
        inf = hand.apply(bubble, pictures)
        if inf.note:
            notes.append(f"{hand.hand_id}: {inf.note}")
        for c in inf.cards:
            if c is None:
                self.counter.cards_on_table += 1
            else:
                self.counter.add(c)
            ev = {"hand_id": hand.hand_id, "card": card_name(c) if c else "?",
                  "source": inf.source, "uncertain": c is None}
            new_cards.append(ev)
            self.log.write("card", round=self.round_no, **ev,
                           running_count=self.counter.running)

    # ------------------------------------------------------- recommendations
    def _recommend(self, out: EngineOutput) -> None:
        tc = self.counter.true_count()
        tcf = self.counter.true_count_floor()
        if self.stage == "betting":
            bet = recommend_bet(tc, self.bankroll, self.settings)
            out.allowed = ["bet"]
            out.recommendation = {"kind": "bet", **bet.to_dict(),
                                  "min_bet": self.rules.min_bet,
                                  "max_bet": min(self.rules.max_bet, self.bankroll),
                                  "legal_moves": out.allowed}
        elif self.stage == "insurance" and self.dealer_up == ACE:
            take, reason = self.strategy.insurance(tcf)
            out.allowed = ["yes", "no"]
            out.recommendation = {"kind": "insurance", "action": "yes" if take else "no",
                                  "basic_strategy": "no", "take": take, "upcard": ACE,
                                  "true_count": round(tc, 2), "reason": reason,
                                  "legal_moves": out.allowed}
        elif self.stage == "player_turn":
            hand = self.current_player_hand()
            if hand is None:
                return
            if self.dealer_up is None:
                out.notes.append("dealer upcard not read yet")
                return
            if hand.low is None:
                out.notes.append(f"{hand.hand_id}: hand total unknown, no advice")
                return
            legal = legal_moves(hand, self.splits_done.get(hand.seat, 0), self.rules)
            if not legal:
                return
            d = self.strategy.decide(hand.low, hand.soft, hand.pair_value,
                                     self.dealer_up, tcf, legal)
            if hand.n_cards == 2 and hand.uncertain and Move.SPLIT not in legal:
                out.notes.append(f"{hand.hand_id}: a card is uncertain, split not offered")
            basic = self.strategy.decide(hand.low, hand.soft, hand.pair_value,
                                         self.dealer_up, tcf, legal, use_count=False)
            out.allowed = [m.value for m in legal]
            out.recommendation = {
                "kind": "move", "hand_id": hand.hand_id,
                "hand": {"cards": list(hand.cards), "total": hand.best,
                         "soft": bool(hand.soft and hand.low + 10 <= 21)},
                "upcard": self.dealer_up, "true_count": round(tc, 2),
                "action": d.move.value, "basic_strategy": basic.move.value,
                "reason": d.reason, "deviation": d.deviation,
                "table_row": d.hand, "legal_moves": out.allowed,
            }
            if self._last_advice.get(hand.hand_id) != d.reason:
                self._last_advice[hand.hand_id] = d.reason
                self.log.write("advice", round=self.round_no, hand_id=hand.hand_id,
                               **d.to_dict())

    # ------------------------------------------------------- player actions
    def submit_bet(self, amount: float) -> MoveResult:
        r = self.rules
        if self.stage != "betting":
            return self._reject("bet", "betting is closed")
        if amount < r.min_bet or amount > r.max_bet:
            return self._reject("bet", f"bet must be ${r.min_bet:g} to ${r.max_bet:g}")
        if amount > self.bankroll:
            return self._reject("bet", f"bet is more than the bankroll (${self.bankroll:g})")
        self.log.write("bet", round=self.round_no, amount=amount,
                       true_count=round(self.counter.true_count(), 2))
        return MoveResult(True, "ok", self._to_sim({"type": "bet", "seat": self.player_seat,
                                                    "amount": amount}), f"You bet: ${amount:g}")

    def submit_insurance(self, take: bool) -> MoveResult:
        if self.stage != "insurance" or self.dealer_up != ACE:
            return self._reject("insurance", "insurance is not offered now")
        advised, _ = self.strategy.insurance(self.counter.true_count_floor())
        self.log.write("insurance", round=self.round_no, take=take,
                       followed_advice=take == advised)
        return MoveResult(True, "ok", self._to_sim({"type": "insurance",
                                                    "seat": self.player_seat, "take": take}),
                          f"You chose: {'Yes' if take else 'No'} to insurance")

    def submit_move(self, move: str | Move, hand_id: str | None = None,
                    source: str = "unknown") -> MoveResult:
        """Player's move from voice or the backup buttons."""
        try:
            m = move if isinstance(move, Move) else Move(
                _MOVE_ALIASES.get(str(move).strip().lower(), str(move).strip().lower()))
        except ValueError:
            return self._reject(str(move), f"unknown move {move!r}")
        if self.stage != "player_turn":
            return self._reject(m.value, "it is not the player's turn")
        hand = self.hands.get(hand_id) if hand_id else self.current_player_hand()
        if hand is None or hand.seat != self.player_seat:
            return self._reject(m.value, "no player hand to play")
        splits = self.splits_done.get(hand.seat, 0)
        if m not in legal_moves(hand, splits, self.rules):
            return self._reject(m.value, why_illegal(m, hand, splits, self.rules))

        if self.real_table:
            self.pending_check = PendingCheck(
                hand.hand_id, hand.seat, m, hand.n_cards,
                self.seat_hand_count(hand.seat), self.dealer.n_cards, hand.bet)
        if m == Move.STAND:
            hand.stood = True
        elif m == Move.DOUBLE:
            hand.doubled = True
        advised = self._last_advice.get(hand.hand_id, "")
        self.log.write("move", round=self.round_no, hand_id=hand.hand_id, move=m.value,
                       source=source, advice=advised,
                       followed_advice=advised.startswith(m.value + ","),
                       true_count=round(self.counter.true_count(), 2))
        return MoveResult(True, "ok",
                          self._to_sim({"type": "move", "seat": hand.seat,
                                        "hand_id": hand.hand_id, "move": m.value}),
                          f"You chose: {m.value.capitalize()}")

    def _to_sim(self, command: dict) -> dict | None:
        """Moves and bets go to the Simulator only; on a real table the
        player acts and the Engine checks the next cards instead."""
        return None if self.real_table else command

    def _reject(self, what: str, why: str) -> MoveResult:
        self.log.write("rejected", round=self.round_no, action=what, reason=why)
        return MoveResult(False, why)

    # ------------------------------------------------------------ overlay
    def overlay(self) -> dict:
        """Snapshot for the App overlay."""
        return {
            "running_count": self.counter.running,
            "true_count": format_count(self.counter.true_count()),
            "decks_left": self.counter.decks_left(),
            "bankroll": self.bankroll,
            "dealer": self.dealer.to_dict(),
            "player_hands": [h.to_dict() for h in self.player_hands()],
            "uncertain_cards": sum(h.uncertain for h in self.hands.values())
                               + self.dealer.uncertain,
        }
