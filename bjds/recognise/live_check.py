"""Check the Engine's count against the simulator while the live viewer runs.

The simulator keeps dealing to the other seats whether or not the viewer is open, so the Engine
cannot start at 0. It waits for an empty table (between rounds), takes the simulator's count at
that moment, and counts from there. After a shuffle it does the same again.

The simulator's count changes the moment a card lands, but Recognition needs the bubble drawn and
read twice, so a short gap is normal ("catching_up"). Only a gap that lasts `settle_seconds` is a
mistake ("mismatch"). Every change is written to `live_check.jsonl`, and the frame is saved as a
picture at each new mistake, so the card that went wrong can be found.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


def _empty(reading: dict) -> bool:
    return not reading["hands"] and not (reading.get("dealer") or {}).get("bubble")


class LiveCheck:
    def __init__(self, log_dir: str | Path, settle_seconds: float = 3.0, clock=time.time):
        self.dir = Path(log_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "live_check.jsonl"
        self.settle = settle_seconds
        self.clock = clock
        self.synced = False
        self.shoe = None
        self.since = None          # when the counts started to differ
        self.mismatches = 0        # since the last reset
        self.pictures = 0          # never reset, so no picture is overwritten
        self._last_key = None

    def _write(self, event: str, **fields) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps({"event": event, "t": round(self.clock(), 2), **fields}) + "\n")

    def resync(self) -> None:
        """Reset button: take the simulator's count again at the next empty table, and clear the tally."""
        self.synced, self.since, self.mismatches, self._last_key = False, None, 0, None
        self._write("resync")

    def step(self, engine, reading: dict, truth: dict, image=None):
        """Feed one reading to the Engine. Returns (Engine output or None, status)."""
        if self.synced and truth["shoe"] != self.shoe:
            self.synced = False
            self._write("new_shoe", shoe=truth["shoe"])
        if not self.synced:
            if not _empty(reading):
                return None, "waiting"
            engine.counter.reset()
            engine.counter.running = truth["running_count"]
            engine.counter.cards_seen = truth["cards_seen"]
            self.synced, self.shoe, self.since = True, truth["shoe"], None
            self._write("sync", shoe=truth["shoe"], running=truth["running_count"],
                        cards_seen=truth["cards_seen"])

        result = engine.process(reading)
        if result.running_count == truth["running_count"]:
            self.since, status = None, "match"
        else:
            if self.since is None:
                self.since = self.clock()
            status = "mismatch" if self.clock() - self.since >= self.settle else "catching_up"

        key = (json.dumps([reading["active_hand"], reading["hands"], reading["dealer"]], sort_keys=True),
               result.running_count, truth["running_count"], status)
        if key != self._last_key:
            if status == "mismatch" and (self._last_key is None or self._last_key[3] != "mismatch"):
                self.mismatches += 1
                self.pictures += 1
                picture = self.dir / f"live_check_mismatch_{self.pictures}.png"
                if image is not None:
                    import cv2
                    cv2.imwrite(str(picture), image)
                self._write("mismatch", n=self.pictures, engine=result.running_count,
                            sim=truth["running_count"], picture=picture.name if image is not None else None)
            self._write("frame", status=status, active=reading["active_hand"], hands=reading["hands"],
                        dealer=reading["dealer"], new_cards=result.new_cards, notes=result.notes,
                        engine=result.running_count, sim=truth["running_count"],
                        sim_last_card=truth.get("last_card"))
            self._last_key = key
        return result, status
