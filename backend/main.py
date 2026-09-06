"""
main.py
--------
The FastAPI backend for Voice Study Buddy.

WHAT THIS FILE DOES
1. Serves the frontend (index.html, style.css, script.js) as static files.
2. Exposes POST /api/ask, which:
      a. Receives a question (already converted from speech to text in the
         browser) plus a "generation_id".
      b. Asks the LLM (llm.py) for a short tutor-style answer.
      c. Asks Rime (rime.py) to turn that answer into speech (mp3 bytes).
      d. Sends the mp3 audio back to the browser as a base64 string inside
         a JSON response, along with the answer text.
3. Implements THE MAIN FEATURE OF THIS PROJECT: interruption + recovery,
   using a "generation ID" - explained in detail below.

======================================================================
HOW THE INTERRUPTION / GENERATION-ID MECHANISM WORKS
======================================================================

Every time the user asks a NEW question (including a question that
interrupts the AI mid-sentence), the browser increases a counter called
`generation_id` and sends that number along with the question.

The server keeps track of the HIGHEST generation_id it has seen so far, in
the variable `latest_generation_id` below.

    Request 1 (question A) arrives with generation_id = 1
        -> latest_generation_id becomes 1
        -> server starts calling the LLM, then Rime (this takes a second or two)

    While request 1 is still processing...

    User clicks INTERRUPT and asks question B.
    Request 2 (question B) arrives with generation_id = 2
        -> latest_generation_id becomes 2 (2 > 1, so it's newer, it wins)

    Now suppose request 1 (question A) FINISHES processing.
    Before sending its audio back, the server checks:
        "Is generation_id 1 still equal to latest_generation_id?"
        latest_generation_id is now 2, so NO - request 1 is stale.
        -> The server throws away request 1's answer and returns
           HTTP 409 Conflict ("superseded") instead of audio.

    Request 2 (question B) finishes normally.
        "Is generation_id 2 still equal to latest_generation_id (2)?" YES.
        -> The server returns question B's audio normally.

This check happens at THREE points during processing (before calling the
LLM, before calling Rime, and right before returning), so a stale request
can be caught as early as possible and is very unlikely to reach the point
of returning audio.

This is a server-side safety net. The browser ALSO keeps its own
generation_id and ignores any response that doesn't match its current one
(see frontend/script.js). Two independent checks make stale audio much
less likely to play, even under real network race conditions - but as with
any check-then-act pattern over a network, there's no absolute guarantee:
a response could in principle pass its last server-side check and still
arrive at the browser microseconds after a new request begins, before the
browser's own check runs. In practice this window is small and the tests
in tests/test_interruption.py cover the main race scenario, but this
should be described as "greatly reduces the chance of" rather than
"eliminates," stale audio.
"""

import base64
import os
from pathlib import Path

from dotenv import load_dotenv

# Load RIME_API_KEY / LLM_API_KEY / STT_API_KEY from the .env file BEFORE
# importing llm/rime below. Both of those modules read their API key from
# the environment at import time (e.g. `RIME_API_KEY = os.getenv(...)` at
# the top of rime.py), so load_dotenv() must run first or they'll pick up
# an empty/missing value instead of what's in .env.
load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import llm  # noqa: E402
import rime  # noqa: E402

app = FastAPI(title="Voice Study Buddy")

# ----------------------------------------------------------------------
# THE GENERATION-ID STATE (see big comment above for the full explanation)
# ----------------------------------------------------------------------
# A plain integer is enough here because FastAPI's default dev server runs
# as a single process with one event loop - there's no multi-worker race
# condition to worry about for a hackathon project. (If you ever deploy
# with multiple worker processes, move this into a shared store like Redis.)
latest_generation_id: int = 0


class AskRequest(BaseModel):
    question: str
    generation_id: int


def _is_stale(generation_id: int) -> bool:
    """True if a newer request has arrived since this one started."""
    return generation_id < latest_generation_id


@app.post("/api/ask")
async def ask(req: AskRequest):
    global latest_generation_id

    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="Question was empty.")

    # A new request is, by definition, the newest one we've seen so far -
    # the browser always counts up, never down.
    if req.generation_id > latest_generation_id:
        latest_generation_id = req.generation_id

    # --- Checkpoint 1: bail out before even calling the LLM ---
    if _is_stale(req.generation_id):
        raise HTTPException(status_code=409, detail="superseded")

    try:
        answer_text = await llm.generate_answer(req.question)
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc

    # --- Checkpoint 2: the LLM call took time; did we get interrupted? ---
    if _is_stale(req.generation_id):
        raise HTTPException(status_code=409, detail="superseded")

    try:
        audio_bytes = await rime.synthesize_speech(answer_text)
    except rime.RimeError as exc:
        raise HTTPException(status_code=502, detail=f"Rime error: {exc}") from exc

    # --- Checkpoint 3: right before we hand back audio ---
    if _is_stale(req.generation_id):
        raise HTTPException(status_code=409, detail="superseded")

    return {
        "generation_id": req.generation_id,
        "question": req.question,
        "answer_text": answer_text,
        # Base64-encode the mp3 bytes so they fit cleanly inside JSON.
        # The frontend decodes this back into an audio Blob.
        "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
    }


@app.get("/api/health")
async def health():
    """Simple endpoint to check the server + keys are configured."""
    return {
        "status": "ok",
        "rime_key_set": bool(os.getenv("RIME_API_KEY")),
        "llm_key_set": bool(os.getenv("LLM_API_KEY")),
    }


# ----------------------------------------------------------------------
# Serve the frontend
# ----------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
