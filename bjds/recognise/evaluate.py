"""Measure how well bubbles are found and read, against frames the simulator saved with labels.

    python -m bjds.recognise.evaluate datasets/sim            # every saved frame
    python -m bjds.recognise.evaluate datasets/sim --unseen   # only frames the classifier never trained on
    python -m bjds.recognise.evaluate datasets/sim --count    # Recognition + Engine count vs the simulator
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2

from bjds.recognise.bubbles import BubbleReader
from bjds.recognise.layout import Layout


def evaluate(dataset: Path, unseen_only: bool = False) -> dict:
    files = sorted((dataset / "bubbles").glob("*.json"))
    if unseen_only:
        files = files[1::2]          # training with --half uses the other frames
    reader = BubbleReader(Layout.load())
    found = read = total = 0
    errors = []
    start = time.time()
    for f in files:
        data = json.loads(f.read_text())
        frame = cv2.imread(str(dataset / "images" / data["image"]))
        got = {(b.seat, b.hand): b for b in reader.read(frame)}
        want = {(t["seat"], t["hand"]): t for t in data["bubbles"]}
        for key, t in want.items():
            total += 1
            g = got.get(key)
            found += bool(g and g.kind == t["kind"])
            read += bool(g and g.text == t["text"])
            if not g or g.text != t["text"]:
                errors.append({"frame": f.stem, "seat": key[0], "hand": key[1], "truth": t["text"],
                               "read": g.text if g else None})
        for key in got.keys() - want.keys():
            errors.append({"frame": f.stem, "seat": key[0], "hand": key[1], "truth": None,
                           "read": got[key].text, "problem": "not a real bubble"})
    seconds = time.time() - start
    return {"frames": len(files), "bubbles": total, "found": found, "read_exactly": read,
            "found_pct": round(100 * found / max(total, 1), 2), "read_pct": round(100 * read / max(total, 1), 2),
            "text_reads": reader.ocr_calls, "tesseract_backups": reader.tesseract_calls,
            "ms_per_frame": round(1000 * seconds / max(len(files), 1), 1), "errors": errors}


def count_check(dataset: Path) -> dict:
    """Replay the saved frames in order through Recognition and the Engine, and compare the
    Engine's running count with the simulator's after every frame."""
    from bjds.engine import Engine, EngineSettings
    from bjds.recognise.table_reading import TableReader
    reader, table = BubbleReader(Layout.load()), TableReader()
    engine = Engine(EngineSettings(player_seat=4))
    agree = checked = 0
    shoe = last_round = None
    first_wrong = None
    seen_before = None
    cards = {"dealt": 0, "right": 0, "wrong": 0, "uncertain": 0, "missed": 0, "extra": 0}
    value = lambda rank: 1 if rank == "A" else 10 if rank in ("10", "J", "Q", "K") else int(rank)
    for f in sorted((dataset / "bubbles").glob("*.json")):
        data = json.loads(f.read_text())
        truth = data.get("truth")
        if not truth:
            continue
        if shoe is not None and truth["shoe"] != shoe:      # the simulator shuffled
            engine.counter.reset()
            seen_before = None
        shoe = truth["shoe"]
        if data.get("round") != last_round:                 # frames are saved only when a card lands,
            engine.process(table.reading([]))                # so show the Engine the empty table between rounds
            last_round = data.get("round")
        frame = cv2.imread(str(dataset / "images" / data["image"]))
        bubbles = reader.read(frame)
        found = []
        for _ in range(2):                                   # a value must be seen twice in a row
            out = engine.process(table.reading(bubbles))
            found += [c.get("card") for c in out.new_cards]
        # card by card: did the Engine name the card the simulator just turned face up?
        if seen_before is not None and truth["cards_seen"] == seen_before + 1:
            cards["dealt"] += 1
            want = value(truth["last_card"]["rank"])
            names = {"A": 1, "T": 10}
            got = [None if c in (None, "?") else names[c] if c in names else int(c) for c in found]
            if got == [want]:
                cards["right"] += 1
            elif not got:
                cards["missed"] += 1
            elif None in got:
                cards["uncertain"] += 1
            else:
                cards["wrong"] += 1
        elif seen_before is not None and truth["cards_seen"] == seen_before and found:
            cards["extra"] += len(found)
        seen_before = truth["cards_seen"]
        checked += 1
        if out.running_count == truth["running_count"]:
            agree += 1
        elif first_wrong is None:
            first_wrong = {"frame": f.stem, "engine": out.running_count, "simulator": truth["running_count"],
                           "notes": out.notes}
    cards["right_pct"] = round(100 * cards["right"] / max(cards["dealt"], 1), 2)
    return {"frames": checked, "cards": cards, "count_matches": agree,
            "match_pct": round(100 * agree / max(checked, 1), 2), "first_mismatch": first_wrong}


if __name__ == "__main__":
    if "--count" in sys.argv:
        print(json.dumps(count_check(Path(sys.argv[1])), indent=2))
        raise SystemExit(0)
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    r = evaluate(Path(sys.argv[1]), "--unseen" in sys.argv)
    print(json.dumps({k: v for k, v in r.items() if k != "errors"}, indent=2))
    for e in r["errors"][:20]:
        print(e)
