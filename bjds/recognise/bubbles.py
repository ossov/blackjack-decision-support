"""Find the total bubbles in a frame and read their text.

1. Colour masks pick out the bubble fills measured on the live table: light grey (a hand in
   play), bright green (the hand being played), dark red (a bust, still showing the total)
   and the dealer's black bubble.
2. Each blob is given to the nearest seat's expected bubble spot; two at one seat are a split,
   and the right-hand one is hand 0 (it is played first).
3. The text is read by a small character classifier trained on the simulator's labelled bubbles
   (see glyphs.py). Tesseract is the backup when the classifier is not sure. Reading runs only
   on bubbles whose pixels changed since the last frame.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import cv2
import numpy as np

from bjds.recognise.glyphs import GlyphModel, binarise
from bjds.recognise.layout import Layout

TESS_CONFIG = "--psm 7 -c tessedit_char_whitelist=0123456789/BJ"
_SOFT = re.compile(r"^(\d{1,2})/(\d{1,2})$")


@dataclass
class Bubble:
    seat: int            # 1-7, or 0 for the dealer
    hand: int            # 0 = first (right-hand) hand of a seat
    kind: str            # "normal", "active", "bust" or "dealer"
    box: tuple[int, int, int, int]   # x, y, w, h in frame pixels
    text: str | None = None
    source: str = ""     # "classifier" or "tesseract"


def clean_text(raw: str) -> str | None:
    """Keep only text a bubble can actually show; anything else is unreadable (None)."""
    t = raw.strip().replace(" ", "").replace("\n", "")
    if t == "BJ":
        return t
    m = _SOFT.match(t)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return t if hi - lo == 10 and 1 <= lo <= 11 else None
    if t.isdigit() and not t.startswith("0") and 1 <= int(t) <= 30:
        return t
    return None


def decode(candidates: list[list[tuple[str, float]]], limit: float) -> str | None:
    """The closest reading that a bubble can actually show.

    candidates holds, for each cut-out character, its closest matches with their distances. The
    best guess is tried first; if it is impossible (for example "6/18", since soft totals are
    always 10 apart), the next-closest characters are tried, keeping every character within
    the confidence limit.
    """
    from itertools import product
    if not candidates:
        return None
    options = [[c for c in chars if c[1] <= limit] for chars in candidates]
    if any(not o for o in options):
        return None
    best = None
    for combo in product(*options):
        text = clean_text("".join(ch for ch, _ in combo))
        if text:
            cost = sum(d for _, d in combo)
            if best is None or cost < best[0]:
                best = (cost, text)
    return best[1] if best else None


def _masks(frame: np.ndarray) -> dict[str, np.ndarray]:
    b, g, r = (frame[..., i].astype(np.int16) for i in range(3))
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    return {
        "normal": (mn >= 180) & (mx <= 228) & (mx - mn <= 16),
        "active": (g >= 170) & (r <= 140) & (b <= 110) & (g - r >= 80),
        "bust": (r >= 80) & (r <= 170) & (g <= 40) & (b <= 70),
        "dealer": mx <= 30,
    }


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """Fill the holes the digits leave inside a bubble's fill."""
    m = mask.astype(np.uint8) * 255
    padded = cv2.copyMakeBorder(255 - m, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=255)
    flood = padded.copy()
    cv2.floodFill(flood, None, (0, 0), 0)              # everything reachable from outside
    holes = flood[1:-1, 1:-1]
    return m | holes


DEALER_REACH = 1.6     # how far, in bubble heights, the dealer bubble may sit above or below its spot


