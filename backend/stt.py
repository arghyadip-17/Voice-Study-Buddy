"""
stt.py
-------
SPEECH-TO-TEXT (STT) EXTENSION POINT.

This project's actual speech-to-text happens FOR FREE, IN THE BROWSER, using
the built-in Web Speech API (see frontend/script.js -> SpeechRecognition).
That is the "simplest reliable approach" for a hackathon: no extra API key,
no extra network hop, works instantly in Chrome/Edge/Safari.

WHY THIS FILE EXISTS ANYWAY:
The assignment asks for the backend to be structured so STT can later be
swapped for a real STT API (e.g. Deepgram, AssemblyAI, OpenAI Whisper, or
Rime's own STT if/when available) without rewriting the rest of the app.
This file is that seam. Today it's a documented stub; tomorrow you can fill
in `transcribe_audio()` and add one call to it in main.py's /api/stt route
(also stubbed below) without touching llm.py, rime.py, or the interruption
logic in main.py at all.

HOW YOU WOULD WIRE UP A REAL STT API LATER:
1. Add STT_API_KEY to .env (the placeholder already exists in .env.example).
2. In transcribe_audio(), POST the raw audio bytes to your chosen STT
   provider's endpoint with that key, and return the transcript string.
3. In frontend/script.js, instead of using SpeechRecognition, record audio
   with the MediaRecorder API and POST the recorded blob to /api/stt.
4. Everything downstream (LLM -> Rime -> interruption handling) stays the
   same, because it only ever deals with plain text questions.
"""

import os

STT_API_KEY = os.getenv("STT_API_KEY")


class STTError(Exception):
    """Raised when speech-to-text fails."""


async def transcribe_audio(audio_bytes: bytes) -> str:
    """
    STUB: convert recorded audio bytes into text.

    Not used by default in this project (the browser's Web Speech API does
    STT on the client side instead - see frontend/script.js). This function
    exists as the documented place to plug in a real STT API later.
    """
    raise STTError(
        "Server-side STT is not implemented in this project. "
        "This build uses the browser's built-in SpeechRecognition instead. "
        "See the comment at the top of backend/stt.py for how to add a "
        "real STT API here."
    )
