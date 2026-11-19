"""Local microphone, speech detection, transcription, and playback for Windows and macOS."""

import argparse
import json
import platform
import subprocess
import sys
import tempfile
import wave
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import COMMANDS, run_turn

SAMPLE_RATE = 16_000
FRAME_SIZE = 512
START_TIMEOUT_SECONDS = 2
RECORDING_LIMIT_SECONDS = 6
END_PAUSE_FRAMES = 16


class InputOverflowError(RuntimeError):
    """The microphone dropped audio samples."""


class LocalAudio:
    def __init__(self, piper_model: Path, whisper_model: str | None):
        import numpy as np
        import sounddevice
        import torch
        from silero_vad import load_silero_vad

        self.np = np
        self.device = sounddevice
        self.torch = torch
        self.detector = load_silero_vad()
        self.piper_model = piper_model
        if sys.platform == "win32":
            from faster_whisper import WhisperModel

            self.whisper = WhisperModel(whisper_model or "base.en", device="cpu", compute_type="int8")
        else:
            import mlx_whisper

            self.whisper = mlx_whisper
            self.whisper_model = whisper_model or "mlx-community/whisper-base.en-mlx"

    def transcribe(self, path: Path) -> str:
        if sys.platform == "win32":
            segments, _ = self.whisper.transcribe(
                str(path), language="en", beam_size=1, temperature=0,
                condition_on_previous_text=False,
            )
            return " ".join(segment.text.strip() for segment in segments)

        result = self.whisper.transcribe(
            str(path), path_or_hf_repo=self.whisper_model,
            language="en", condition_on_previous_text=False, temperature=0,
        )
        return result["text"]

    def speak(self, text: str) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "advice.wav"
            try:
                subprocess.run(
                    [sys.executable, "-m", "piper", "--model", str(self.piper_model), "--output_file", str(output)],
                    input=text, text=True, check=True, timeout=15,
                )
            except (OSError, subprocess.SubprocessError):
                if sys.platform != "darwin":
                    raise
                subprocess.run(["say", "--", text], check=True, timeout=15)
                return

            if sys.platform == "win32":
                import winsound

                winsound.PlaySound(str(output), winsound.SND_FILENAME)
            else:
                subprocess.run(["afplay", str(output)], check=True, timeout=15)

    def beep(self, frequency: int) -> None:
        time = self.np.arange(SAMPLE_RATE // 8) / SAMPLE_RATE
        tone = (0.15 * self.np.sin(2 * self.np.pi * frequency * time)).astype("float32")
        self.device.play(tone, SAMPLE_RATE, blocking=True)

    def listen(self) -> str:
        try:
            self.beep(880)
            audio = self.capture()
            self.beep(440)
            if audio is None:
                return ""
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "move.wav"
                with wave.open(str(path), "wb") as recording:
                    recording.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
                    recording.writeframes(audio.tobytes())
                return self.transcribe(path)
        except self.device.PortAudioError as error:
            raise RuntimeError("Audio device failed") from error

    def capture(self):
        self.detector.reset_states()
        frames = []
        spoken = False
        quiet_frames = 0
        with self.device.InputStream(
            samplerate=SAMPLE_RATE, blocksize=FRAME_SIZE, channels=1, dtype="int16",
        ) as stream:
            for _ in range(RECORDING_LIMIT_SECONDS * SAMPLE_RATE // FRAME_SIZE):
                frame, overflow = stream.read(FRAME_SIZE)
                if overflow:
                    raise InputOverflowError("The microphone dropped audio samples")
                samples = self.torch.from_numpy(frame[:, 0].astype("float32") / 32768)
                voiced = self.detector(samples, SAMPLE_RATE).item() >= 0.5
                frames.append(frame)
                spoken = spoken or voiced
                quiet_frames = 0 if voiced else quiet_frames + 1
                if spoken and quiet_frames >= END_PAUSE_FRAMES:
                    break
                if not spoken and len(frames) >= START_TIMEOUT_SECONDS * SAMPLE_RATE // FRAME_SIZE:
                    return None
        if spoken and quiet_frames >= END_PAUSE_FRAMES:
            return self.np.concatenate(frames)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Try one local Voice interaction.")
    parser.add_argument("--phase", required=True, choices=("turn", "insurance"))
    parser.add_argument("--advice", required=True, help="Checked advice with the action first.")
    parser.add_argument("--legal", nargs="+", required=True, type=str.lower)
    parser.add_argument("--piper-model", required=True, type=Path)
    parser.add_argument("--whisper-model", help="Override the default English Whisper model.")
    parser.add_argument("--log", required=True, type=Path)
    args = parser.parse_args()

    if sys.platform not in {"win32", "darwin"}:
        parser.error("The audio adapter supports Windows and Apple silicon macOS.")

    if sys.platform == "darwin" and platform.machine() != "arm64":
        parser.error("Run the macOS audio adapter with native Apple silicon Python.")
    if set(args.legal) - COMMANDS[args.phase]:
        parser.error(f"--legal for {args.phase} accepts: {', '.join(sorted(COMMANDS[args.phase]))}")

    try:
        audio = LocalAudio(args.piper_model, args.whisper_model)
    except Exception as error:
        parser.exit(1, f"Could not start Voice ({type(error).__name__}): {error}\n")

    def log(result):
        event = {"timestamp": datetime.now(timezone.utc).isoformat(), **asdict(result)}
        with args.log.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event) + "\n")

    result = run_turn(
        args.advice, args.phase, frozenset(args.legal),
        audio.speak, audio.listen, log,
    )
    print(json.dumps(asdict(result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
