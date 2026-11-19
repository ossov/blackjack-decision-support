# Voice demo and test guide

Run this guide on the team's demo computer. Follow the setup for that computer in [Voice setup](README.md). Record the operating system, microphone, branch commit, and test date.

## Demo scenario

1. Start a simulator turn where both Hit and Stand are legal.
2. The app sends Voice this advice: “Stand. Keep your hand.”
3. Voice reads the advice. Wait for the high beep, then say “Hit.” The low beep marks the end of the recording.
4. Check that the app receives `hit` and the simulator takes the chosen action.
5. Start another turn. Stay silent twice. Check that the app shows the legal buttons. Use one button to continue.

For a standalone Voice run, check the JSON output. A valid choice has `move: "hit"` and `show_buttons: false`. A failed input has `move: null` and `show_buttons: true`. The standalone demo reports the button request. The team app displays the buttons.

## Test cases

| Case | Input | Expected result |
| --- | --- | --- |
| Valid move | Say “Hit” when Hit and Stand are legal. | Voice returns Hit on the first attempt. |
| Retry | Say “Double” when only Hit and Stand are legal. Say “Stand” after the retry prompt. | Voice lists the legal options and returns Stand. |
| Fallback | Stay silent for both attempts. | Voice requests buttons. The integrated app shows the legal choices. |
| Insurance | In the insurance phase, say “No.” | Voice returns No. |
| Background speech | Repeat the valid move test while another person talks nearby. | Record what Voice heard. Mark the test failed if it accepts a move the player did not say. |

Run the automated checks from the project root with `python -B -m unittest discover -s tests -v`. The reviewed Voice v2 passed 15 automated tests with simulated inputs. Record live results separately.

## Record the results

| Case | Pass or fail | Transcript and returned move | Error or observation |
| --- | --- | --- | --- |
| | | | |

For the first valid move, record the approximate time from the end of speech to the displayed choice. If a case fails, include the exact error message or the relevant session log entry. Share the results with Ayham for the final report.