def _is_dealer_bubble(frame: np.ndarray, filled: np.ndarray, box: tuple[int, int, int, int]) -> bool:
    """The dealer's black bubble has a light grey ring and white text; other black things on the
    table (such as the puck beside the discard tray) have neither.
    Measured: bubbles have ring brightness 99-118 and 6-15 % text, the puck 24-36 and 0 %."""
    x, y, w, h = box
    pad = 4
    y0, x0 = max(0, y - pad), max(0, x - pad)
    region = filled[y0:y + h + pad, x0:x + w + pad] > 0
    darkest = frame[y0:y + h + pad, x0:x + w + pad].min(2)
    ring = cv2.dilate(region.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    ring &= ~region
    inside = filled[y:y + h, x:x + w] > 0
    text = (frame[y:y + h, x:x + w].min(2) >= 140)[inside]
    return bool(ring.any() and darkest[ring].mean() >= 70 and text.size and text.mean() >= 0.03)


def find_bubbles(frame: np.ndarray, layout: Layout) -> list[Bubble]:
    spots = layout.bubble_spots()
    h = layout.bubble_height
    reach = layout.split_offset + h                       # how far a bubble can sit from its spot
    lift = layout.active_lift
    side = max(3, int(h * 0.45)) | 1
    opening = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (side, side))
    found: list[Bubble] = []
    for kind, mask in _masks(frame).items():
        filled = _fill_holes(mask)                         # the digits are holes in the fill
        m = cv2.morphologyEx(filled, cv2.MORPH_OPEN, opening)   # drop thin lines touching the bubble
        n, labels, stats, centres = cv2.connectedComponentsWithStats(m, 8)
        for i in range(1, n):
            x, y, w, hh, area = stats[i]
            if not (0.75 * h <= hh <= 1.3 * h and 0.85 * hh <= w <= 3.2 * hh):
                continue
            if area < 0.6 * w * hh:                        # a filled pill, not an outline
                continue
            # a bubble is round, so the corners of its box are empty; a lit card face is not
            c = max(2, int(hh * 0.18))
            blob = filled[y:y + hh, x:x + w] > 0            # the shape before smoothing
            corners = [blob[:c, :c], blob[:c, -c:], blob[-c:, :c], blob[-c:, -c:]]
            if np.mean([q.mean() for q in corners]) > 0.35:
                continue
            if kind == "normal":
                # a bubble is neutral grey; a lit card face picks up a purple tint from the felt
                inside = frame[y:y + hh, x:x + w][mask[y:y + hh, x:x + w]].astype(np.float32)
                if inside.size and np.ptp(inside.mean(0)) > 8:
                    continue
            cx, cy = centres[i]
            if kind == "dealer":
                # only the dealer has a black bubble, so it is the dealer's wherever it sits near
                # its spot (on the real table it sits higher than the traced spot, and a slightly
                # different capture area moves it further)
                sx, sy = spots[0]
                if abs(cx - sx) > reach or abs(cy - sy) > DEALER_REACH * h:
                    continue
                if not _is_dealer_bubble(frame, filled, (x, y, w, hh)):
                    continue
                found.append(Bubble(0, 0, kind, (int(x), int(y), int(w), int(hh))))
                continue
            seat, dist = min(((s, float(np.hypot(cx - sx, cy - sy))) for s, (sx, sy) in spots.items() if s),
                             key=lambda p: p[1])
            sx, sy = spots[seat]
            # bubbles sit on their spot, shifted sideways for a split and lifted for the active hand
            if abs(cx - sx) > reach or not (sy - lift - 0.5 * h <= cy <= sy + 0.5 * h):
                continue
            found.append(Bubble(seat, 0, kind, (int(x), int(y), int(w), int(hh))))
    by_seat: dict[int, list[Bubble]] = {}
    for b in found:
        by_seat.setdefault(b.seat, []).append(b)
    for bubbles in by_seat.values():               # a split: the right-hand bubble is hand 0
        bubbles.sort(key=lambda b: -b.box[0])
        for i, b in enumerate(bubbles):
            b.hand = i
    return sorted(found, key=lambda b: (b.seat, b.hand))


def _tesseract(bw: np.ndarray) -> str:
    import pytesseract
    img = 255 - bw                                # dark text on white
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
    img = cv2.copyMakeBorder(img, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return pytesseract.image_to_string(img, config=TESS_CONFIG)


class BubbleReader:
    """Reads every bubble in a frame, skipping bubbles whose pixels did not change."""

    def __init__(self, layout: Layout, model: GlyphModel | None = None):
        self.layout = layout
        self.model = model or GlyphModel.load()
        self.cache: dict[str, tuple[str | None, str]] = {}
        self.ocr_calls = 0
        self.tesseract_calls = 0

    def _read_one(self, frame: np.ndarray, b: Bubble) -> tuple[str | None, str]:
        bw = binarise(frame, b.box, b.kind in ("bust", "dealer"))
        text, sure = self.model.read(bw)
        if sure and clean_text(text):
            return clean_text(text), "classifier"
        fixed = decode(self.model.read_candidates(bw), self.model.max_distance)
        if fixed:
            return fixed, "classifier"
        self.tesseract_calls += 1
        backup = clean_text(_tesseract(bw))
        return (backup, "tesseract") if backup else (clean_text(text) if sure else None, "classifier")

    def read(self, frame: np.ndarray) -> list[Bubble]:
        bubbles = find_bubbles(frame, self.layout)
        for b in bubbles:
            x, y, w, h = b.box
            key = b.kind + hashlib.blake2b(frame[y:y + h, x:x + w].tobytes(), digest_size=12).hexdigest()
            if key not in self.cache:
                self.ocr_calls += 1
                self.cache[key] = self._read_one(frame, b)
                if len(self.cache) > 512:
                    self.cache.pop(next(iter(self.cache)))
            b.text, b.source = self.cache[key]
        return bubbles
