# Engine: existing library or our own strategy tables?

**Date:** 2026-11-20 · **Owner:** Liam · **Status:** decided (can be revisited)

## Question

The proposal says the Engine tries existing Python libraries for card counting
and strategy first, and adopts one only if it gives the published moves in the
strategy tests and its licence fits AGPL-3.0.

## What we looked at (short search, PyPI and GitHub)

| Project | What it is | Why not adopted |
|---|---|---|
| `blackjack-api` (py-jack) | 1-on-1 game library | Plays whole games; one deck; no counting or count changes |
| `blackjack-gui` (MIT) | GUI/CLI game with basic strategy and simple counting | A game to play, not a lookup we can call with one hand; 6-deck rules |
| `cardsharp` (MIT) | Simulation framework for blackjack strategies | Plays and simulates whole games; much more than we need |
| `py21` | Simulator for testing strategies | Simulator; no count changes for our rules |
| `1andDone/blackjack` | Simulator with Hi-Lo back-counters and bet ramps | Simulator; strategy built into its players |
| `5igor99/Blackjack` | Tkinter trainer with Hi-Lo and Illustrious 18 | An app, not a library; not on PyPI |
| `seblau/BlackJack-Simulator` | Simulator that reads a strategy CSV | Uses Omega II, not Hi-Lo |

## Decision

No library is adopted. Every project found is a whole-game simulator or trainer:
none takes "this hand, this dealer card, this true count" and returns a move for
our exact rules (8 decks, stand on all 17s, no double after split, one split,
no surrender, no dealer hole card). None works out cards from bubble totals,
which is the Engine's main job.

The strategy is therefore written by the team as JSON tables in
`bjds/engine/data/` (as the proposal allows), and checked by
`tests/engine/test_strategy.py` against the published moves. This adds no
dependency, so nothing needs adding to the licence table in `README.md`.
