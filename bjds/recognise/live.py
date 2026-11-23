"""Watch Recognition read the table live, in its own window.

    python -m bjds.recognise.live                 # first run: drag a box around the video area
    python -m bjds.recognise.live --select        # pick the area again (e.g. after moving the window)
    python -m bjds.recognise.live --check http://127.0.0.1:8765   # also compare with the simulator
    (the log of every count change is logs/live_check.jsonl, with a picture at each count mistake)

Each bubble gets a box in its colour with the text that was read. The readings go through the
Engine (Component 3), which works out each card and keeps the Hi-Lo count shown at the top.
With --check, a bubble that does not match what the simulator really shows is drawn in red
with the true value beside it, and the simulator's own count is shown beside the Engine's.
macOS asks once for Screen Recording permission for the app that runs this (your terminal app).
Keys: Q or Esc quits, S picks the area again, R (or the Reset count button) resets the count:
with --check it takes the simulator's count again at the next empty table, otherwise it goes to 0.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from bjds.engine import Engine, EngineSettings
from bjds.recognise.bubbles import BubbleReader
from bjds.recognise.capture import ScreenGrabber, frame_to_stage, load_region, save_region, stage_to_frame
from bjds.recognise.layout import Layout
from bjds.recognise.live_check import LiveCheck
from bjds.recognise.table_reading import TableReader

COLOURS = {"normal": (210, 210, 210), "active": (60, 230, 60), "bust": (60, 60, 220), "dealer": (255, 200, 80)}
# count line: green = same as the simulator, yellow = a card just landed and is still being read,
# red = still different after 3 seconds (a real mistake, logged with a picture)
STATUS_COLOURS = {"match": (80, 230, 80), "catching_up": (0, 220, 255), "mismatch": (60, 60, 255)}
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
WINDOW = "Recognition (live)"
FONT = cv2.FONT_HERSHEY_SIMPLEX
RESET_LABEL = "RESET COUNT (R)"


def select_region(delay: int = 5) -> dict:
    import mss
    print("Switch to the simulator (or live table) window now, so it is in front.")
    for n in range(delay, 0, -1):
        print(f"  taking a screenshot in {n}...", flush=True)
        time.sleep(1)
    with mss.mss() as sct:
        mon = sct.monitors[1]
        shot = cv2.cvtColor(np.asarray(sct.grab(mon)), cv2.COLOR_BGRA2BGR)
    ratio = shot.shape[1] / mon["width"]                    # 2 on a Retina screen
    view = cv2.resize(shot, None, fx=0.5, fy=0.5)
    print("Drag a box around the table's video area (inside the side panels), then press Enter.")
    x, y, w, h = cv2.selectROI("Select the video area", view, showCrosshair=False)
    cv2.destroyWindow("Select the video area")
    if w == 0 or h == 0:
        raise SystemExit("No area selected.")
    k = 2 / ratio                                           # view pixels -> screen points
    region = {"left": mon["left"] + int(x * k), "top": mon["top"] + int(y * k),
              "width": int(w * k), "height": int(h * k)}
    save_region(region)
    print(f"Saved the area to config/capture.json: {region}")
    return region


def sim_state(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/state", timeout=0.3) as r:
            return json.loads(r.read())
    except Exception:
        return None


def truth_bubbles(s: dict | None) -> dict | None:
    if s is None:
        return None
    out = {(0, 0): s["dealer"]["bubble"]} if s["dealer"]["bubble"] else {}
    for seat in s["seats"]:
        for i, h in enumerate(seat["hands"]):
            if h["bubble"]:
                out[(seat["seat"], i)] = h["bubble"]
    return out


def count_lines(result, cards_seen: int, truth: dict | None = None) -> list[str]:
    """The count rows at the top of the window: the Engine's count, then the simulator's under it."""
    lines = [f"DETECTED   running {result.running_count:+d}   true {result.true_count:+.2f}"
             f"   cards seen {cards_seen}   uncertain {result.uncertain_cards}"]
    if truth:
        lines.append(f"SIMULATOR  running {truth['running_count']:+d}   true {truth['true_count']:+.2f}"
                     f"   cards seen {truth['cards_seen']}")
    return lines


def reset_button(width: int, scale: float) -> tuple[int, int, int, int]:
    """The Reset count button's box (x0, y0, x1, y1) at the right end of the status row."""
    bar = int(40 * scale * 2)
    (tw, _), _ = cv2.getTextSize(RESET_LABEL, FONT, 0.45 * scale * 2, max(1, int(2 * scale)))
    pad = int(10 * scale)
    x1 = width - pad
    return x1 - tw - 2 * pad, int(6 * scale), x1, bar - int(6 * scale)


