from bjds.engine import Engine, EngineSettings

from helpers import reading


def new_engine(**kw):
    return Engine(EngineSettings(log_readings=False, **kw))


def test_betting_stage_recommends_a_bet_and_rejects_bets_outside_limits():
    e = new_engine(bankroll=1000)
    out = e.process(reading("betting"))
    assert out.recommendation["kind"] == "bet" and out.recommendation["amount"] == 10
    assert e.submit_bet(10).accepted
    assert not e.submit_bet(1).accepted
    assert not e.submit_bet(2000).accepted


def test_player_turn_recommends_a_move_with_its_reason():
    e = new_engine()
    e.process(reading("betting"))
    e.process(reading("dealing", [("s0", 0, "10")], "6"))
    out = e.process(reading("player_turn", [("s0", 0, "16")], "6"))
    rec = out.recommendation
    assert rec["action"] == "stand" and rec["basic_strategy"] == "stand"
    assert rec["hand"] == {"cards": [10, 6], "total": 16, "soft": False}
    assert rec["upcard"] == 6 and rec["legal_moves"] == ["hit", "stand", "double"]


def test_accepted_move_shows_the_choice_and_builds_the_simulator_command():
    e = new_engine()
    e.process(reading("betting"))
    e.process(reading("player_turn", [("s0", 0, "12")], "10"))
    r = e.submit_move("H", source="voice")
    assert r.accepted and r.shown == "You chose: Hit"
    assert r.command == {"type": "move", "seat": 0, "hand_id": "s0", "move": "hit"}


def test_double_on_three_cards_is_rejected():
    e = new_engine()
    e.process(reading("betting"))
    e.process(reading("player_turn", [("s0", 0, "5")], "10"))
    e.process(reading("player_turn", [("s0", 0, "8")], "10"))
    e.process(reading("player_turn", [("s0", 0, "11")], "10"))
    r = e.submit_move("double")
    assert not r.accepted and "3 cards" in r.reason


def test_split_on_a_non_pair_is_rejected():
    e = new_engine()
    e.process(reading("betting"))
    e.process(reading("player_turn", [("s0", 0, "10")], "10"))
    e.process(reading("player_turn", [("s0", 0, "16")], "10"))
    r = e.submit_move("split")
    assert not r.accepted and "non-pair" in r.reason


def test_split_makes_two_hands_without_counting_cards_twice():
    e = new_engine()
    e.process(reading("betting"))
    e.process(reading("player_turn", [("s0", 0, "8")], "9"))
    e.process(reading("player_turn", [("s0", 0, "16")], "9"))
    assert e.submit_move("split").accepted
    rc = e.counter.running
    out = e.process({"stage": "player_turn", "dealer": {"bubble": "9"},
                     "hands": [{"hand_id": "s0", "seat": 0, "bubble": "11"},
                               {"hand_id": "s0b", "seat": 0, "bubble": "8", "split_of": "s0"}]})
    assert [h["hand_id"] for h in out.hands] == ["s0", "s0b"]
    assert e.hands["s0"].cards == [8, 3] and e.hands["s0b"].cards == [8]
    assert e.counter.running == rc + 1


def test_no_second_split_and_no_double_after_split():
    e = new_engine()
    e.process(reading("betting"))
    e.process(reading("player_turn", [("s0", 0, "8")], "9"))
    e.process(reading("player_turn", [("s0", 0, "16")], "9"))
    e.submit_move("split")
    e.process({"stage": "player_turn", "dealer": {"bubble": "9"},
               "hands": [{"hand_id": "s0", "seat": 0, "bubble": "16"},
                         {"hand_id": "s0b", "seat": 0, "bubble": "8", "split_of": "s0"}]})
    out = e.process({"stage": "player_turn", "dealer": {"bubble": "9"},
                     "hands": [{"hand_id": "s0", "seat": 0, "bubble": "16"},
                               {"hand_id": "s0b", "seat": 0, "bubble": "8"}]})
    assert out.allowed == ["hit", "stand"]
    assert not e.submit_move("split").accepted
    assert not e.submit_move("double").accepted


def test_insurance_is_offered_yes_or_no_against_an_ace():
    e = new_engine()
    e.process(reading("betting"))
    out = e.process(reading("insurance", [("s0", 0, "12")], "1/11"))
    assert out.recommendation["action"] == "no" and out.allowed == ["yes", "no"]
    assert e.submit_insurance(False).accepted


def test_move_is_rejected_outside_the_players_turn():
    e = new_engine()
    e.process(reading("betting"))
    assert not e.submit_move("hit").accepted


def test_moves_are_written_to_the_session_log(tmp_path):
    log = tmp_path / "session.jsonl"
    e = Engine(EngineSettings(), log_path=log)
    e.process(reading("betting"))
    e.process(reading("player_turn", [("s0", 0, "12")], "10"))
    e.submit_move("hit", source="voice")
    text = log.read_text()
    assert '"event": "move"' in text and '"source": "voice"' in text


def test_real_table_sends_nothing_to_the_simulator():
    e = Engine(EngineSettings(log_readings=False), real_table=True)
    e.process(reading("betting"))
    assert e.submit_bet(10).command is None
    e.process(reading("player_turn", [("s0", 0, "12")], "10"))
    r = e.submit_move("hit")
    assert r.accepted and r.command is None


def test_real_table_flags_a_card_after_the_player_said_stand():
    e = Engine(EngineSettings(log_readings=False), real_table=True)
    e.process(reading("betting"))
    e.process(reading("player_turn", [("s0", 0, "12")], "10"))
    e.submit_move("stand")
    out = e.process(reading("player_turn", [("s0", 0, "20")], "10"))
    assert out.verification["status"] == "mismatch"
