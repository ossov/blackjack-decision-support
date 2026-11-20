# Engine (part 3)

Takes the table reading from Recognition, works out each card, keeps the Hi-Lo
count, and sends back the recommended move, bet size and insurance decision.
It also checks the player's moves are legal and builds the command for the
Simulator.

```
python -m pytest tests/engine -q                    # all engine tests
python -m bjds.engine.replay logs/engine_demo.jsonl  # replay a log
python -m bjds.engine.demo --rounds 300 --verbose  # bubbles only
python -m bjds.engine.demo --rounds 3000 --pictures  # bubbles + card pictures
```

No packages needed beyond the Python standard library (pytest for tests).

## Files

| File | What it does |
|---|---|
| `bjds/engine/engine.py` | `Engine`: `process(reading)`, `submit_bet`, `submit_insurance`, `submit_move`, `overlay()` |
| `bjds/engine/hands.py` | Works out new cards from bubble changes (new total − old total, ace = 1). BJ / BUST / pictures / uncertain |
| `bjds/engine/cards.py` | Card values, Hi-Lo tags, bubble parsing (`16`, `6/16`, `BJ`, `BUST`) |
| `bjds/engine/count.py` | Running count, decks left from the discard tray, true count, reset on shuffle |
| `bjds/engine/strategy.py` | Looks up the move in the JSON tables and applies count deviations |
| `bjds/engine/replay.py` | Replays a session log through a fresh Engine |
| `bjds/engine/data/*.json` | Basic strategy (no double after split), double-after-split pair rows, no-hole-card changes, Illustrious 18 + insurance |
| `bjds/engine/betting.py` | Bet size from true count and bankroll (half Kelly, table limits) |
| `bjds/engine/legal.py` | Allowed moves right now (no double on 3 cards, no split on a non-pair, 1 split) |
| `bjds/engine/verify.py` | Real table: checks the next cards match the move the player said |
| `bjds/engine/messages.py` | The message formats between parts |
| `bjds/engine/session_log.py` | JSONL session log |
| `bjds/engine/demo.py` | Fake table that deals seeded shoes and feeds the Engine only bubble text |

## Table rules (`config/engine.example.json`)

From the proposal: 8 decks, dealer stands on all 17s, blackjack pays 3 to 2,
double on any two cards but **not after a split**, one split, no surrender.
From the reference recording (not in the proposal, **team to confirm**): the
dealer takes no hole card until players finish, and doubles/splits are lost to
a dealer blackjack (`no_hole_card`, `enhc_lose_all`). Every rule is a setting;
changing it changes the strategy automatically.

## Messages

The formats are in `contracts/` (see `contracts/README.md`); the tests check the
Engine against those examples.

## How cards are worked out

1. Normal total: card = new total − old total (aces as 1). A soft 21 is shown
   as plain `21`; the engine handles that.
2. `BJ`: the other card must complete 21 with the first.
3. `BUST`: if only one value can bust the old total (e.g. from 12, only a ten), that's it.
4. Otherwise the card picture is used if Recognition sent one.
5. If nothing gives a valid card, it is marked uncertain and not counted.

Demo results (3,000 rounds, `python -m bjds.engine.demo --rounds 3000`): 0 wrong cards. Bubbles only: ~7% of cards
uncertain, mostly bust cards, so the count is off by a little in about a third
of rounds. With card pictures: 0 uncertain. **The card-picture backup matters
most for BUST hands**.
