import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, Mock

from bjds.voice.__main__ import FRAME_SIZE, LocalAudio


class CaptureTests(unittest.TestCase):
    def make_audio(self, speech_frames, overflow=False):
        audio = LocalAudio.__new__(LocalAudio)
        audio.device = Mock()
        audio.np = Mock()
        audio.torch = Mock()
        audio.detector = Mock()
        audio.detector.side_effect = [
            Mock(**{"item.return_value": probability}) for probability in speech_frames
        ]
        frame = MagicMock()
        stream = Mock()
        stream.read.return_value = (frame, overflow)
        audio.device.InputStream.return_value = nullcontext(stream)
        return audio, stream, frame

    def test_capture_stops_after_speech_and_a_pause(self):
        audio, stream, frame = self.make_audio([0.1, 0.9] + [0.1] * 16)

        self.assertIs(audio.capture(), audio.np.concatenate.return_value)
        self.assertEqual(stream.read.call_count, 18)
        stream.read.assert_called_with(FRAME_SIZE)
        audio.detector.reset_states.assert_called_once()
        audio.np.concatenate.assert_called_once_with([frame] * 18)

    def test_capture_discards_silence(self):
        audio, stream, _ = self.make_audio([0.1] * 62)

        self.assertIsNone(audio.capture())
        self.assertEqual(stream.read.call_count, 62)
        audio.np.concatenate.assert_not_called()

    def test_capture_discards_an_overflow(self):
        audio, stream, _ = self.make_audio([], overflow=True)

        self.assertIsNone(audio.capture())
        stream.read.assert_called_once_with(FRAME_SIZE)
        audio.detector.assert_not_called()


if __name__ == "__main__":
    unittest.main()
