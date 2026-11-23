# Message formats

The components pass these small JSON messages (proposal, Table 4). Each
`*.example.json` file is a real example; the Engine's tests check that the
Engine reads and writes exactly these shapes, so if a format changes, change
the example and the test fails until the code matches.

| Message | From → To | File | Status |
|---|---|---|---|
| Table reading | Recognition → Engine | `table_reading.example.json` | Engine side done |
| Recommendation | Engine → App | `recommendation.move.example.json`, `recommendation.bet.example.json`, `recommendation.insurance.example.json` | Done |
| Advice | App → Voice | `advice.example.json` | Draft: App and Voice to confirm |
| Player's move | Voice → App | `player_move.example.json` | Draft: App and Voice to confirm |
| Player's action | App → Engine | `player_action.example.json` | Done |
| Move or bet | Engine → Simulator | `simulator_command.example.json` | Done; never sent on a real table |

## Shared conventions

- **Card values:** `1` = ace, `2`–`9`, `10` = any ten-value card. Suits are never used.
  An uncertain card is `null`.
- **Moves:** `"hit"`, `"stand"`, `"double"`, `"split"`; insurance is `"yes"` / `"no"`.
- **Seats** are numbered 1-7 as the simulator does: seat 1 is first base (the dealer's
  left, the viewer's right) and plays first. The dealer has no seat number.
- **Hand ids** are chosen by Recognition and must stay the same for the whole
  round, for example `"seat4"`; the second hand of a split is `"seat4b"`. A hand created by a split gets a new id and
  `"split_of"` set to the original hand's id.
- **Game stage:** `"betting"`, `"dealing"`, `"insurance"`, `"player_turn"`,
  `"dealer_turn"`, `"round_over"`.

## Table reading (Recognition → Engine)

| Field | Type | Meaning |
|---|---|---|
| `stage` | string | Game stage (above) |
| `hands` | list | One entry per bubble at the table, the player's and other seats' |
| `hands[].hand_id` | string | Stable id for the round |
| `hands[].seat` | int | Seat number; the player's seat is set in `config/engine.example.json` |
| `hands[].bubble` | string or null | Raw bubble text: `"16"`, `"6/16"`, `"BJ"`, `"BUST"`; `null` if unreadable |
| `hands[].new_cards` | list | Card values read from pictures since the last reading (optional, later phase) |
| `hands[].bet` | number | Bet on the hand, if read (optional; used to confirm doubles on a real table) |
| `hands[].split_of` | string | Set when this bubble appeared from a split (optional) |
| `dealer` | object | `bubble` and `new_cards` for the dealer |
| `discard_tray_height` | number | Tray height; `tray_height_per_deck` in the config converts it to decks |
| `cut_card_out` | bool | The yellow cut card has come out |
| `active_hand` | string | The hand being played, if Recognition can tell (optional) |
| `timestamp` | number | Seconds, for timing (optional) |

## Recommendation (Engine → App)

`kind` is `"bet"`, `"insurance"` or `"move"`. Every recommendation has
`reason`, `true_count` and `legal_moves` (what the backup buttons may show).
A move recommendation also has `hand`, `upcard`, `action` (the move to make),
`basic_strategy` (the move without the count) and `deviation` (true when the
count changed the move). The App's language model explains `action` and must
never change it.
