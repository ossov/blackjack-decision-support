import json

import pytest

from sim.cards import Shoe
from sim.rules import Rules
from sim.strategy import basic_strategy
from sim.cards import Card
from sim.hand import Hand
from sim.table import Table


def solo_table(ranks, history=None, **kw):
    """A table where only the player's seat (4) is occupied, dealt from a stacked shoe."""
    t = Table(shoe=Shoe.stacked(ranks), other_players=False, player_seat=4,
              balance=1000, history_path=history, **kw)
    return t


def play_to_decision(t, bet=10):
    t.run_until("betting")
    t.act("bet", amount=bet)
    t.act("deal")
    return t.run_until("player_turn", "insurance", "round_over")


def test_round_deals_player_then_dealer_twice():
    # order: player, dealer up, player, dealer hole
    t = solo_table(["10", "6", "7", "10"])
    play_to_decision(t)
    s = t.snapshot()
    assert [c["rank"] for c in s["seats"][3]["hands"][0]["cards"]] == ["10", "7"]
    assert s["dealer"]["cards"][0]["rank"] == "6"
    assert s["dealer"]["hole_hidden"] is True


def test_player_bubble_appears_after_first_card():
    t = solo_table(["10", "6", "7", "10"])
    t.run_until("betting")
    t.act("bet", amount=10)
    t.act("deal")
    t.step()  # first card to the player
    assert t.snapshot()["seats"][3]["hands"][0]["bubble"] == "10"


def test_hit_draws_one_card():
    t = solo_table(["10", "6", "2", "10", "5", "10"])
    play_to_decision(t)
    t.act("hit")
    t.step()
    assert t.snapshot()["seats"][3]["hands"][0]["bubble"] == "17"


def test_illegal_move_is_rejected():
    t = solo_table(["10", "6", "9", "10"])
    play_to_decision(t)
    with pytest.raises(ValueError):
        t.act("split")


def test_stand_on_19_against_dealer_16_who_busts_wins():
    # player 10,9 ; dealer 6,10 then draws 10 and busts
    t = solo_table(["10", "6", "9", "10", "10"])
    play_to_decision(t)
    t.act("stand")
    t.run_until("round_over")
    assert t.balance == 1010


def test_double_takes_one_card_and_doubles_the_bet():
    t = solo_table(["5", "9", "6", "8", "10"])
    play_to_decision(t)
    t.act("double")
    t.run_until("round_over")
    # player 21 v dealer 17
    assert t.balance == 1020


def test_split_makes_two_hands():
    t = solo_table(["8", "6", "8", "10", "3", "2", "10"])
    play_to_decision(t)
    t.act("split")
    t.step()
    hands = t.snapshot()["seats"][3]["hands"]
    assert len(hands) == 2
    assert [c["rank"] for c in hands[0]["cards"]] == ["8", "3"]


def test_insurance_offered_against_an_ace_and_pays_two_to_one():
    t = solo_table(["10", "A", "8", "K"])
    phase = play_to_decision(t)
    assert phase == "insurance"
    t.act("insurance", take=True)
    t.run_until("round_over")
    # main bet loses 10 to dealer blackjack, insurance of 5 wins 10
    assert t.balance == 1000


def test_player_blackjack_pays_three_to_two():
    t = solo_table(["A", "9", "K", "7"])
    play_to_decision(t)
    t.run_until("round_over")
    assert t.balance == 1015


def test_decision_timer_stands_for_the_player():
    t = solo_table(["10", "6", "9", "10", "10"], decision_seconds=10)
    play_to_decision(t)
    t.tick(10.1)
    assert t.run_until("round_over") == "round_over"
    assert t.balance == 1010


def test_cards_go_to_the_discard_tray_after_the_round():
    t = solo_table(["10", "6", "9", "10", "10"])
    play_to_decision(t)
    t.act("stand")
    t.run_until("round_over")
    t.run_until("betting")
    assert t.snapshot()["discard"]["count"] == 5


def test_fixed_bet_script_bets_the_same_every_round():
    t = Table(shoe=Shoe(seed=4), other_players=False, player_seat=4, balance=1000,
              auto_bet=25, auto_play=True)
    bets = []
    for _ in range(3):
        t.run_until("player_turn", "insurance", "dealer_turn", "round_over")
        bets.append(t.snapshot()["seats"][3]["bet"])
        t.run_until("round_over")
        t.run_until("betting")
    assert bets == [25, 25, 25]


