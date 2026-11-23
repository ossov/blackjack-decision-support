"""Component 2: finding and reading the total bubbles.

The fixtures are simulator frames saved with each bubble's true text, colour and box
(tests/fixtures/recognise/*.json), so nothing is labelled by hand.
"""
import json
from pathlib import Path

import cv2
import pytest

from bjds.recognise.bubbles import BubbleReader, clean_text, find_bubbles
from bjds.recognise.layout import Layout

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "recognise"
LAYOUT = Layout.load()


def frames():
    for label in sorted(FIXTURES.glob("*.json")):
        data = json.loads(label.read_text())
        yield label.stem, cv2.imread(str(FIXTURES / data["image"])), data["bubbles"]


def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / (aw * ah + bw * bh - inter)


def test_there_are_fixtures_with_every_kind_of_bubble():
    kinds = {b["kind"] for _, _, bubbles in frames() for b in bubbles}
    assert {"normal", "active", "bust", "dealer"} <= kinds


@pytest.mark.parametrize("name,frame,truth", list(frames()))
def test_finds_every_bubble_with_its_seat_and_colour(name, frame, truth):
    found = find_bubbles(frame, LAYOUT)
    assert len(found) == len(truth), name
    for t in truth:
        match = max(found, key=lambda f: iou(f.box, t["box"]))
        assert iou(match.box, t["box"]) > 0.5, (name, t)
        assert match.seat == t["seat"] and match.hand == t["hand"] and match.kind == t["kind"], (name, t, match)


@pytest.mark.parametrize("name,frame,truth", list(frames()))
def test_reads_every_bubble_exactly(name, frame, truth):
    reader = BubbleReader(LAYOUT)
    got = {(b.seat, b.hand): b.text for b in reader.read(frame)}
    want = {(t["seat"], t["hand"]): t["text"] for t in truth}
    assert got == want, name


def test_rejects_text_a_bubble_cannot_show():
    assert clean_text("6/16") == "6/16"
    assert clean_text("BJ") == "BJ"
    assert clean_text("24") == "24"        # a bust keeps its total
    assert clean_text("6/19") is None      # soft totals are always 10 apart
    assert clean_text("0") is None
    assert clean_text("7a") is None


def test_an_unchanged_bubble_is_not_read_again():
    name, frame, _ = next(frames())
    reader = BubbleReader(LAYOUT)
    reader.read(frame)
    calls = reader.ocr_calls
    reader.read(frame.copy())
    assert reader.ocr_calls == calls


def test_an_impossible_reading_is_fixed_with_the_next_closest_characters():
    from bjds.recognise.bubbles import decode
    # each character's candidates, closest first: "6/18" cannot exist, "8/18" can
    cands = [[("6", 1.0), ("8", 1.4)], [("/", 0.2)], [("1", 0.1)], [("8", 0.3)]]
    assert decode(cands, limit=5.0) == "8/18"


def test_decoding_gives_up_when_no_valid_reading_is_close_enough():
    from bjds.recognise.bubbles import decode
    cands = [[("6", 1.0), ("8", 9.0)], [("/", 0.2)], [("1", 0.1)], [("8", 0.3)]]
    assert decode(cands, limit=5.0) is None


def moved_dealer_bubble(dx, dy):
    """A fixture frame with its dealer bubble moved by (dx, dy) frame pixels, the way a slightly
    different capture area or camera position shifts it on the real table."""
    for _, frame, truth in frames():
        dealer = [t for t in truth if t["kind"] == "dealer"]
        if dealer:
            break
    t = dealer[0]
    x, y, w, h = t["box"]
    m = 3
    patch = frame[y - m:y + h + m, x - m:x + w + m].copy()
    ring = frame[y - 2 * m:y + h + 2 * m, x - 2 * m:x + w + 2 * m]
    frame[y - m:y + h + m, x - m:x + w + m] = ring.reshape(-1, 3).mean(0)   # paint the old spot over
    frame[y - m + dy:y + h + m + dy, x - m + dx:x + w + m + dx] = patch
    return frame, t["text"]


@pytest.mark.parametrize("dx,dy", [(0, -30), (-25, -30), (0, -50), (-40, -50), (0, 30), (25, 0)])
def test_finds_the_dealer_bubble_when_it_sits_off_its_spot(dx, dy):
    frame, text = moved_dealer_bubble(dx, dy)
    dealer = [b for b in BubbleReader(LAYOUT).read(frame) if b.seat == 0]
    assert [b.text for b in dealer] == [text]
    assert dealer[0].kind == "dealer"


def test_a_black_object_without_a_ring_or_text_is_not_the_dealer_bubble():
    # the real table has a black puck on the felt near the dealer's bubble
    for _, frame, truth in frames():
        if any(t["kind"] == "dealer" for t in truth):
            break
    sx, sy = LAYOUT.bubble_spots()[0]
    cv2.ellipse(frame, (int(sx) - 60, int(sy) - 35), (15, 13), 0, 0, 360, (12, 8, 14), -1)
    dealer = [b for b in find_bubbles(frame, LAYOUT) if b.seat == 0]
    assert len(dealer) == 1
