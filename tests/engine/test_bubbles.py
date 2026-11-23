import pytest

from bjds.engine.cards import hilo, parse_bubble


@pytest.mark.parametrize("text,kind,low,soft", [
    ("16", "total", 16, False), ("6/16", "total", 6, True), ("1/11", "total", 1, True),
    ("BJ", "bj", None, False), ("bust", "bust", None, False), (" 5 / 15 ", "total", 5, True),
])
def test_bubble_text_is_read_as_total_soft_total_bj_or_bust(text, kind, low, soft):
    b = parse_bubble(text)
    assert (b.kind, b.low, b.soft) == (kind, low, soft)


@pytest.mark.parametrize("bad", [None, "", "31", "6/15", "B", "J", "0"])  # 25 is now a bust total
def test_text_a_bubble_cannot_show_is_unreadable(bad):
    assert parse_bubble(bad) is None


def test_hilo_counts_2_to_6_plus_one_7_to_9_zero_tens_and_aces_minus_one():
    assert [hilo(v) for v in range(1, 11)] == [-1, 1, 1, 1, 1, 1, 0, 0, 0, -1]