def test_other_players_take_seats_and_play():
    t = Table(shoe=Shoe(seed=11), other_players=True, player_seat=4, balance=1000, auto_bet=10,
              auto_play=True)
    t.run_until("round_over")
    seats = t.snapshot()["seats"]
    others = [s for s in seats if s["occupied"] and not s["is_player"]]
    assert 1 <= len(others) <= 6
    assert all(s["hands"] and len(s["hands"][0]["cards"]) >= 2 for s in others)


def test_history_records_every_card_and_move(tmp_path):
    path = tmp_path / "history.jsonl"
    t = solo_table(["10", "6", "2", "10", "5", "10"], history=path)
    play_to_decision(t)
    t.act("hit")
    t.act("stand")
    t.run_until("round_over")
    events = [json.loads(line) for line in path.read_text().splitlines()]
    kinds = [e["event"] for e in events]
    assert kinds[0] == "session_start"
    assert kinds.count("card") == 6
    assert {"event": "move", "seat": 4, "hand": 0, "move": "hit", "source": "button"}.items() <= \
        next(e for e in events if e["event"] == "move").items()


def test_shuffle_after_cut_card_comes_out():
    t = Table(shoe=Shoe(seed=2, penetration=0.01), other_players=False, player_seat=4,
              balance=1000, auto_bet=10, auto_play=True)
    t.run_until("round_over")
    assert t.snapshot()["shoe"]["cut_card_out"]
    t.run_until("betting")
    s = t.snapshot()
    assert s["shoe"]["dealt"] == 0 and not s["shoe"]["cut_card_out"]
    assert s["discard"]["count"] == 0


def test_basic_strategy_samples():
    def h(*r):
        return Hand([Card(x, "S") for x in r])
    assert basic_strategy(h("10", "6"), Card("10", "S")) == "hit"
    assert basic_strategy(h("10", "6"), Card("6", "S")) == "stand"
    assert basic_strategy(h("5", "6"), Card("10", "S")) == "double"
    assert basic_strategy(h("8", "8"), Card("10", "S")) == "split"
    assert basic_strategy(h("A", "7"), Card("9", "S")) == "hit"
    assert basic_strategy(h("A", "7"), Card("2", "S")) == "stand"
    assert basic_strategy(h("A", "7"), Card("2", "S"), can_double=False) == "stand"
    assert basic_strategy(h("5", "6", "2"), Card("6", "S"), can_double=False) == "stand"


def test_snapshot_marks_a_bust_hand():
    t = solo_table(["10", "6", "6", "10", "K"])
    play_to_decision(t)
    t.act("hit")
    hand = t.snapshot()["seats"][3]["hands"][0]
    assert hand["bubble"] == "26" and hand["bust"] is True



def test_dealer_checks_for_blackjack_only_when_showing_an_ace():
    # dealer shows a 10 with an ace underneath: no check, so the player still plays the hand
    t = solo_table(["5", "10", "6", "A", "10"])
    assert play_to_decision(t) == "player_turn"


def test_ten_up_dealer_blackjack_takes_a_doubled_bet_after_players_act():
    t = solo_table(["5", "10", "6", "A", "10"])
    play_to_decision(t)
    t.act("double")
    t.run_until("round_over")
    # the doubled bet (20) is lost to the dealer's blackjack revealed at the end
    assert t.balance == 980


def test_ace_up_dealer_blackjack_ends_the_round_before_players_act():
    t = solo_table(["5", "A", "6", "K"])
    assert play_to_decision(t) == "insurance"
    t.act("insurance", take=False)
    assert t.run_until("player_turn", "round_over") == "round_over"


def test_second_split_hand_waits_before_its_card_arrives():
    # finishing the first split hand must not instantly deal the second hand's card
    t = solo_table(["8", "6", "8", "10", "3", "2", "10"])
    play_to_decision(t)
    t.act("split")
    t.act("stand")
    t.step()                         # no time has passed yet
    assert len(t.snapshot()["seats"][3]["hands"][1]["cards"]) == 1
    t.run_until("player_turn", "round_over")
    t.tick(5)
    t.step()
    assert len(t.snapshot()["seats"][3]["hands"][1]["cards"]) == 2


def test_dealer_soft_total_shows_both_values_while_the_dealer_is_still_drawing():
    # dealer shows a 5, turns over an ace (soft 16) and must still draw
    t = solo_table(["10", "5", "9", "A", "8"])
    play_to_decision(t)
    t.act("stand")
    t.run_until("dealer_turn")
    while not (not t.snapshot()["dealer"]["hole_hidden"] and len(t.snapshot()["dealer"]["cards"]) == 2):
        t.step(force=True)
    assert t.snapshot()["dealer"]["bubble"] == "6/16"
