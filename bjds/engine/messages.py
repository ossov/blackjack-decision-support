"""Messages between the parts (all plain JSON-friendly dicts).

Recognition -> Engine : TableReading
Engine -> App         : EngineOutput   (recommendation + overlay data)
App -> Engine         : submit_move / submit_bet / submit_insurance
Engine -> Simulator   : command dict, e.g. {"type": "move", "hand_id": "s0", "move": "hit"}
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

STAGES = ("betting", "dealing", "insurance", "player_turn", "dealer_turn", "round_over")


@dataclass
class HandReading:
    hand_id: str                       # stable id, e.g. "seat3" / "seat3-split"
    seat: int | None = None            # None for the dealer
    bubble: str | None = None          # raw bubble text: "16", "6/16", "BJ", "BUST"
    new_cards: list[Any] = field(default_factory=list)  # card pictures read since last time
    bet: float | None = None
    split_of: str | None = None        # set when this bubble appeared from a split

    @classmethod
    def from_dict(cls, d: dict) -> "HandReading":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class TableReading:
    stage: str
    hands: list[HandReading] = field(default_factory=list)
    dealer: HandReading | None = None
    discard_tray_height: float | None = None
    cut_card_out: bool = False
    active_hand: str | None = None     # hand being played, if Recognition can tell
    timestamp: float | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "TableReading":
        hands = [HandReading.from_dict(h) for h in d.get("hands", [])]
        dealer = d.get("dealer")
        dealer = HandReading.from_dict({"hand_id": "dealer", **dealer}) if dealer else None
        return cls(stage=d["stage"], hands=hands, dealer=dealer,
                   discard_tray_height=d.get("discard_tray_height"),
                   cut_card_out=bool(d.get("cut_card_out", False)),
                   active_hand=d.get("active_hand"),
                   timestamp=d.get("timestamp"))


@dataclass
class EngineOutput:
    stage: str
    round: int
    running_count: int
    true_count: float
    decks_left: float
    recommendation: dict | None = None   # kind: 'bet' | 'insurance' | 'move'
    allowed: list[str] = field(default_factory=list)
    new_cards: list[dict] = field(default_factory=list)
    uncertain_cards: int = 0
    hands: list[dict] = field(default_factory=list)
    dealer: dict | None = None
    verification: dict | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["true_count"] = round(self.true_count, 2)
        return d


@dataclass
class MoveResult:
    accepted: bool
    reason: str
    command: dict | None = None          # forwarded to the Simulator
    shown: str | None = None             # e.g. "You chose: Hit"

    def to_dict(self) -> dict:
        return asdict(self)
