from argparse import Namespace

from sim.server import Sim


def make_sim(tmp_path, seed=7):
    args = Namespace(seed=seed, history=tmp_path / "first.jsonl", penetration=0.5, seat=4, balance=1000,
                     no_others=False, bet=10, script=True, dataset=False, speed=1.0)
    return Sim(args)


def play_a_while(sim, seconds=40):
    for _ in range(int(seconds / 0.05)):
        sim.table.tick(0.05)
        sim.table.step()


def test_restart_deals_a_fresh_shoe_from_the_given_seed(tmp_path):
    sim = make_sim(tmp_path)
    play_a_while(sim)
    assert sim.state()["truth"]["cards_seen"] > 0
    s = sim.restart({"seed": 42})
    assert s["seed"] == 42
    assert s["truth"]["cards_seen"] == 0 and s["truth"]["running_count"] == 0
    fresh = make_sim(tmp_path / "fresh", seed=42).state()
    assert s["round"] == fresh["round"] and s["balance"] == fresh["balance"]


def test_restart_without_a_seed_picks_a_new_one(tmp_path):
    sim = make_sim(tmp_path)
    seeds = {sim.restart({})["seed"] for _ in range(5)}
    assert len(seeds) > 1


def test_restart_writes_a_new_history_file(tmp_path):
    sim = make_sim(tmp_path)
    first = sim.history_path
    s = sim.restart({"seed": 42})
    assert s["history"] != str(first)
    assert sim.history_path.parent == first.parent and sim.history_path.exists()


def test_restart_saves_the_report_for_the_unfinished_shoe(tmp_path):
    sim = make_sim(tmp_path)
    play_a_while(sim)
    sim.restart({"seed": 42})
    assert list(tmp_path.glob("first-shoe*.json"))


def test_restart_unpauses(tmp_path):
    sim = make_sim(tmp_path)
    sim.pause({"paused": True})
    assert sim.restart({"seed": 42})["paused"] is False
