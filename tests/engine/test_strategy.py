import pytest

from bjds.engine import Move, Strategy, TableRules
from bjds.engine.cards import ACE

ALL = [Move.HIT, Move.STAND, Move.DOUBLE, Move.SPLIT]
NO_SPLIT = [Move.HIT, Move.STAND, Move.DOUBLE]


@pytest.fixture
def strat():
    return Strategy(TableRules())


# Published basic strategy, 8 decks, dealer stands on soft 17, no double
# after split, dealer has no hole card (doubles and splits lost to a BJ).
@pytest.mark.parametrize("low,soft,pair,up,move", [
    (16, False, None, 7, Move.HIT), (16, False, None, 6, Move.STAND),
    (12, False, None, 2, Move.HIT), (12, False, None, 4, Move.STAND),
    (11, False, None, 6, Move.DOUBLE), (11, False, None, 10, Move.HIT),
    (10, False, None, 9, Move.DOUBLE), (9, False, None, 3, Move.DOUBLE),
    (8, True, None, 6, Move.DOUBLE), (8, True, None, 9, Move.HIT), (8, True, None, 2, Move.STAND),
    (3, True, None, 5, Move.DOUBLE), (7, True, None, 3, Move.DOUBLE),
    (2, True, ACE, 6, Move.SPLIT), (16, False, 8, 9, Move.SPLIT), (18, False, 9, 7, Move.STAND),
    (20, False, 10, 6, Move.STAND), (4, False, 2, 3, Move.HIT), (4, False, 2, 4, Move.SPLIT),
    (12, False, 6, 2, Move.HIT), (12, False, 6, 3, Move.SPLIT), (8, False, 4, 5, Move.HIT),  # 8 decks: hard 8 always hits
])
def test_strategy_table_gives_the_published_move(strat, low, soft, pair, up, move):
    assert strat.decide(low, soft, pair, up, 0, ALL, use_count=False).move == move


def test_double_falls_back_to_hit_or_stand_when_not_allowed(strat):
    two = [Move.HIT, Move.STAND]
    assert strat.decide(11, False, None, 6, 0, two).move == Move.HIT
    assert strat.decide(8, True, None, 6, 0, two).move == Move.STAND


def test_16_against_10_is_hit_at_low_count_and_stand_at_high_count(strat):
    assert strat.decide(16, False, None, 10, -1, NO_SPLIT).move == Move.HIT
    d = strat.decide(16, False, None, 10, 2, NO_SPLIT)
    assert d.move == Move.STAND and d.deviation
    assert d.reason.startswith("stand, 16 against 10, count is +2")


def test_pair_of_tens_is_split_against_6_only_at_plus_4(strat):
    assert strat.decide(20, False, 10, 6, 4, ALL).move == Move.SPLIT
    assert strat.decide(20, False, 10, 6, 3, ALL).move == Move.STAND


def test_count_changes_that_need_a_hole_card_are_skipped_without_one(strat):
    assert strat.decide(11, False, None, ACE, 5, ALL).move == Move.HIT
    peek = Strategy(TableRules(no_hole_card=False))
    assert peek.decide(11, False, None, ACE, 1, ALL).move == Move.DOUBLE


def test_double_after_split_setting_changes_the_pair_table():
    das = Strategy(TableRules(double_after_split=True))
    assert das.decide(4, False, 2, 2, 0, ALL, use_count=False).move == Move.SPLIT
    assert Strategy(TableRules()).decide(4, False, 2, 2, 0, ALL, use_count=False).move == Move.HIT


def test_insurance_is_taken_only_at_true_count_plus_3(strat):
    assert strat.insurance(3)[0] is True
    assert strat.insurance(2)[0] is False