def inside(rect: tuple[int, int, int, int], x: int, y: int) -> bool:
    x0, y0, x1, y1 = rect
    return x0 <= x <= x1 and y0 <= y <= y1


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Watch Recognition read the table live.")
    p.add_argument("--select", action="store_true", help="pick the video area again")
    p.add_argument("--check", metavar="URL", help="simulator address, to compare with what it really shows")
    p.add_argument("--fps", type=float, default=5)
    args = p.parse_args(argv)

    region = select_region() if args.select or not load_region() else load_region()
    grabber = ScreenGrabber(region)
    reader = BubbleReader(Layout.load())
    table = TableReader()
    engine = Engine(EngineSettings(player_seat=4))
    check = LiveCheck(LOG_DIR) if args.check else None
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    mouse = {"button": None, "clicked": False}

    def on_mouse(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN and mouse["button"] and inside(mouse["button"], x, y):
            mouse["clicked"] = True

    cv2.setMouseCallback(WINDOW, on_mouse)
    reads = matches = 0
    while True:
        start = time.time()
        stage = grabber.grab()
        bubbles = reader.read(stage_to_frame(stage))
        reading = table.reading(bubbles)
        state = sim_state(args.check) if args.check else None
        truth = truth_bubbles(state)
        check_status = None
        if check and state and state.get("truth"):
            # starts from the simulator's count at an empty table, and again after each shuffle
            # (Recognition does not read the discard tray yet); logs every change to logs/
            # a restarted simulator starts again at shoe 1, so tell shoes apart by history file too
            tr = dict(state["truth"], shoe=f"{state.get('history')}#{state['truth']['shoe']}")
            result, check_status = check.step(engine, reading, tr, stage)
        else:
            result = engine.process(reading)
        view = stage.copy()
        sh, sw = stage.shape[:2]
        scale = sh / 1080
        for b in bubbles:
            x, y, w, h = b.box
            (x0, y0), (x1, y1) = frame_to_stage(x, y, (sw, sh)), frame_to_stage(x + w, y + h, (sw, sh))
            colour = COLOURS[b.kind]
            label = f"{'D' if b.seat == 0 else b.seat}{'.' + str(b.hand) if b.hand else ''}: {b.text or '?'}"
            if truth is not None:
                real = truth.get((b.seat, b.hand))
                reads += 1
                matches += real == b.text
                if real != b.text:
                    colour, label = (0, 0, 255), label + f"  (sim: {real})"
            cv2.rectangle(view, (int(x0), int(y0)), (int(x1), int(y1)), colour, max(2, int(3 * scale)))
            cv2.putText(view, label, (int(x0), int(y0) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6 * scale * 2,
                        colour, max(1, int(2 * scale)), cv2.LINE_AA)
        took = (time.time() - start) * 1000
        status = f"{len(bubbles)} bubbles  |  {took:.0f} ms"
        if truth is not None and reads:
            status += f"  |  bubbles match sim {100 * matches / reads:.1f}% ({reads} reads)"
        if check:
            status += f"  |  count mistakes {check.mismatches}"
        colour = (255, 255, 255)
        if result is None:
            rows = ["WAITING for the table to clear, to start in sync with the simulator's count"]
        else:
            rows = count_lines(result, engine.counter.cards_seen, state and state.get("truth"))
            if state and state.get("truth"):
                colour = STATUS_COLOURS.get(check_status, colour)
        bar = int(40 * scale * 2)
        cv2.rectangle(view, (0, 0), (sw, (1 + len(rows)) * bar), (0, 0, 0), -1)
        for i, (text, c) in enumerate([(status, (255, 255, 255))] + [(r, colour) for r in rows]):
            cv2.putText(view, text, (12, i * bar + int(28 * scale * 2)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7 * scale * 2, c, max(1, int(2 * scale)), cv2.LINE_AA)
        x0, y0, x1, y1 = mouse["button"] = reset_button(sw, scale)
        cv2.rectangle(view, (x0, y0), (x1, y1), (70, 70, 70), -1)
        cv2.rectangle(view, (x0, y0), (x1, y1), (200, 200, 200), max(1, int(scale)))
        (_, th), _ = cv2.getTextSize(RESET_LABEL, FONT, 0.45 * scale * 2, max(1, int(2 * scale)))
        cv2.putText(view, RESET_LABEL, (x0 + int(10 * scale), (y0 + y1 + th) // 2), FONT, 0.45 * scale * 2,
                    (255, 255, 255), max(1, int(2 * scale)), cv2.LINE_AA)
        cv2.imshow(WINDOW, view)
        key = cv2.waitKey(max(1, int(1000 / args.fps - took))) & 0xFF
        if key in (ord("q"), 27):
            break
        if key == ord("s"):
            grabber = ScreenGrabber(select_region())
        if key == ord("r") or mouse["clicked"]:
            mouse["clicked"] = False
            if check:
                check.resync()           # the Engine takes the simulator's count at the next empty table
            else:
                engine.counter.reset()   # e.g. a new shoe on the real table
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
