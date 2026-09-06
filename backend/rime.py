"""
rime.py
--------
This file talks to Rime's text-to-speech (TTS) API.

WHAT IS RIME?
Rime turns text (a string) into spoken audio (mp3 bytes). We send it the
tutor's written answer, and it sends back an mp3 file we can play in the
browser.

VERIFIED AGAINST CURRENT RIME DOCS (checked live before writing this file):
  - Endpoint:      https://users.rime.ai/v1/rime-tts   (docs.rime.ai/docs/api-reference)
  - Auth:          "Authorization: Bearer <RIME_API_KEY>" header
  - Current model: "coda" -> Rime's flagship model. Rime's older "arcana" model
                    is being retired for cloud traffic on 2026-08-15, so this
                    project uses "coda" instead.
  - Speaker used:  "astra" -> Rime's own documentation uses this as the
                    recommended first voice to try with Coda.
  - Audio format:  We ask for MP3 by setting the "Accept" header to
                    "audio/mpeg". MP3 plays natively in every browser with a
                    plain <audio> tag, which keeps the frontend simple.

SECURITY NOTE:
This file is the ONLY place that ever sees RIME_API_KEY. The browser never
sees it. The frontend calls OUR backend, and our backend calls Rime.
"""

import os

import httpx

# Read the Rime API key from the environment (loaded from .env by main.py).
RIME_API_KEY = os.getenv("RIME_API_KEY")

# The current official Rime TTS endpoint (see docstring above for source).
RIME_TTS_URL = "https://users.rime.ai/v1/rime-tts"

# Default voice + model. You can change SPEAKER to any other Coda voice
# listed at https://docs.rime.ai/docs/voices without touching any other code.
DEFAULT_MODEL_ID = "coda"
DEFAULT_SPEAKER = "astra"


class RimeError(Exception):
    """Raised when Rime TTS fails, so main.py can show a friendly error."""


async def synthesize_speech(text: str) -> bytes:
    """
    Send `text` to Rime and return the resulting MP3 audio as raw bytes.

    Parameters
    ----------
    text: the sentence(s) we want spoken out loud (the tutor's answer).

    Returns
    -------
    bytes of a playable MP3 file.

    Raises
    ------
    RimeError if the API key is missing, the text is empty, or Rime
    returns a non-200 response.
    """
    if not RIME_API_KEY:
        raise RimeError(
            "RIME_API_KEY is not set. Add it to your .env file. "
            "Get a key at https://app.rime.ai/tokens"
        )

    if not text or not text.strip():
        raise RimeError("Cannot synthesize empty text.")

    payload = {
        "speaker": DEFAULT_SPEAKER,
        "text": text,
        "modelId": DEFAULT_MODEL_ID,
        "lang": "en",
    }

    headers = {
        "Authorization": f"Bearer {RIME_API_KEY}",
        "Content-Type": "application/json",
        # Ask Rime for MP3 bytes back (see docstring for why MP3).
        "Accept": "audio/mpeg",
    }

    # 30 second timeout: TTS is usually fast (sub-second to a few seconds),
    # but we give it room on a slow connection instead of failing too eagerly.
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(RIME_TTS_URL, headers=headers, json=payload)
        except httpx.RequestError as exc:
            raise RimeError(f"Could not reach Rime (network error): {exc}") from exc

    if response.status_code != 200:
        # Never leak the API key value in error text, only Rime's own message.
        raise RimeError(
            f"Rime API returned an error (status {response.status_code}): "
            f"{response.text[:300]}"
        )

    return response.content
