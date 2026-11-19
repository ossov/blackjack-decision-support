import unittest
from unittest.mock import Mock

from bjds.voice import VoiceResult, run_turn


class VoiceTests(unittest.TestCase):
    def run_interaction(self, transcripts, phase="turn", legal=("hit", "stand")):
        speak = Mock()
        listen = Mock(side_effect=transcripts)
        log = Mock()
        result = run_turn("Stand. Keep your hand.", phase, frozenset(legal), speak, listen, log)
        log.assert_called_once_with(result)
        return result, speak, listen

    def test_clear_command_is_normalized(self):
        result, speak, listen = self.run_interaction([" HIT. "])
        self.assertEqual(result, VoiceResult("hit", (" HIT. ",), False))
        speak.assert_called_once_with("Stand. Keep your hand.")
        listen.assert_called_once_with()

    def test_illegal_command_prompts_once(self):
        result, speak, listen = self.run_interaction(["double", "stand"])
        self.assertEqual(result.move, "stand")
        self.assertEqual(speak.call_count, 2)
        self.assertEqual(listen.call_count, 2)

    def test_ambiguous_command_and_silence_request_buttons(self):
        result, _, listen = self.run_interaction(["hit or stand", ""])
        self.assertEqual(result, VoiceResult(None, ("hit or stand", ""), True))
        self.assertEqual(listen.call_count, 2)

    def test_insurance_only_accepts_yes_or_no(self):
        result, _, _ = self.run_interaction(["hit", "No"], "insurance", ("hit", "yes", "no"))
        self.assertEqual(result.move, "no")

    def test_missing_legal_actions_skips_recording(self):
        result, speak, listen = self.run_interaction([], legal=())
        self.assertTrue(result.show_buttons)
        speak.assert_not_called()
        listen.assert_not_called()

    def test_audio_failure_requests_buttons(self):
        result, _, _ = self.run_interaction([RuntimeError("microphone unavailable")])
        self.assertEqual(result, VoiceResult(None, (), True, "RuntimeError"))

    def test_unexpected_transcription_error_requests_buttons_and_keeps_transcript(self):
        result, _, _ = self.run_interaction(["unclear", ValueError("decoder failed")])
        self.assertEqual(result, VoiceResult(None, ("unclear",), True, "ValueError"))

    def test_playback_error_requests_buttons_without_listening(self):
        speak = Mock(side_effect=OSError("speaker unavailable"))
        listen = Mock()
        log = Mock()
        result = run_turn("Hit.", "turn", frozenset({"hit"}), speak, listen, log)
        self.assertEqual(result, VoiceResult(None, (), True, "OSError"))
        listen.assert_not_called()
        log.assert_called_once_with(result)

    def test_log_error_preserves_command_and_reports_failure(self):
        log = Mock(side_effect=OSError("disk unavailable"))
        with self.assertLogs("bjds.voice", "ERROR"):
            result = run_turn("Hit.", "turn", frozenset({"hit"}), Mock(), Mock(return_value="hit"), log)
        self.assertEqual(result.move, "hit")

    def test_silence_then_legal_move_with_punctuation(self):
        for command in ("double,", "split..."):
            with self.subTest(command=command):
                result, speak, _ = self.run_interaction(["", command], legal=("double", "split"))
                self.assertEqual(result.move, command.rstrip(".,"))
                self.assertEqual(speak.call_args.args, ("Allowed commands: double, split.",))


if __name__ == "__main__":
    unittest.main()
