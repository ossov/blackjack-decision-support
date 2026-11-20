"""End-to-end demo: a tiny stand-in for the Simulator + Recognition.

It deals a seeded 8-deck shoe, shows each hand only as its bubble text
(exactly what Recognition will send), lets the Engine pick moves and bets,
and checks the Engine's running count against the true count.

    python -m bjds.engine.demo --rounds 200 --seed 7 --verbose
"""
from __future__ import annotations

import argparse
import random

from bjds.engine import Engine, EngineSettings
from bjds.engine.cards import ACE, hilo


def bubble(cards: list[int]) -> str:
    low = sum(cards)
    if len(cards) == 2 and sorted(cards) == [ACE, 10]:
        return "BJ"
    if low > 21:
        return "BUST"
    if ACE in cards and low + 10 <= 21:
        return "21" if low + 10 == 21 else f"{low}/{low + 10}"
    return str(low)


class FakeTable:
    def __init__(self, seed: int, decks: int = 8, penetration: float = 0.75):
        self.rng = random.Random(seed)
        self.decks = decks
        self.pen = penetration
        self.true_running = 0
        self.new_shoe()

    def new_shoe(self):
        self.shoe = [v for v in list(range(1, 10)) + [10] * 4 for _ in range(4 * self.decks)]
        self.rng.shuffle(self.shoe)
        self.cut = int(len(self.shoe) * (1 - self.pen))
        self.discards = 0
        self.true_running = 0

    def draw(self) -> int:
        c = self.shoe.pop()
        self.true_running += hilo(c)
        return c

    @property
    def cut_out(self):
        return len(self.shoe) <= self.cut

    @property
    def tray(self):
        return self.discards / 52   # tray height in decks


def basic_other_player(cards):  # other players: hit below 17
    return sum(cards) + (10 if ACE in cards and sum(cards) + 10 <= 21 else 0) < 17


def play(rounds: int, seed: int, verbose: bool, pictures: bool = False) -> dict:
    t = FakeTable(seed)
    e = Engine(EngineSettings(player_seat=0, bankroll=2000), log_path="logs/engine_demo.jsonl")
    mismatches = shuffles = explained = 0
    sent: dict[str, int] = {}   # cards already reported per hand (for pictures)

    def pics(hid, cards):
        if not pictures:
            return {}
        new = cards[sent.get(hid, 0):]
        sent[hid] = len(cards)
        return {"new_cards": new}

    def snap(stage, hands, dealer, active=None):
        return {"stage": stage, "active_hand": active,
                "hands": [{"hand_id": hid, "seat": seat, "bubble": bubble(c),
                           **extra, **pics(hid, c)}
                          for hid, (seat, c, extra) in hands.items() if c],
                "dealer": {"bubble": bubble(dealer), **pics("dealer", dealer)} if dealer else None,
                "discard_tray_height": t.tray, "cut_card_out": t.cut_out}

    for _ in range(rounds):
        out = e.process(snap("betting", {}, []))
        if any("shuffle" in n for n in out.notes):
            shuffles += 1
        bet = out.recommendation["amount"]
        e.submit_bet(bet)
        if verbose:
            print(f"\n-- round {e.round_no}: TC {out.true_count:+.2f}, {out.recommendation['reason']}")

        sent.clear()
        hands = {"s0": (0, [], {}), "s1": (1, [], {})}
        dealer: list[int] = []
        for _ in range(2):
            for h in hands.values():
                h[1].append(t.draw())
                e.process(snap("dealing", hands, dealer))
            if not dealer:
                dealer.append(t.draw())
                e.process(snap("dealing", hands, dealer))

        if dealer[0] == ACE:
            out = e.process(snap("insurance", hands, dealer))
            e.submit_insurance(out.recommendation["take"])

        # players act in order; hands dict may grow on a split
        order = ["s0", "s1"]
        i = 0
        while i < len(order):
            hid = order[i]
            seat, cards, _ = hands[hid]
            while True:
                if seat != 0:
                    if not basic_other_player(cards):
                        break
                    cards.append(t.draw())
                    e.process(snap("player_turn", hands, dealer, hid))
                    continue
                out = e.process(snap("player_turn", hands, dealer, hid))
                rec = out.recommendation
                if not rec or rec.get("kind") != "move" or rec["hand_id"] != hid:
                    break
                if verbose:
                    print(f"   {hid} {bubble(cards):>6} vs {dealer[0]}: {rec['reason']}")
                res = e.submit_move(rec["action"], hid, source="demo")
                assert res.accepted, res.reason
                m = rec["action"]
                if m == "stand":
                    break
                if m == "split":
                    new_id = hid + "b"
                    hands[hid] = (seat, [cards[0]], {})
                    hands[new_id] = (seat, [cards[1]], {"split_of": hid})
                    sent[hid] = sent[new_id] = 1
                    hands = dict(sorted(hands.items()))
                    order.insert(i + 1, new_id)
                    e.process(snap("player_turn", hands, dealer, hid))
                    cards = hands[hid][1]
                    cards.append(t.draw())
                    hands[new_id][1].append(t.draw())
                    e.process(snap("player_turn", hands, dealer, hid))
                    if cards[0] == ACE:
                        break
                    continue
                cards.append(t.draw())
                e.process(snap("player_turn", hands, dealer, hid))
                if m == "double":
                    break
            i += 1

        while True:  # dealer stands on all 17s
            low = sum(dealer)
            best = low + 10 if ACE in dealer and low + 10 <= 21 else low
            if best >= 17:
                break
            dealer.append(t.draw())
            e.process(snap("dealer_turn", hands, dealer))
        e.process(snap("round_over", hands, dealer))

        if e.counter.running != t.true_running:
            unc = e.overlay()["uncertain_cards"]
            if unc:
                explained += 1   # engine refused to guess an uncertain card
            else:
                mismatches += 1
                print(f"round {e.round_no}: engine count {e.counter.running} != true {t.true_running}")
            e.counter.running = t.true_running  # resync so later rounds are tested fairly

        t.discards += sum(len(c) for _, c, _ in hands.values()) + len(dealer)
        if t.cut_out:
            t.new_shoe()

    moves = [ev for ev in e.log.events if ev["event"] == "move"]
    unc = sum(1 for ev in e.log.events if ev["event"] == "card" and ev["uncertain"])
    cards = sum(1 for ev in e.log.events if ev["event"] == "card")
    print(f"\n{'bubbles + pictures' if pictures else 'bubbles only'}: {rounds} rounds, "
          f"{shuffles} shuffles, {cards} cards read, {unc} uncertain")
    print(f"  rounds where count was off: {mismatches} wrong, "
          f"{explained} only because of uncertain cards")
    print(f"  moves logged: {len(moves)}")
    return {"wrong": mismatches, "uncertain_rounds": explained, "uncertain": unc}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=300)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--pictures", action="store_true",
                    help="also send card pictures (the YOLO backup)")
    a = ap.parse_args()
    play(a.rounds, a.seed, a.verbose, a.pictures)
