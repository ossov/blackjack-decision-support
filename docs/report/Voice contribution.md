# Solution Description & Results

## Component 5 — Voice

The Voice component reads the app's checked advice aloud. The action comes first. For example, the app can send “Stand. Keep your hand.” The player can still say any move the app allows for that turn.

The first beep signals that the player can speak. Silero VAD detects speech and the pause at the end (Silero Team, n.d.). The second beep marks the end of recording. Whisper transcribes the clip in English (Radford et al., 2022). The Mac adapter uses Whisper base.en through MLX (MLX Community, n.d.). The Windows adapter uses Faster Whisper on the CPU (SYSTRAN, n.d.). Piper handles playback, with macOS speech as a backup (Open Home Foundation, n.d.).

The program checks the transcript against the current legal moves. It accepts one command at a time. During play, the command can be hit, stand, double, or split. During insurance, it can be yes or no. If the first attempt fails, the player gets one retry. A second failure returns a request to show the app's decision buttons. The result includes both transcripts and the accepted move. The app records the result in its session log. The app also records whether the player actually uses a backup button.

Fifteen automated tests passed. They covered command validation, retries, audio failures, and fallback behavior. They also checked that a logging failure preserves the turn result. The tests used simulated transcripts and microphone input. Live microphone accuracy, response time, and integration with the full simulator remain unmeasured.

# Work Plan

Ayham Faez Almahasaneh owned Component 5, Voice. The team planned 8.5 hours from November 18 to December 4, 2026. This contribution includes the command rules, local audio adapter, and automated tests. The team should enter actual dates and hours from its work log.

# Lessons Learned

A transcript can contain several possible commands. For example, “hit or stand” gives the app no clear choice. The program rejects it and asks the player again. The same rule applies to silence and commands that are illegal in the current phase. Keeping playback and transcription behind separate functions made it possible to test these cases with plain text.

# References

MLX Community. (n.d.). *whisper-base.en-mlx* [Machine learning model]. Hugging Face. https://huggingface.co/mlx-community/whisper-base.en-mlx

Open Home Foundation. (n.d.). *Piper* [Computer software]. GitHub. https://github.com/OHF-Voice/piper1-gpl

Radford, A., Kim, J. W., Xu, T., Brockman, G., McLeavey, C., & Sutskever, I. (2022). *Robust speech recognition via large-scale weak supervision* [Preprint]. arXiv. https://doi.org/10.48550/arXiv.2212.04356

Silero Team. (n.d.). *Silero VAD* [Computer software]. GitHub. https://github.com/snakers4/silero-vad

SYSTRAN. (n.d.). *Faster Whisper* [Computer software]. GitHub. https://github.com/SYSTRAN/faster-whisper
