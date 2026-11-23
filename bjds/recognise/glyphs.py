"""A small character classifier for the text inside total bubbles.

General text readers (Tesseract, Apple Vision) often miss a lone digit in a small bubble. The
bubbles use one fixed font per table, so instead each character is cut out and matched against
labelled examples (a nearest-neighbour classifier). The examples come from the simulator's
saved bubbles, whose true text is known, so nobody labels anything by hand.

    python -m bjds.recognise.glyphs train datasets/sim     # build the model from saved frames
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

MODEL = Path(__file__).resolve().parent / "models" / "glyphs_sim.npz"
SIZE = 16
CHARS = "0123456789/BJ"


def binarise(frame: np.ndarray, box: tuple[int, int, int, int], light_text: bool) -> np.ndarray:
    """The bubble's text as white strokes on black, with everything outside the pill removed."""
    x, y, w, h = box
    g = cv2.cvtColor(frame[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
    if light_text:                      # white text on a dark bubble: flip it
        g = 255 - g
    m = np.zeros_like(g)
    r, s = h // 2, max(2, int(h * 0.16))
    cv2.rectangle(m, (r, s), (max(r, w - r), h - s), 255, -1)
    cv2.circle(m, (r, r), max(1, r - s), 255, -1)
    cv2.circle(m, (max(r, w - r), r), max(1, r - s), 255, -1)
    # fill the outside with the bubble's own colour so the threshold splits text from fill
    fill = int(np.median(g[m > 0])) if (m > 0).any() else 255
    g = np.where(m > 0, g, fill).astype(np.uint8)
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return bw


def segment(bw: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Cut the text into characters, splitting blobs too wide to be one character."""
    n, _, st, _ = cv2.connectedComponentsWithStats(bw, 8)
    parts = [st[i][:4] for i in range(1, n) if st[i][4] >= 5 and st[i][3] >= bw.shape[0] * 0.25]
    if not parts:
        return []
    char_h = max(p[3] for p in parts)
    out = []
    for x, y, w, h in sorted(parts, key=lambda p: p[0]):
        k = int(round(w / (0.62 * char_h))) if w > 0.85 * char_h else 1
        if k <= 1:
            out.append((int(x), int(y), int(w), int(h)))
            continue
        col = bw[y:y + h, x:x + w].sum(0)
        cuts = []
        for j in range(1, k):
            c = int(w * j / k)
            lo, hi = max(1, c - int(0.18 * char_h)), min(w - 1, c + int(0.18 * char_h))
            cuts.append(lo + int(np.argmin(col[lo:hi])) if hi > lo else c)
        edges = [0] + cuts + [int(w)]
        out += [(int(x + a), int(y), int(b - a), int(h)) for a, b in zip(edges[:-1], edges[1:]) if b > a]
    return out


def features(bw: np.ndarray, part: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = part
    g = bw[y:y + h, x:x + w]
    side = max(w, h)
    sq = np.zeros((side, side), np.uint8)
    sq[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = g
    f = cv2.resize(sq, (SIZE, SIZE), interpolation=cv2.INTER_AREA).astype(np.float32).ravel() / 255
    return np.concatenate([f, [w / h]]).astype(np.float32)


class GlyphModel:
    def __init__(self, x: np.ndarray, y: np.ndarray, max_distance: float):
        self.x, self.y, self.max_distance = x.astype(np.float32), y, max_distance

    @classmethod
    def load(cls, path: str | Path = MODEL) -> "GlyphModel":
        d = np.load(path)
        return cls(d["x"], d["y"], float(d["max_distance"]))

    def save(self, path: str | Path = MODEL) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, x=self.x.astype(np.float16), y=self.y, max_distance=self.max_distance)

    def predict(self, f: np.ndarray) -> tuple[str, float]:
        d = ((self.x - f) ** 2).sum(1)
        i = int(np.argmin(d))
        return str(self.y[i]), float(d[i])

    def candidates(self, f: np.ndarray, k: int = 3) -> list[tuple[str, float]]:
        """The k closest different characters for one cut-out, closest first."""
        d = ((self.x - f) ** 2).sum(1)
        best: dict[str, float] = {}
        for i in np.argsort(d):
            ch = str(self.y[i])
            if ch not in best:
                best[ch] = float(d[i])
                if len(best) == k:
                    break
        return list(best.items())

    def read_candidates(self, bw: np.ndarray, k: int = 3) -> list[list[tuple[str, float]]]:
        return [self.candidates(features(bw, part), k) for part in segment(bw)]

    def read(self, bw: np.ndarray) -> tuple[str, bool]:
        """Text of a binarised bubble, and whether every character was a confident match."""
        text, sure = "", True
        for part in segment(bw):
            ch, dist = self.predict(features(bw, part))
            text += ch
            sure = sure and dist <= self.max_distance
        return text, sure and bool(text)


# Window sizes the page may be shown at, relative to the 1080-pixel frame. Each training frame is
# also passed through these, so the classifier has seen the blur a browser's resizing adds.
SCALES = (1.0, 0.6, 0.8, 1.3, 1.8)


def _as_shown(frame: np.ndarray, scale: float) -> np.ndarray:
    if scale == 1.0:
        return frame
    small = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    return cv2.resize(small, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_AREA if scale > 1 else cv2.INTER_LINEAR)


def samples(dataset: Path, only=None, scales=SCALES):
    """(features, character) for every bubble whose cut-out characters match its known text."""
    for label in sorted((dataset / "bubbles").glob("*.json")):
        if only is not None and label.stem not in only:
            continue
        data = json.loads(label.read_text())
        original = cv2.imread(str(dataset / "images" / data["image"]))
        if original is None:
            continue
        for scale in scales:
            frame = _as_shown(original, scale)
            for b in data["bubbles"]:
                bw = binarise(frame, tuple(b["box"]), b["kind"] in ("bust", "dealer"))
                parts = segment(bw)
                if len(parts) == len(b["text"]):
                    for ch, part in zip(b["text"], parts):
                        yield features(bw, part), ch


def train(dataset: Path, per_char: int = 200, seed: int = 0, only=None) -> GlyphModel:
    by_char: dict[str, list[np.ndarray]] = defaultdict(list)
    for f, ch in samples(dataset, only):
        by_char[ch].append(f)
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for ch, fs in sorted(by_char.items()):
        pick = rng.permutation(len(fs))[:per_char]
        xs += [fs[i] for i in pick]
        ys += [ch] * len(pick)
    x, y = np.array(xs), np.array(ys)
    # confidence limit: well above the distance between examples of the same character
    nearest = []
    for i in range(len(x)):
        d = ((x - x[i]) ** 2).sum(1)
        d[i] = np.inf
        same = d[y == y[i]]
        if same.size and np.isfinite(same.min()):
            nearest.append(same.min())
    limit = float(np.percentile(nearest, 99) * 3) if nearest else 10.0
    return GlyphModel(x, y, limit)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "train":
        names = sorted(p.stem for p in (Path(sys.argv[2]) / "bubbles").glob("*.json"))
        # "--half" trains on every other frame and leaves the rest unseen, for testing
        only = set(names[::2]) if "--half" in sys.argv else None
        model = train(Path(sys.argv[2]), only=only)
        model.save()
        counts = {c: int((model.y == c).sum()) for c in CHARS}
        print(f"saved {MODEL} with {len(model.y)} examples {counts}, confidence limit {model.max_distance:.2f}")
    else:
        print(__doc__)
