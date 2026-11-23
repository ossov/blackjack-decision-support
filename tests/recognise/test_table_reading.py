"""Turning bubbles into the table reading the Engine takes (contracts/README.md)."""
from bjds.recognise.bubbles import Bubble
from bjds.recognise.table_reading import TableReader


def bubbles(*items):
    return [Bubble(seat, hand, kind, (0, 0, 10, 10), text) for seat, hand, kind, text in items]


def test_a_value_is_passed_on_only_after_two_matching_frames():
    r = TableReader()
    first = r.reading(bubbles((4, 0, "normal", "12")))
    assert first["hands"] == []                         # seen once: not trusted, so not reported yet
    second = r.reading(bubbles((4, 0, "normal", "12")))
    assert second["hands"][0]["bubble"] == "12"


def test_while_a_value_is_changing_the_old_one_is_not_passed_on():
    r = TableReader()
    for _ in range(2):
        r.reading(bubbles((4, 0, "normal", "12")))
    changing = r.reading(bubbles((4, 0, "normal", "10")))
    assert changing["hands"][0]["bubble"] is None       # not yet confirmed, and 12 is out of date
    assert r.reading(bubbles((4, 0, "normal", "10")))["hands"][0]["bubble"] == "10"


def test_a_bubble_that_was_never_read_is_not_reported_as_a_hand():
    r = TableReader()
    for _ in range(3):
        out = r.reading(bubbles((4, 0, "normal", "13"), (4, 1, "normal", None)))
    assert [h["hand_id"] for h in out["hands"]] == ["seat4"]


def test_hands_get_stable_ids_and_a_split_names_its_parent():
    r = TableReader()
    for _ in range(2):
        out = r.reading(bubbles((4, 0, "normal", "8"), (4, 1, "active", "3")))
    ids = {h["hand_id"]: h for h in out["hands"]}
    assert set(ids) == {"seat4", "seat4b"}
    assert ids["seat4b"]["split_of"] == "seat4" and ids["seat4"]["seat"] == 4
    assert out["active_hand"] == "seat4b"


def test_dealer_bubble_goes_in_the_dealer_field():
    r = TableReader()
    for _ in range(2):
        out = r.reading(bubbles((0, 0, "dealer", "10"), (2, 0, "normal", "15")))
    assert out["dealer"]["bubble"] == "10"
    assert [h["seat"] for h in out["hands"]] == [2]


def test_an_empty_table_is_the_betting_stage():
    r = TableReader()
    assert r.reading([])["stage"] == "betting"
    for _ in range(2):
        out = r.reading(bubbles((3, 0, "active", "14")))
    assert out["stage"] == "player_turn"


def test_reading_has_every_field_the_engine_expects():
    out = TableReader().reading(bubbles((1, 0, "normal", "9")))
    assert {"stage", "hands", "dealer", "discard_tray_height", "cut_card_out", "active_hand", "timestamp"} <= set(out)
