"""Table rules and engine settings."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json
from pathlib import Path


@dataclass
class TableRules:
    # The proposal's rule set: 8 decks, dealer stands on all 17s, blackjack
    # pays 3 to 2, double on any two cards but not after a split, one split,
    # no surrender.
    decks: int = 8
    dealer_hits_soft_17: bool = False      # "stand on all 17s"
    double_after_split: bool = False
    max_splits: int = 1                    # 1 split = up to 2 hands
    split_aces_one_card: bool = True
    double_on: str = "any2"                # 'any2' | '9-11' | '10-11'
    surrender: bool = False
    # Checked on the live table (Nov 21, 2026): the dealer takes a face-down
    # second card and checks it for blackjack only when showing an ace. Under a
    # 10 a dealer blackjack shows up only after players act, and with
    # ``enhc_lose_all`` doubles and splits are lost to it, so strategy avoids
    # extra money against a 10. ``no_hole_card=True`` is a table with no
    # face-down card at all (nothing checked); ``peek_on_ten=True`` a table
    # that also checks under a 10.
    no_hole_card: bool = False
    peek_on_ten: bool = False
    enhc_lose_all: bool = True
    min_bet: float = 10.0
    max_bet: float = 5000.0
    chip_size: float = 1.0                 # bets rounded down to this


@dataclass
class EngineSettings:
    player_seat: int = 0                   # which seat is the user's
    log_readings: bool = True              # write each table reading to the log (for replay)
    bankroll: float = 1000.0
    # Discard tray: Recognition reports a height; this many units = 1 deck.
    tray_height_per_deck: float = 1.0
    # Round decks-left to the nearest half deck (usual Hi-Lo practice).
    decks_left_step: float = 0.5
    # Betting: fraction of Kelly to bet, and house edge / edge per TC.
    kelly_fraction: float = 0.5
    base_edge: float = -0.005
    edge_per_true_count: float = 0.005
    variance: float = 1.33
    rules: TableRules = field(default_factory=TableRules)

    @classmethod
    def load(cls, path: str | Path) -> "EngineSettings":
        data = json.loads(Path(path).read_text())
        rules = TableRules(**data.pop("rules", {}))
        return cls(rules=rules, **data)

    def to_dict(self) -> dict:
        return asdict(self)
