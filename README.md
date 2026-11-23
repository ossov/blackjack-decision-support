# Blackjack Decision Support

A human-in-the-loop blackjack decision-support system, built for CST8327 (AI in Software Development), Algonquin College, Fall 2026.

The system reads a blackjack table from the screen, keeps a Hi-Lo count, suggests a bet size, recommends the best move, explains it out loud, and listens for the player's spoken move. The player makes every decision.

- **Stage 1 (committed):** works on our own browser-based table simulator, with every model running locally.
- **Stage 2 (attempted):** reads a real live-dealer table shown on screen. Advice only: on a real table the system never bets or clicks.

## Components

| # | Component | Folder | Owner |
|---|---|---|---|
| 1 | Simulator | `sim/` | Clark |
| 2 | Recognition | `bjds/recognise/` | Ethan O. |
| 3 | Engine | `bjds/engine/` | Liam |
| 4 | App (overlay) | `bjds/app/` | Ethan S. |
| 5 | Voice | `bjds/voice/` | Ayham |

## Working in this repository

1. Work only on your own branch, `dev/<your-name>`. Nobody commits directly to `main`.
2. Merge `main` into your branch before you start, and at least every two days.
3. Write the failing test first (see `CLAUDE.md`), then the code that passes it.
4. Commit small changes, naming the component first, for example `engine: add 12 v 3 count change`.
5. Push your branch and open a pull request into `main`. Another member reviews it, and GitHub Actions runs the tests.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Running the simulator

```bash
python -m sim.server              # play by hand, or let the Engine send moves
python -m sim.server --script     # default test script: same bet every round, plays itself
python -m sim.server --dataset    # also saves labelled card pictures to datasets/sim/
```

Open http://127.0.0.1:8765. Keys: Space pause, H/S/D/P hit/stand/double/split, Y/N insurance, 1–8 chips, Enter deal, T truth panel. The Restart button (click twice) starts a new game with a new random seed and history file, and saves the report for the shoe in progress.

- The table is a 3D scene drawn at 1920×1080. Its camera was fitted to the team's 1440p table recording, so the felt, seats, shoe and discard tray sit where they do in the footage (felt edge within about 20 px). All positions are in `config/layout_sim.json`, which Recognition also reads. The page shows the whole 16:9 video frame with the same margins as the live page, so the table lines up when you switch tabs; if your window differs, adjust the margins with `?inset=left,right,top,bottom` (CSS pixels).
- The Engine sends moves with `POST /api/action` and `{"action": "hit", "source": "engine"}`; `GET /api/state` returns the table.
- Each launch uses a new random shoe; the seed is printed and saved, and `--seed N` replays that exact game.
- Every card and move is written to the simulator history in `sim/history/` as JSON Lines (one event per line), with the running and true count after each card.
- When a shoe ends (or the simulator stops), a shoe report is written next to the history: `...-shoe01.json`. It holds the final running and true count, the highest and lowest true count, every rank seen, the cut card and penetration, the player's results, a count check, and one entry per round (count at the start and end, bet, cards, result).
- The left margin shows the simulator's true count (running count, true count, decks left, last card). It sits outside the table so Recognition can never read it; press T to hide it. Only face-up cards are counted, so the dealer's face-down card counts when it is turned over.
- Card pictures are saved in YOLO format with 10 classes: 2–9, 10 (10/J/Q/K) and A.

## Recognition (Component 2): reading the total bubbles

```bash
pip install -e ".[recognise]"      # and: brew install tesseract
python -m bjds.recognise.evaluate datasets/sim --unseen    # accuracy on frames saved by --dataset
python -m bjds.recognise.glyphs train datasets/sim --half   # rebuild the character classifier
```

- Bubbles are found by their measured colours (grey, green for the hand being played, dark red for a bust, black for the dealer) and given to the nearest seat; a split's right-hand bubble is hand 0.
- The text is read by a small character classifier trained on the simulator's labelled bubbles (`bjds/recognise/models/glyphs_sim.npz`); Tesseract is the backup when the classifier is unsure. Only bubbles whose pixels changed are read again.
- Measured on a fresh simulator session the classifier never saw (801 frames, 3,315 bubbles): 100% found and 100% read exactly, about 24 ms per frame; through a simulated Retina screen capture, 99.9%. Tesseract alone read 91.6% (it misses lone digits).
- Recognition + Engine together, replayed over 759 frames: all 556 dealt cards identified correctly and the running count matched the simulator's after every frame.
- Live view: `python -m bjds.recognise.live --check http://127.0.0.1:8765` opens a window showing each bubble found and the text read. The readings go through the Engine, and the window shows the Engine's running and true count; with `--check` it also shows the simulator's count (green when they agree, red when not) and marks misread bubbles. The first run asks you to drag a box around the video area (saved in `config/capture.json`).
- `python -m bjds.recognise.evaluate datasets/sim --count` replays saved frames through Recognition and the Engine and reports how often the Engine's count matches the simulator's.

## Licence

This project is licensed under the GNU Affero General Public License v3.0 (see `LICENSE`).

### Third-party licences

| Library | Licence | Used for |
|---|---|---|
| Ultralytics YOLO | AGPL-3.0 | Card detector |
| Piper | GPL-3.0 | Text-to-speech |
| three.js (r170, in `sim/web/vendor/`) | MIT | 3D drawing of the simulated table |
| OpenCV (`opencv-python`) | Apache-2.0 | Recognition: finding bubbles; the live viewer window |
| NumPy | BSD-3-Clause | Image arrays and the character classifier |
| Tesseract 5 and `pytesseract` | Apache-2.0 | Recognition: backup text reader |
| `mss` | MIT | Recognition: screen capture |

Any further library is added here, with its licence, before it is used.

## AI use

This project is built with Claude Code. Project instructions are in `CLAUDE.md`, and each member records the AI tools and prompts they used in `docs/ai_usage/`.
