# Rime Evidence

## Project

Voice Study Buddy

## Hard Voice Problem

Interruption and recovery: letting a user naturally talk over an AI tutor
that is speaking through Rime, and have the system stop the stale response
and immediately process the new one, so the old audio is very unlikely to
resume afterward.

## Claim

The user can interrupt an ongoing Rime response and provide a new
instruction, and the previous response is very unlikely to continue
playing. This is enforced by a "generation ID" that is checked both in the
browser (frontend/script.js) and on the server (backend/main.py), at
multiple points in the request lifecycle (before calling the LLM, before
calling Rime, and right before returning audio). This check-then-act
pattern greatly reduces, but does not mathematically eliminate, the chance
of stale audio playing - see the note in `backend/main.py`'s module
docstring for the specific narrow race window that remains.

## Acceptance Test

1. Click "🎤 Ask Question" and ask: *"Explain supervised learning in
   detail."*
2. Wait until the "🔊 AI is speaking..." indicator appears and Rime's audio
   begins playing.
3. Click "🛑 Interrupt" while the audio is still playing.
4. Ask the new question: *"Stop. Give me a simple example."*
5. Verify the previous (supervised learning) audio stops immediately when
   Interrupt is clicked.
6. Verify the new question is accepted and a new answer is generated.
7. Verify the new answer is spoken by Rime.
8. Verify the old, stale audio never resumes or overlaps with the new audio,
   even if it was still being generated when you interrupted.

## Result

> Fill this in after running the acceptance test yourself. Do not fabricate
> results - leave "PASS/FAIL" and the notes fields blank until you've
> actually run it.

| Step | Result (PASS/FAIL) | Notes |
| ---- | ------------------- | ----- |
| 1. Question asked | | |
| 2. Rime audio begins playing | | |
| 3. Interrupt clicked mid-speech | | |
| 4. New question asked | | |
| 5. Old audio stopped immediately | | |
| 6. New question accepted | | |
| 7. New answer generated | | |
| 8. New answer spoken by Rime | | |
| 9. Stale audio never resumed | | |

**10-run manual stress test** (repeat the acceptance test 10 times back to
back):

| Run | Interruption handled correctly? (Y/N) | Notes |
| --- | -------------------------------------- | ----- |
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |
| 6 | | |
| 7 | | |
| 8 | | |
| 9 | | |
| 10 | | |

## Reproduction

```bash
# 1. Clone and enter the project
git clone <your-repo-url>
cd voice-study-buddy

# 2. Install dependencies
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure API keys
cp .env.example .env
# edit .env and paste in your RIME_API_KEY and LLM_API_KEY

# 4. Run the server
cd backend
uvicorn main:app --reload --port 8000

# 5. Open the app
# Visit http://localhost:8000 in Chrome or Edge (for microphone support)

# 6. Run the automated interruption-logic tests
cd ..
pytest tests/test_interruption.py -v

# 7. Perform the manual acceptance test described above, 10 times,
#    and fill in the tables in this file with real results.
```

## What Was Verified in Rime's Documentation Before Implementation

Before writing `backend/rime.py`, the current Rime documentation
(docs.rime.ai) was checked directly rather than relying on memorized/assumed
API details:

- **Endpoint**: `https://users.rime.ai/v1/rime-tts` (confirmed current in
  Rime's API reference and its FastAPI voice-agent integration guide).
- **Authentication**: bearer token via `Authorization: Bearer <RIME_API_KEY>`.
- **Model**: `coda` - Rime's current flagship model. Rime's older `arcana`
  model is scheduled to stop serving cloud traffic on 2026-08-15 (cloud
  Arcana requests are redirected to Coda after that date per Rime's
  changelog), so this project targets `coda` directly instead of a model
  that is being retired.
- **Speaker**: `astra` - used as the example/starter voice in Rime's own
  documentation and FastAPI integration guide.
- **Audio format**: MP3, requested via the `Accept: audio/mpeg` header, so
  it plays natively in a browser `<audio>` element with no extra decoding.
