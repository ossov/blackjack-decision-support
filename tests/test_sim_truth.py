"""The simulator's true count, and the report written when a shoe ends."""
import json

from sim.cards import Shoe, hilo
from sim.server import choose_seed
from sim.table import Table


def solo(ranks, **kw):
    return Table(shoe=Shoe.stacked(ranks), other_players=False, player_seat=4, balance=1000, **kw)


def to_decision(t):
    t.run_until("betting")
    t.act("bet", amount=10)
    t.act("deal")
    return t.run_until("player_turn", "insurance", "round_over")


def test_count_includes_only_face_up_cards():
    # player 10 (-1), dealer up 6 (+1), player 2 (+1), dealer hole 10 stays hidden
    t = solo(["10", "6", "2", "10", "10"])
    to_decision(t)
    truth = t.snapshot()["truth"]
    assert truth["running_count"] == 1
    assert truth["cards_seen"] == 3


def test_hole_card_counts_when_it_is_turned_over():
    t = solo(["10", "6", "9", "10", "10"])
    to_decision(t)
    t.act("stand")
    t.run_until("round_over")
    # 10, 6, 9, hole 10, dealer draws 10 -> -1 +1 0 -1 -1
    assert t.snapshot()["truth"]["running_count"] == -2


def test_true_count_uses_the_exact_decks_left():
    t = Table(shoe=Shoe(seed=8), other_players=False, player_seat=4, balance=1000, auto_bet=10, auto_play=True)
    t.run_until("round_over")
    truth = t.snapshot()["truth"]
    decks_left = t.shoe.remaining / 52
    assert truth["decks_left"] == round(decks_left, 2)
    assert truth["true_count"] == round(truth["running_count"] / decks_left, 2)


def test_last_card_names_the_card_and_who_got_it():
    t = solo(["10", "6", "2", "10", "10"])
    to_decision(t)
    last = t.snapshot()["truth"]["last_card"]
    assert last["rank"] == "2" and last["to"] == "seat" and last["seat"] == 4


def test_history_card_events_carry_the_count(tmp_path):
    path = tmp_path / "h.jsonl"
    t = solo(["10", "6", "2", "10", "10"], history_path=path)
    to_decision(t)
    cards = [json.loads(l) for l in path.read_text().splitlines() if '"card"' in l]
    assert [c["running_count"] for c in cards] == [-1, 0, 1, 1]   # the hole card leaves it unchanged


def test_shoe_report_is_written_when_the_shoe_is_shuffled(tmp_path):
    t = Table(shoe=Shoe(seed=2, penetration=0.01), other_players=False, player_seat=4, balance=1000,
              auto_bet=10, auto_play=True, history_path=tmp_path / "s.jsonl")
    t.run_until("round_over")
    t.run_until("betting")          # the cut card came out, so the shoe is shuffled here
    reports = sorted(tmp_path.glob("*shoe*.json"))
    assert len(reports) == 1
    r = json.loads(reports[0].read_text())
    assert r["shoe"] == 1 and r["seed"] == 2 and r["complete"] is True
    assert r["rounds"] == len(r["round_log"]) >= 1
    assert r["cards_dealt"] == sum(r["rank_counts"].values())
    assert r["final_running_count"] == sum(hilo(c) for c in t_cards(r))
    assert r["count_check"] == "ok"


def t_cards(report):
    from sim.cards import Card
    return [Card(rank, "S") for rank, n in report["rank_counts"].items() for _ in range(n)]


def test_stopping_writes_a_report_for_the_unfinished_shoe(tmp_path):
    t = Table(shoe=Shoe(seed=3), other_players=False, player_seat=4, balance=1000,
              auto_bet=10, auto_play=True, history_path=tmp_path / "s.jsonl")
    t.run_until("round_over")
    t.finish()
    r = json.loads(next(tmp_path.glob("*shoe*.json")).read_text())
    assert r["complete"] is False and r["rounds"] == 1


def test_seed_is_random_unless_one_is_given():
    assert choose_seed(42) == 42
    seeds = {choose_seed(None) for _ in range(5)}
    assert len(seeds) > 1
