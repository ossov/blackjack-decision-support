"""Run the simulator: a small local web server that runs the game and serves the table page.

    python -m sim.server                  # play by hand (or let the Engine send moves)
    python -m sim.server --script         # default test script: same bet every round, auto-play
    python -m sim.server --dataset        # also save labelled card pictures for the card detector

Then open http://127.0.0.1:8765 in a browser.

API (JSON):
    GET  /api/state                     the table as the page draws it
    POST /api/action  {"action": ..., "source": "engine", ...}
         actions: bet {amount}, undo, clear, double_bet, deal, hit, stand, double, split,
                  insurance {take: true|false}
    POST /api/pause   {"paused": true|false}   (omit "paused" to toggle)
    POST /api/restart {"seed": n}               new game: new shoe (random seed if omitted), new history file
"""
from __future__ import annotations

import argparse
import base64
import json
import secrets
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sim.cards import Shoe
from sim.rules import Rules
from sim.table import Table

ROOT = Path(__file__).resolve().parent.parent
WEB = Path(__file__).resolve().parent / "web"
LAYOUT = ROOT / "config" / "layout_sim.json"
CLASSES = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]
TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json"}


def choose_seed(seed: int | None) -> int:
    """The given seed, or a new random one so every launch gets a different shoe."""
    return seed if seed is not None else secrets.randbelow(1_000_000)


class Sim:
    def __init__(self, args):
        self.args = args
        self.history_dir = args.history.parent if args.history else ROOT / "sim" / "history"
        self.lock = threading.Lock()
        self.paused = False
        self._new_table(args.history)
        self.dataset_dir = ROOT / "datasets" / "sim" if args.dataset else None
        self.dataset_count = 0
        if self.dataset_dir:
            (self.dataset_dir / "images").mkdir(parents=True, exist_ok=True)
            (self.dataset_dir / "labels").mkdir(parents=True, exist_ok=True)
            (self.dataset_dir / "classes.txt").write_text("\n".join(CLASSES) + "\n")

    def _new_table(self, history: Path | None = None) -> None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        history = history or self.history_dir / f"{stamp}-seed{self.args.seed}.jsonl"
        rules = Rules(penetration=self.args.penetration)
        a = self.args
        self.table = Table(shoe=Shoe(seed=a.seed, decks=rules.decks, penetration=rules.penetration),
                           rules=rules, player_seat=a.seat, balance=a.balance,
                           other_players=not a.no_others,
                           auto_bet=a.bet if a.script else None, auto_play=a.script,
                           history_path=history)
        self.history_path = history

    def restart(self, body: dict) -> dict:
        """End this game (saving the unfinished shoe's report) and start a new one:
        a new shoe from body["seed"] or a new random seed, a new history file, the starting balance."""
        with self.lock:
            self.table.finish()
            self.args.seed = choose_seed(body.get("seed"))
            self._new_table()
            self.paused = False
        return self.state()

    def run(self):
        last = time.monotonic()
        while True:
            time.sleep(0.05)
            now = time.monotonic()
            dt, last = now - last, now
            with self.lock:
                if not self.paused:
                    self.table.tick(dt * self.args.speed)
                    self.table.step()

    def state(self) -> dict:
        with self.lock:
            s = self.table.snapshot()
        s.update(paused=self.paused, script=self.args.script, seed=self.args.seed,
                 dataset=bool(self.dataset_dir), history=str(self.history_path))
        return s

    def action(self, body: dict) -> dict:
        body = dict(body)
        action = body.pop("action", "")
        source = body.pop("source", "button")
        with self.lock:
            self.table.act(action, source=source, **body)
        return self.state()

    def pause(self, body: dict) -> dict:
        with self.lock:
            self.paused = (not self.paused) if "paused" not in body else bool(body["paused"])
            self.table.history.write("pause" if self.paused else "resume")
        return self.state()

    def save_sample(self, body: dict) -> dict:
        if not self.dataset_dir:
            raise ValueError("start the simulator with --dataset to save card pictures")
        header, data = body["image"].split(",", 1)
        ext = "jpg" if "jpeg" in header else "png"
        w, h = body["width"], body["height"]
        self.dataset_count += 1
        name = f"seed{self.args.seed}_{self.dataset_count:06d}"
        (self.dataset_dir / "images" / f"{name}.{ext}").write_bytes(base64.b64decode(data))
        lines = []
        for item in body["labels"]:
            x, y, bw, bh = item["box"]
            cls = CLASSES.index(item["label"])
            lines.append(f"{cls} {(x + bw / 2) / w:.6f} {(y + bh / 2) / h:.6f} {bw / w:.6f} {bh / h:.6f}")
        (self.dataset_dir / "labels" / f"{name}.txt").write_text("\n".join(lines) + "\n")
        if "bubbles" in body:   # the bubbles' true text, colour and box, for testing Recognition
            (self.dataset_dir / "bubbles").mkdir(exist_ok=True)
            (self.dataset_dir / "bubbles" / f"{name}.json").write_text(
                json.dumps({"image": f"{name}.{ext}", "width": w, "height": h, "bubbles": body["bubbles"],
                            "truth": body.get("truth"), "round": body.get("round")}))
        return {"saved": name}


def make_handler(sim: Sim):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/state":
                return self._json(200, sim.state())
            if path == "/layout.json":
                return self._send(200, LAYOUT.read_bytes(), "application/json")
            file = (WEB / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
            if file.is_file() and WEB in file.parents and file.suffix in TYPES:
                return self._send(200, file.read_bytes(), TYPES[file.suffix] + "; charset=utf-8")
            self._json(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                if self.path == "/api/action":
                    return self._json(200, sim.action(body))
                if self.path == "/api/pause":
                    return self._json(200, sim.pause(body))
                if self.path == "/api/restart":
                    return self._json(200, sim.restart(body))
                if self.path == "/api/dataset":
                    return self._json(200, sim.save_sample(body))
                self._json(404, {"error": "not found"})
            except (ValueError, TypeError, KeyError) as e:
                self._json(400, {"error": str(e)})

    return Handler


def main(argv=None):
    p = argparse.ArgumentParser(description="Blackjack table simulator")
    p.add_argument("--seed", type=int, default=None, help="shoe seed to replay a game (default: random)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--seat", type=int, default=4, help="your seat, 1 (first base) to 7")
    p.add_argument("--balance", type=float, default=1000)
    p.add_argument("--script", action="store_true", help="default test script: fixed bet, auto-play")
    p.add_argument("--bet", type=float, default=10, help="bet used by --script")
    p.add_argument("--no-others", action="store_true", help="no other players at the table")
    p.add_argument("--penetration", type=float, default=0.5, help="cut card position (0-1)")
    p.add_argument("--speed", type=float, default=1.0, help="game speed multiplier")
    p.add_argument("--dataset", action="store_true", help="save labelled card pictures")
    p.add_argument("--history", type=Path, default=None, help="simulator history file (.jsonl)")
    args = p.parse_args(argv)
    args.seed = choose_seed(args.seed)

    sim = Sim(args)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(sim))
    except OSError:
        raise SystemExit(f"Port {args.port} is already in use (is the simulator already running?). "
                         f"Stop the other copy, or pick another port with --port {args.port + 1}.")
    threading.Thread(target=sim.run, daemon=True).start()
    print(f"Simulator running at http://127.0.0.1:{args.port}  (seed {args.seed}, history: {sim.history_path})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        with sim.lock:
            report = sim.table.finish()
        if report:
            print(f"Shoe report for the unfinished shoe: {report}")


if __name__ == "__main__":
    main()
