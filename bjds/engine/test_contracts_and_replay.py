import json
from pathlib import Path

from bjds.engine import Engine, EngineSettings
from bjds.engine.replay import replay

from helpers import reading

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"


def load(name):
    return json.loads((CONTRACTS / name).read_text())


def test_engine_reads_the_table_reading_contract_example():
    e = Engine(EngineSettings(log_readings=False))
    e.process({"stage": "betting"})
    out = e.process(load("table_reading.example.json"))
    assert out.recommendation["kind"] == "move"


def test_move_recommendation_has_the_contract_fields():
    e = Engine(EngineSettings(log_readings=False))
    e.process({"stage": "betting"})
    rec = e.process(load("table_reading.example.json")).recommendation
    assert set(rec) == set(load("recommendation.move.example.json"))


def test_bet_and_insurance_recommendations_have_the_contract_fields():
    e = Engine(EngineSettings(log_readings=False))
    assert set(e.process({"stage": "betting"}).recommendation) == set(
        load("recommendation.bet.example.json"))
    rec = e.process(reading("insurance", [("s0", 0, "18")], "1/11")).recommendation
    assert set(rec) == set(load("recommendation.insurance.example.json"))


def test_simulator_command_matches_the_contract_example():
    e = Engine(EngineSettings(log_readings=False))
    e.process({"stage": "betting"})
    e.process(load("table_reading.example.json"))
    cmd = e.submit_move("stand").command
    assert set(cmd) == set(load("simulator_command.example.json")["move"])


def test_replaying_a_session_log_gives_the_same_count(tmp_path):
    log = tmp_path / "session.jsonl"
    e = Engine(EngineSettings(), log_path=log)
    e.process(reading("betting"))
    e.submit_bet(10)
    e.process(reading("player_turn", [("s0", 0, "10"), ("s1", 1, "5")], "6"))
    e.process(reading("player_turn", [("s0", 0, "16"), ("s1", 1, "15")], "6"))
    e.submit_move("stand")
    replayed, results = replay(log)
    assert replayed.counter.running == e.counter.running
    assert any(r["event"] == "move" and r["result"]["accepted"] for r in results)
