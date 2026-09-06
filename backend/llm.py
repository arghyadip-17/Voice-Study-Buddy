"""
llm.py
-------
This file asks an LLM (Claude) to answer the student's question like a
friendly study tutor.

We call Anthropic's Messages API directly with `httpx` (no extra SDK needed,
which keeps requirements.txt small and the code easy to read).

The SYSTEM_PROMPT below is what makes the AI behave like a tutor instead of
a generic chatbot: short, simple, example-driven answers.
"""

import os

import httpx

LLM_API_KEY = os.getenv("LLM_API_KEY")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# A small, fast model is a good fit here: answers are short and we want low
# latency, since the user is waiting to hear a spoken response.
MODEL_NAME = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are Voice Study Buddy, a friendly AI study tutor for
college students, mainly helping with computer science and general study
topics.

Rules for every answer:
- Keep answers SHORT (2-4 sentences unless the student asks for more detail).
- Explain concepts in simple, plain language.
- Give a short concrete example when it helps understanding.
- Avoid unnecessary jargon; if you must use a technical term, briefly say
  what it means.
- Your answer will be read aloud by a text-to-speech engine, so write in
  natural spoken sentences. Do not use bullet points, numbered lists,
  markdown, code blocks, or special symbols.
- If the student says "stop" or interrupts with a follow-up like "give me a
  simpler example", treat it as a fresh instruction and answer that instead.
"""


class LLMError(Exception):
    """Raised when the LLM call fails, so main.py can show a friendly error."""


async def generate_answer(question: str) -> str:
    """
    Send `question` to Claude and return a short, spoken-friendly answer.
    """
    if not LLM_API_KEY:
        raise LLMError(
            "LLM_API_KEY is not set. Add it to your .env file. "
            "Get a key at https://console.anthropic.com/settings/keys"
        )

    if not question or not question.strip():
        raise LLMError("Cannot answer an empty question.")

    headers = {
        "x-api-key": LLM_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    body = {
        "model": MODEL_NAME,
        "max_tokens": 300,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": question}],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(ANTHROPIC_URL, headers=headers, json=body)
        except httpx.RequestError as exc:
            raise LLMError(f"Could not reach the LLM (network error): {exc}") from exc

    if response.status_code != 200:
        raise LLMError(
            f"LLM API returned an error (status {response.status_code}): "
            f"{response.text[:300]}"
        )

    data = response.json()

    # Claude's response content is a list of blocks; we want the text ones.
    text_blocks = [block["text"] for block in data.get("content", []) if block.get("type") == "text"]
    answer = " ".join(text_blocks).strip()

    if not answer:
        raise LLMError("LLM returned an empty answer.")

    return answer
