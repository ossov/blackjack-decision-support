from bjds.engine import Engine, EngineSettings
from bjds.engine.count import HiLoCounter
from bjds.engine.demo import FakeTable

from helpers import reading


def test_true_count_divides_by_decks_left_from_the_discard_tray():
    c = HiLoCounter(8, tray_height_per_deck=10)
    for v in (2, 3, 4, 5, 6, 2):
        c.add(v)
    c.set_tray_height(40)          # 4 decks in the tray
    assert c.decks_left() == 4.0
    assert c.true_count() == 1.5


def test_full_shoe_counts_back_to_zero():
    t = FakeTable(seed=42)
    e = Engine(EngineSettings(log_readings=False))
    e.process(reading("betting"))
    i = 0
    while t.shoe:
        card = t.draw()
        e.process({"stage": "dealing", "hands": [
            {"hand_id": f"h{i}", "seat": 1, "bubble": None, "new_cards": [card]}]})
        i += 1
    assert e.counter.cards_seen == 416
    assert e.counter.running == 0


def test_count_resets_in_the_round_after_the_cut_card_comes_out():
    e = Engine(EngineSettings(log_readings=False))
    e.process(reading("betting"))
    e.process(reading("player_turn", [("s0", 0, "5")], "4", cut_card_out=True))
    assert e.counter.running == 2
    e.process(reading("round_over"))
    out = e.process(reading("betting"))
    assert e.counter.running == 0 and any("shuffle" in n for n in out.notes)


def test_uncertain_card_is_left_out_of_the_count():
    e = Engine(EngineSettings(log_readings=False))
    e.process(reading("betting"))
    e.process(reading("player_turn", [("s1", 1, "10"), ], "6"))
    e.process(reading("player_turn", [("s1", 1, "15")], "6"))
    before = e.counter.running
    out = e.process(reading("player_turn", [("s1", 1, "BUST")], "6"))
    assert out.uncertain_cards == 1 and e.counter.running == before
