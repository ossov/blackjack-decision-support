"""Strategy tables: the right move for every hand and dealer card, adjusted
for the true count.

All moves come from JSON tables in ``bjds/engine/data``:

* ``basic_strategy.json`` - basic strategy (8 decks, S17, no double after split)
* ``das_pairs.json``      - pair rows used instead if double after split is on
* ``enhc_overrides.json`` - changes when the dealer has no hole card
* ``deviations.json``     - count-based changes (Illustrious 18 + insurance)

Codes: H hit, S stand, D double (else hit), Ds double (else stand),
P split, '-' don't split (use the total row).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .cards import ACE, card_name
from .rules import TableRules

DATA_DIR = Path(__file__).parent / "data"


class Move(str, Enum):
    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SPLIT = "split"

    @property
    def key(self) -> str:
        return {"hit": "H", "stand": "S", "double": "D", "split": "P"}[self.value]


def dealer_label(up: int) -> str:
    return "A" if up == ACE else str(up)


def hand_label(low: int, soft: bool) -> str:
    """Row name for a total: 'soft 18' or 'hard 16'."""
    if soft and low + 10 <= 21:
        return f"soft {low + 10}"
    return f"hard {low}"


def format_count(tc: float) -> str:
    n = math.floor(tc)
    return f"+{n}" if n > 0 else str(n)


@dataclass
class Decision:
    move: Move
    reason: str              # e.g. "stand, 16 against 10, count is +2"
    hand: str                # e.g. "hard 16" / "pair 8"
    dealer: str              # e.g. "10"
    true_count: float
    deviation: bool          # True when the count changed the move
    table_code: str          # raw code from the table

    def to_dict(self) -> dict:
        return {
            "move": self.move.value, "reason": self.reason, "hand": self.hand,
            "dealer": self.dealer, "true_count": round(self.true_count, 2),
            "deviation": self.deviation, "table_code": self.table_code,
        }


class Strategy:
    def __init__(self, rules: TableRules, data_dir: Path = DATA_DIR):
        self.rules = rules
        self.table = self._load_table(data_dir / "basic_strategy.json")
        if rules.double_after_split:
            das = json.loads((data_dir / "das_pairs.json").read_text())
            for total, row in das["pair"].items():
                for dealer, code in row.items():
                    self.table[(f"pair {total}", dealer)] = code
        if rules.no_hole_card and rules.enhc_lose_all:
            for c in json.loads((data_dir / "enhc_overrides.json").read_text())["changes"]:
                self.table[(c["hand"], c["dealer"])] = c["action"]
        self.deviations: dict[tuple[str, str], dict] = {}
        skip_hole_card = rules.no_hole_card and rules.enhc_lose_all
        for c in json.loads((data_dir / "deviations.json").read_text())["changes"]:
            if skip_hole_card and c["needs_hole_card"]:
                continue
            self.deviations[(c["hand"], c["dealer"])] = c

    @staticmethod
    def _load_table(path: Path) -> dict[tuple[str, str], str]:
        data = json.loads(path.read_text())
        table = {}
        for kind in ("hard", "soft", "pair"):
            for total, row in data[kind].items():
                for dealer, code in row.items():
                    table[(f"{kind} {total}", dealer)] = code
        return table

    # ------------------------------------------------------------------
    def _lookup(self, label: str, dealer: str, tc: float | None) -> tuple[str, bool]:
        """Table code for a hand. ``tc=None`` means plain basic strategy."""
        code = self.table.get((label, dealer))
        if code is None:
            raise KeyError(f"no table entry for {label} vs {dealer}")
        dev = self.deviations.get((label, dealer))
        if dev is None or tc is None:
            return code, False
        new = dev["at_or_above"] if tc >= dev["index"] else dev["below"]
        return new, new != code

    def decide(self, low: int, soft: bool, pair_value: int | None,
               dealer_up: int, true_count: float, legal: list[Move],
               use_count: bool = True) -> Decision:
        """Pick the move for a hand. ``legal`` must be non-empty.

        use_count=False gives plain basic strategy (sent as ``basic_strategy``).
        """
        tc_used = true_count if use_count else None
        if not legal:
            raise ValueError("no legal moves")
        d = dealer_label(dealer_up)

        if pair_value is not None and Move.SPLIT in legal:
            label = f"pair {'A' if pair_value == ACE else pair_value}"
            code, dev = self._lookup(label, d, tc_used)
            if code == "P":
                return self._make(Move.SPLIT, label, d, true_count, dev, code,
                                  f"{card_name(pair_value)}s")

        label = hand_label(low, soft)
        if label.endswith(" 21"):
            code, dev = "S", False
        else:
            code, dev = self._lookup(label, d, tc_used)
        if code in ("D", "Ds"):
            move = Move.DOUBLE if Move.DOUBLE in legal else (
                Move.HIT if code == "D" else Move.STAND)
        elif code == "S":
            move = Move.STAND
        else:
            move = Move.HIT
        if move not in legal:  # e.g. split aces can't be hit
            move = Move.STAND if Move.STAND in legal else legal[0]
        return self._make(move, label, d, true_count, dev, code, label)

    def insurance(self, true_count: float) -> tuple[bool, str]:
        dev = self.deviations.get(("insurance", "A"))
        take = dev is not None and true_count >= dev["index"]
        word = "yes" if take else "no"
        need = format_count(dev["index"]) if dev else "n/a"
        return take, (f"{word} to insurance, count is {format_count(true_count)}"
                      f" (take it at {need} or more)")

    @staticmethod
    def _make(move, label, dealer, tc, dev, code, desc) -> Decision:
        total = desc.replace("hard ", "")
        reason = f"{move.value}, {total} against {dealer}, count is {format_count(tc)}"
        if dev:
            reason += " (count changes the move)"
        return Decision(move, reason, label, dealer, tc, dev, code)
