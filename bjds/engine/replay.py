"""Replay a log through the Engine, without running the other components.

The log is JSONL. Lines the Engine understands:

* ``{"event": "table_reading", "reading": {...}}`` - fed to ``Engine.process``
* ``{"event": "bet", "amount": 10}``
* ``{"event": "insurance", "take": false}``
* ``{"event": "move", "move": "hit", "hand_id": "seat0"}``
* a bare table reading (a dict with a ``stage``)

Other lines are skipped. Usage::

    python -m bjds.engine.replay logs/session.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import Engine
from .rules import EngineSettings


def replay(path: str | Path, settings: EngineSettings | None = None,
           real_table: bool = False) -> tuple[Engine, list[dict]]:
    """Feed every line of a log to a fresh Engine.

    Returns the engine and a list of results, one per line it used.
    """
    settings = settings or EngineSettings()
    settings.log_readings = False          # don't log the replay itself
    engine = Engine(settings, real_table=real_table)
    results: list[dict] = []
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        rec = json.loads(line)
        event = rec.get("event")
        if event == "table_reading" or (event is None and "stage" in rec):
            out = engine.process(rec.get("reading", rec)).to_dict()
        elif event == "bet":
            out = engine.submit_bet(rec["amount"]).to_dict()
        elif event == "insurance":
            out = engine.submit_insurance(rec["take"]).to_dict()
        elif event == "move":
            out = engine.submit_move(rec["move"], rec.get("hand_id"),
                                     source="replay").to_dict()
        else:
            continue
        results.append({"line": n, "event": event or "table_reading", "result": out})
    return engine, results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("log")
    ap.add_argument("--real-table", action="store_true")
    a = ap.parse_args()
    engine, results = replay(a.log, real_table=a.real_table)
    for r in results:
        rec = r["result"].get("recommendation")
        if rec:
            print(f"line {r['line']}: {rec['kind']}: {rec['reason']}")
    print(f"{len(results)} lines replayed; running count {engine.counter.running}, "
          f"true count {engine.counter.true_count():+.2f}")


if __name__ == "__main__":
    main()
