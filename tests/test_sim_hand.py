from sim.cards import Card
from sim.hand import Hand, bubble_text
from sim.rules import Rules, legal_moves, dealer_should_hit, settle


def hand(*ranks, **kw):
    return Hand([Card(r, "S") for r in ranks], **kw)


def test_hard_total():
    assert hand("10", "6").total == 16
    assert not hand("10", "6").is_soft


def test_soft_total_counts_one_ace_as_eleven():
    h = hand("A", "5")
    assert h.total == 16 and h.is_soft


def test_ace_drops_to_one_when_eleven_would_bust():
    h = hand("A", "5", "9")
    assert h.total == 15 and not h.is_soft


def test_two_card_21_is_blackjack_but_not_after_split():
    assert hand("A", "K").is_blackjack
    assert not hand("A", "K", from_split=True).is_blackjack
    assert not hand("7", "7", "7").is_blackjack


def test_bubble_after_first_card_shows_its_value():
    assert bubble_text(hand("6")) == "6"
    assert bubble_text(hand("A")) == "1/11"


def test_bubble_shows_both_soft_totals_while_playing():
    assert bubble_text(hand("A", "5")) == "6/16"


def test_bubble_shows_best_total_once_hand_is_finished():
    assert bubble_text(hand("A", "5"), finished=True) == "16"


def test_bubble_for_blackjack():
    assert bubble_text(hand("A", "Q")) == "BJ"


def test_bust_bubble_shows_the_total():
    # the live table shows a bust as the total in a red bubble, not the word BUST
    assert bubble_text(hand("10", "6", "9")) == "25"


def test_bubble_is_empty_with_no_cards():
    assert bubble_text(hand()) == ""


def test_double_allowed_on_any_two_cards_only():
    r = Rules()
    assert "double" in legal_moves(hand("5", "6"), r, splits_used=0)
    assert "double" not in legal_moves(hand("2", "3", "4"), r, splits_used=0)


def test_no_double_after_split():
    assert "double" not in legal_moves(hand("5", "6", from_split=True), Rules(), splits_used=1)


def test_split_only_on_a_pair_and_only_once():
    r = Rules()
    assert "split" in legal_moves(hand("8", "8"), r, splits_used=0)
    assert "split" in legal_moves(hand("K", "10"), r, splits_used=0)
    assert "split" not in legal_moves(hand("8", "9"), r, splits_used=0)
    assert "split" not in legal_moves(hand("8", "8", from_split=True), r, splits_used=1)


def test_no_moves_on_21_or_bust():
    assert legal_moves(hand("10", "5", "6"), Rules(), splits_used=0) == []
    assert legal_moves(hand("10", "5", "9"), Rules(), splits_used=0) == []


def test_dealer_stands_on_soft_17():
    assert not dealer_should_hit(hand("A", "6"), Rules())
    assert dealer_should_hit(hand("10", "6"), Rules())


def test_blackjack_pays_three_to_two():
    assert settle(hand("A", "K", bet=10), hand("10", "8"), Rules()) == 15


def test_push_and_loss_and_win():
    r = Rules()
    assert settle(hand("10", "8", bet=10), hand("10", "8"), r) == 0
    assert settle(hand("10", "7", bet=10), hand("10", "8"), r) == -10
    assert settle(hand("10", "9", bet=10), hand("10", "8"), r) == 10


def test_doubled_hand_wins_double():
    assert settle(hand("5", "6", "10", bet=10, doubled=True), hand("10", "8"), Rules()) == 20


def test_player_bust_loses_even_if_dealer_busts():
    assert settle(hand("10", "6", "9", bet=10), hand("10", "6", "8"), Rules()) == -10


def test_dealer_blackjack_beats_player_21():
    assert settle(hand("7", "7", "7", bet=10), hand("A", "K"), Rules()) == -10


def test_a_soft_total_stays_split_while_its_hand_is_being_played():
    h = hand("A", "9")
    h.finished = True
    assert bubble_text(h, active=True) == "10/20"
    assert bubble_text(h) == "20"
