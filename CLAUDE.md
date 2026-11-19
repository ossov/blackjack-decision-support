# Project instructions

Blackjack decision support for CST8327. Five components pass small JSON messages to each other; formats live in `contracts/`. See `README.md` for owners and folders.

## Test-driven development (always)

1. **Red:** write a failing test that describes the behaviour, with no implementation. Run it and confirm it fails.
2. **Green:** write the least code that makes the test pass, and nothing more.
3. **Refactor:** clean up while every test stays green.

Rules:
- Never write code before a failing test exists for it.
- Never change a test just to make it pass. If a test is wrong, say so and stop.
- Name each test after the behaviour it checks, for example `test_same_seed_gives_same_shoe`.
- The failing test is committed before the code that passes it.

## Project rules

- The Engine chooses every move from strategy tables. The language model only explains the move and must never choose or change it.
- A card that cannot be confirmed is marked uncertain and left out of the count. Never guess.
- Recognition reads screen pixels only: no web page code, network traffic or stored browser data, and no browser extension.
- The system never clicks or bets on a real table. Moves are carried out only in the simulator.
- Everything runs locally unless a cloud model is explicitly switched on for Stage 2. Keys go in `.env`, never in code.
- Before adding a dependency, check that its licence is compatible with AGPL-3.0 and add it to the licence table in `README.md`.

## Conventions

- Python 3.12, dependencies in `pyproject.toml`, tests in `tests/` run with `pytest`.
- Commit messages start with the component: `sim:`, `recognise:`, `engine:`, `app:`, `voice:`, `docs:`.
- Work on `dev/<name>` branches; never commit to `main`.
