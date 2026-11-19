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

## Licence

This project is licensed under the GNU Affero General Public License v3.0 (see `LICENSE`).

### Third-party licences

| Library | Licence | Used for |
|---|---|---|
| Ultralytics YOLO | AGPL-3.0 | Card detector |
| Piper | GPL-3.0 | Text-to-speech |

Any further library is added here, with its licence, before it is used.

## AI use

This project is built with Claude Code. Project instructions are in `CLAUDE.md`, and each member records the AI tools and prompts they used in `docs/ai_usage/`.
