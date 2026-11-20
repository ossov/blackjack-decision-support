from bjds.engine import EngineSettings
from bjds.engine.betting import recommend_bet


def test_no_edge_bets_the_table_minimum():
    assert recommend_bet(0, 10000, EngineSettings()).amount == 10


def test_high_count_bets_more_within_table_limits():
    amount = recommend_bet(5, 10000, EngineSettings()).amount
    assert 10 < amount <= 5000


def test_bankroll_below_the_minimum_bets_nothing():
    assert recommend_bet(5, 5, EngineSettings()).amount == 0
