# AI use: Liam (Engine)

## Tools

- Claude (claude.ai, agent mode, Claude Opus 5.5) to write the first version of
  the Engine, its tests and the message formats in `contracts/`.

## What I asked for

1. "My goal is building the engine in Python for this project, help me develop
   it", with the section requirements, data flow diagram, round flowchart and a
   reference recording of a live table attached.
2. A check that the Engine follows the requirements and flowchart. This found
   and fixed three gaps: card pictures and bubbles disagreeing, misread bubbles,
   and the real-table mode sending moves to the Simulator.
3. Fitting the code to this repository after sharing it: proposal rule set (no
   double after a split), JSON strategy tables, the proposal's recommendation
   fields, `contracts/`, a full-shoe count test, log replay and the library
   search in `docs/decisions/engine-strategy-library.md`.

## How the output was checked

- 80 pytest tests, named after the behaviour they check.
- A simulation of 3,000 rounds of seeded 8-deck shoes (`bjds/engine/demo.py`)
  in which the Engine read only bubble text: 0 wrong cards.
- One test expectation written by the AI was wrong (4,4 against a 5 doubles only
  in single deck; with 8 decks it is a hit) and was corrected to the published
  move.

## Note on test-driven development

This first version was generated with its tests in one pass, not test-first,
so its commits cannot show the red-green cycle `CLAUDE.md` asks for. Changes
from here on follow the cycle: failing test committed first, then the code.
