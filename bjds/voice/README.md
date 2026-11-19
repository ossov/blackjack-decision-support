# Voice component

The Python command logic runs without audio packages. From the project root:

    python -B -m unittest discover -s tests -v

## Run the microphone demo on Windows

From the project root in PowerShell:

    python -m venv .venv-voice
    .\.venv-voice\Scripts\python.exe -m pip install faster-whisper numpy sounddevice silero-vad piper-tts
    .\.venv-voice\Scripts\python.exe -m piper.download_voices en_US-lessac-medium
    .\.venv-voice\Scripts\python.exe -m bjds.voice --phase turn --advice "Stand. Keep your hand." --legal hit stand --piper-model en_US-lessac-medium.onnx --log voice-session.jsonl

Windows uses Faster Whisper base.en on the CPU. Allow microphone access for desktop apps. After the high beep, say “hit” or “stand.” Model weights download on the first setup.

## Run the microphone demo on Apple silicon

Use Python 3.11 in a virtual environment. The microphone demo uses FFmpeg to read the recorded WAV and PortAudio for the microphone and beeps.

    brew install ffmpeg portaudio
    python3.11 -m venv .venv
    source .venv/bin/activate
    python -m pip install mlx-whisper numpy sounddevice silero-vad piper-tts
    python -m piper.download_voices en_US-lessac-medium
    python -m bjds.voice --phase turn --advice "Stand. Keep your hand." --legal hit stand --piper-model en_US-lessac-medium.onnx --log voice-session.jsonl

Give the terminal microphone access when macOS asks. Say “hit” or “stand” after the high beep. The low beep marks the end. The first transcription may download model weights. Model files and session logs belong outside version control.

## Connect to the team app

Call run_turn with the checked advice, phase, legal moves, the audio functions, and the session log callback. Keep the interaction on a worker so recording cannot block the overlay. Use one interaction at a time. The overlay should ignore a result if that turn has ended.

    from bjds.voice import run_turn
    from bjds.voice.__main__ import LocalAudio

    audio = LocalAudio(model_path, whisper_model=None)
    result = run_turn(advice, phase, frozenset(legal), audio.speak, audio.listen, log_voice)

The app receives a legal move or a request to show its buttons. Log a separate event if the player uses a button. Voice does not send moves directly to the simulator.

For the live check, try every command when legal, one illegal command, background speech, and silence. Record the expected command, transcript, accepted command, fallback, and response time. Run the same cases with the demo microphone.
