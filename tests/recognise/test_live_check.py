import json

from bjds.engine import Engine, EngineSettings
from bjds.recognise.live_check import LiveCheck


def empty_table():
    return {"stage": "betting", "active_hand": None, "hands": [],
            "dealer": {"bubble": None, "new_cards": []},
            "discard_tray_height": None, "cut_card_out": False, "timestamp": 0}


def mid_round():
    r = empty_table()
    r.update(stage="dealing",
             hands=[{"hand_id": "seat1", "seat": 1, "bubble": "12", "new_cards": []}],
             dealer={"bubble": "10", "new_cards": []})
    return r


def truth(running=0, cards=0, shoe=1):
    return {"running_count": running, "true_count": 0.0, "cards_seen": cards, "shoe": shoe}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(tmp_path, clock=None):
    return Engine(EngineSettings(player_seat=4)), LiveCheck(tmp_path, clock=clock or Clock())


def events(tmp_path):
    return [json.loads(line) for line in (tmp_path / "live_check.jsonl").read_text().splitlines()]


def test_waits_for_an_empty_table_before_counting(tmp_path):
    engine, check = make(tmp_path)
    result, status = check.step(engine, mid_round(), truth(running=-1, cards=20))
    assert result is None and status == "waiting"
    assert engine.counter.running == 0


def test_syncs_the_engine_to_the_simulator_count_at_an_empty_table(tmp_path):
    engine, check = make(tmp_path)
    result, status = check.step(engine, empty_table(), truth(running=-1, cards=20))
    assert status == "match"
    assert engine.counter.running == -1 and engine.counter.cards_seen == 20
    assert result.running_count == -1


def test_a_short_disagreement_is_catching_up_not_a_mistake(tmp_path):
    clock = Clock()
    engine, check = make(tmp_path, clock)
    check.step(engine, empty_table(), truth())
    clock.now += 1
    _, status = check.step(engine, empty_table(), truth(running=1, cards=1))
    assert status == "catching_up"


def test_a_lasting_disagreement_is_a_mistake_and_is_logged(tmp_path):
    clock = Clock()
    engine, check = make(tmp_path, clock)
    check.step(engine, empty_table(), truth())
    check.step(engine, empty_table(), truth(running=1, cards=1))
    clock.now += 3.5
    _, status = check.step(engine, empty_table(), truth(running=1, cards=1))
    assert status == "mismatch"
    kinds = [e["event"] for e in events(tmp_path)]
    assert kinds.count("mismatch") == 1


def test_a_new_shoe_resyncs_at_the_next_empty_table(tmp_path):
    engine, check = make(tmp_path)
    check.step(engine, empty_table(), truth(running=-4, cards=200, shoe=1))
    result, status = check.step(engine, mid_round(), truth(running=2, cards=4, shoe=2))
    assert result is None and status == "waiting"
    check.step(engine, empty_table(), truth(running=2, cards=4, shoe=2))
    assert engine.counter.running == 2 and engine.counter.cards_seen == 4


def test_unchanged_frames_are_not_logged_again(tmp_path):
    engine, check = make(tmp_path)
    for _ in range(5):
        check.step(engine, empty_table(), truth(running=-1, cards=20))
    frames = [e for e in events(tmp_path) if e["event"] == "frame"]
    assert len(frames) == 1


def test_resync_waits_for_an_empty_table_then_takes_the_simulators_count(tmp_path):
    engine, check = make(tmp_path)
    check.step(engine, empty_table(), truth(running=-1, cards=20))
    engine.counter.running = 5                     # the count has gone wrong
    check.resync()
    result, status = check.step(engine, mid_round(), truth(running=-2, cards=24))
    assert result is None and status == "waiting"
    check.step(engine, empty_table(), truth(running=-2, cards=24))
    assert engine.counter.running == -2 and engine.counter.cards_seen == 24


def test_resync_clears_the_mistake_tally(tmp_path):
    clock = Clock()
    engine, check = make(tmp_path, clock)
    check.step(engine, empty_table(), truth())
    check.step(engine, empty_table(), truth(running=1, cards=1))
    clock.now += 3.5
    check.step(engine, empty_table(), truth(running=1, cards=1))
    assert check.mismatches == 1
    check.resync()
    assert check.mismatches == 0
    assert events(tmp_path)[-1]["event"] == "resync"
