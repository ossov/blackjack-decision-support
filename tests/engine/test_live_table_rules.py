"""Rules measured on the live table (FanDuel Blackjack 1, Nov 21, 2026)."""
from bjds.engine import Move, Strategy, TableRules
from bjds.engine.cards import ACE, TEN, parse_bubble
from bjds.engine.hands import HandState

ALL = [Move.HIT, Move.STAND, Move.DOUBLE, Move.SPLIT]


def feed(hand, *bubbles):
    cards = []
    for b in bubbles:
        cards += hand.apply(parse_bubble(b), []).cards
    return cards


# A bust keeps its total (in a red bubble) instead of showing "BUST".
def test_a_total_over_21_is_read_as_a_bust_with_its_total():
    b = parse_bubble("24")
    assert b.kind == "bust" and b.low == 24
    assert parse_bubble("31") is None            # no hand can bust past 30


def test_bust_total_gives_the_exact_card():
    h = HandState("h")
    assert feed(h, "10", "15", "24") == [10, 5, 9]
    assert h.busted and h.finished and h.uncertain == 0


def test_bust_total_that_does_not_fit_the_old_total_is_uncertain():
    h = HandState("h")
    assert feed(h, "10", "15", "27")[-1] is None   # +12 is not one card


# The dealer checks the face-down card for blackjack only when showing an ace.
def test_by_default_the_dealer_checks_only_under_an_ace():
    r = TableRules()
    assert r.no_hole_card is False and r.peek_on_ten is False


def test_against_an_ace_basic_strategy_is_the_normal_one():
    s = Strategy(TableRules())
    assert s.decide(2, True, ACE, ACE, 0, ALL, use_count=False).move == Move.SPLIT
    assert s.decide(16, False, 8, ACE, 0, ALL, use_count=False).move == Move.SPLIT
    assert s.decide(11, False, None, ACE, 5, ALL).move == Move.DOUBLE   # count change kept: the ace was checked


def test_against_a_ten_doubles_and_splits_avoid_an_unchecked_blackjack():
    s = Strategy(TableRules())
    assert s.decide(11, False, None, TEN, 0, ALL, use_count=False).move == Move.HIT
    assert s.decide(16, False, 8, TEN, 0, ALL, use_count=False).move == Move.HIT


# A finished soft hand's bubble drops the low value ("10/20" becomes "20"): that is not a card.
def engine_with(*readings):
    from bjds.engine import Engine, EngineSettings
    e = Engine(EngineSettings(player_seat=4))
    e.process({"stage": "betting", "hands": [], "dealer": {"bubble": None}})
    out = None
    for r in readings:
        out = e.process(r)
    return e, out


def reading(active, *hands, dealer=None):
    return {"stage": "player_turn", "active_hand": active,
            "hands": [{"hand_id": h, "seat": s, "bubble": b} for h, s, b in hands],
            "dealer": {"bubble": dealer}}


def test_a_soft_hand_that_is_not_being_played_cannot_take_a_card():
    # e.g. the hands left on the table when the round is settled
    e, out = engine_with(reading("seat3", ("seat3", 3, "9")), reading("seat3", ("seat3", 3, "10/20")),
                         reading("seat2", ("seat3", 3, "10/20"), ("seat2", 2, "12")),
                         reading(None, ("seat3", 3, "20"), ("seat2", 2, "12")))
    assert e.hands["seat3"].cards == [9, ACE]


def test_standing_on_a_soft_hand_is_not_a_new_card():
    e, out = engine_with(reading("seat3", ("seat3", 3, "9")), reading("seat3", ("seat3", 3, "10/20")),
                         reading("seat2", ("seat3", 3, "20"), ("seat2", 2, "12")))
    cards = [c for c in e.hands["seat3"].cards]
    assert cards == [9, ACE]


def test_a_ten_on_a_soft_hand_while_it_is_still_played_is_a_card():
    e, out = engine_with(reading("seat3", ("seat3", 3, "9")), reading("seat3", ("seat3", 3, "10/20")),
                         reading("seat3", ("seat3", 3, "20")))
    assert e.hands["seat3"].cards == [9, ACE, TEN]


def test_dealer_standing_on_soft_17_is_not_a_new_card():
    e, _ = engine_with(reading(None, dealer="6"), reading(None, dealer="7/17"), reading(None, dealer="17"))
    assert e.dealer.cards == [6, ACE]


def test_a_ten_on_a_dealer_soft_16_is_a_card():
    e, _ = engine_with(reading(None, dealer="5"), reading(None, dealer="6/16"), reading(None, dealer="16"))
    assert e.dealer.cards == [5, ACE, TEN]
