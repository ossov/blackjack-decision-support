"""Voice interaction for the blackjack simulator."""

import logging
import re
from dataclasses import dataclass
from typing import Callable, Literal

LOGGER = logging.getLogger(__name__)

Phase = Literal["turn", "insurance"]
COMMANDS = {
    "turn": frozenset({"hit", "stand", "double", "split"}),
    "insurance": frozenset({"yes", "no"}),
}


@dataclass(frozen=True)
class VoiceResult:
    move: str | None
    transcripts: tuple[str, ...]
    show_buttons: bool
    error: str | None = None


def recognize_command(transcript: str, allowed: frozenset[str]) -> str | None:
    match = re.fullmatch(r"\s*([a-z]+)[.,!?\u2026]*\s*", transcript.casefold())
    if match and match[1] in allowed:
        return match[1]
    return None


def run_turn(
    advice: str,
    phase: Phase,
    legal_moves: frozenset[str],
    speak: Callable[[str], None],
    listen: Callable[[], str],
    log: Callable[[VoiceResult], None],
) -> VoiceResult:
    """Speak checked advice and return one current legal move or a UI fallback."""
    allowed = COMMANDS[phase] & legal_moves
    transcripts = []
    result = VoiceResult(None, (), True)

    if allowed:
        try:
            speak(advice)
            for prompt in (None, f"Allowed commands: {', '.join(sorted(allowed))}."):
                if prompt:
                    speak(prompt)
                transcript = listen()
                transcripts.append(transcript)
                move = recognize_command(transcript, allowed)
                if move:
                    result = VoiceResult(move, tuple(transcripts), False)
                    break
            else:
                result = VoiceResult(None, tuple(transcripts), True)
        except Exception as error:
            result = VoiceResult(None, tuple(transcripts), True, type(error).__name__)

    try:
        log(result)
    except Exception:
        LOGGER.exception("Could not write the Voice result to the session log")
    return result
