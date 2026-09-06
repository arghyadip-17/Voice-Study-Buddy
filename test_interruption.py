"""
test_interruption.py
---------------------
Automated tests for the interruption/generation-id mechanism in
backend/main.py. These test the LOGIC (does a stale request get rejected?)
without needing real Rime/LLM API keys, by monkeypatching llm.generate_answer
and rime.synthesize_speech with fast fakes.

Run with:
    cd backend
    pytest ../tests/test_interruption.py -v

These are UNIT/INTEGRATION tests of the generation-id logic itself. They are
separate from the manual, real-microphone acceptance test described in
RIME_EVIDENCE.md, which verifies the full experience with real audio.
"""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Make backend/ importable when running pytest from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import llm  # noqa: E402
import main  # noqa: E402
import rime  # noqa: E402


@pytest.fixture(autouse=True)
def reset_generation_id():
    """Each test starts with a clean generation-id counter."""
    main.latest_generation_id = 0
    yield
    main.latest_generation_id = 0


@pytest.fixture
def fast_fakes(monkeypatch):
    """Replace the real LLM/Rime network calls with instant fakes."""

    async def fake_generate_answer(question: str) -> str:
        return f"Answer to: {question}"

    async def fake_synthesize_speech(text: str) -> bytes:
        return b"FAKE_MP3_BYTES"

    monkeypatch.setattr(llm, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(rime, "synthesize_speech", fake_synthesize_speech)


client = TestClient(main.app)


def test_normal_question_returns_answer_and_audio(fast_fakes):
    """A single, non-interrupted question should succeed normally."""
    res = client.post("/api/ask", json={"question": "What is a stack?", "generation_id": 1})
    assert res.status_code == 200
    body = res.json()
    assert body["generation_id"] == 1
    assert "Answer to: What is a stack?" in body["answer_text"]
    assert body["audio_base64"]  # non-empty


def test_newer_generation_wins_over_older(fast_fakes):
    """
    Simulates: question A (gen 1) starts, then question B (gen 2) arrives
    before A's response is requested. A should be considered stale.
    """
    # Question B arrives first and sets the "latest" pointer to 2.
    res_b = client.post("/api/ask", json={"question": "Question B", "generation_id": 2})
    assert res_b.status_code == 200

    # Question A (an older generation id) arrives afterward - e.g. a slow
    # network delayed it. It must be rejected as stale.
    res_a = client.post("/api/ask", json={"question": "Question A", "generation_id": 1})
    assert res_a.status_code == 409


def test_empty_question_is_rejected(fast_fakes):
    res = client.post("/api/ask", json={"question": "   ", "generation_id": 1})
    assert res.status_code == 400


def test_llm_failure_returns_friendly_error(monkeypatch):
    async def failing_generate_answer(question: str) -> str:
        raise llm.LLMError("simulated LLM outage")

    monkeypatch.setattr(llm, "generate_answer", failing_generate_answer)

    res = client.post("/api/ask", json={"question": "Anything", "generation_id": 1})
    assert res.status_code == 502
    assert "LLM error" in res.json()["detail"]


def test_rime_failure_returns_friendly_error(monkeypatch):
    async def ok_generate_answer(question: str) -> str:
        return "some answer"

    async def failing_synthesize_speech(text: str) -> bytes:
        raise rime.RimeError("simulated Rime outage")

    monkeypatch.setattr(llm, "generate_answer", ok_generate_answer)
    monkeypatch.setattr(rime, "synthesize_speech", failing_synthesize_speech)

    res = client.post("/api/ask", json={"question": "Anything", "generation_id": 1})
    assert res.status_code == 502
    assert "Rime error" in res.json()["detail"]
