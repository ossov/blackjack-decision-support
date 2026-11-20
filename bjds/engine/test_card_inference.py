from bjds.engine.cards import ACE, TEN, parse_bubble
from bjds.engine.hands import HandState


def feed(hand, *bubbles):
    cards = []
    for b in bubbles:
        cards += hand.apply(parse_bubble(b), []).cards
    return cards


def test_new_card_is_new_total_minus_old_total_with_ace_as_one():
    assert feed(HandState("h"), "5", "6/16", "12", "20") == [5, ACE, 6, 8]


def test_lone_ace_shown_as_11_is_an_ace():
    assert feed(HandState("h"), "11") == [ACE]


def test_soft_21_shown_as_plain_21_gives_the_right_card():
    assert feed(HandState("h"), "5", "6/16", "21", "21") == [5, ACE, 5]
    assert feed(HandState("h"), "5", "10", "21") == [5, 5, ACE]
    assert feed(HandState("h"), "5", "12", "21") == [5, 7, 9]


def test_blackjack_bubble_gives_the_card_that_completes_21():
    assert feed(HandState("h"), "10", "BJ") == [10, ACE]
    assert feed(HandState("h"), "1/11", "BJ") == [ACE, TEN]


def test_bust_from_12_must_be_a_ten():
    assert feed(HandState("h"), "12", "BUST")[-1] == TEN


def test_bust_with_several_possible_cards_is_marked_uncertain():
    h = HandState("h")
    assert feed(h, "10", "15", "BUST")[-1] is None
    assert h.uncertain == 1


def test_bust_card_is_taken_from_its_picture():
    h = HandState("h")
    feed(h, "10", "15")
    assert h.apply(parse_bubble("BUST"), [8]).cards == [8]


def test_two_cards_landing_at_once_are_uncertain_without_pictures():
    assert feed(HandState("h"), "15") == [None, None]


def test_two_cards_landing_at_once_are_read_from_pictures():
    assert HandState("h").apply(parse_bubble("15"), [7, 8]).cards == [7, 8]


def test_bubble_wins_when_the_picture_disagrees():
    h = HandState("h")
    feed(h, "5")
    inf = h.apply(parse_bubble("12"), [6])
    assert inf.cards == [7] and "used the bubble" in inf.note


def test_total_that_goes_down_is_ignored():
    h = HandState("h")
    feed(h, "14")
    assert h.apply(parse_bubble("12"), []).cards == [] and h.low == 14


def test_misread_bubble_falls_back_to_the_picture():
    h = HandState("h")
    feed(h, "14")
    assert h.apply(parse_bubble("12"), [5]).cards == [5] and h.low == 19
