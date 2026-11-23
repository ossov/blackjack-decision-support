"""Session log: one JSON object per line (JSONL)."""
from __future__ import annotations

import json
import time
from pathlib import Path


class SessionLog:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.events: list[dict] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **data) -> dict:
        rec = {"t": round(time.time(), 3), "event": event, **data}
        self.events.append(rec)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
        return rec
