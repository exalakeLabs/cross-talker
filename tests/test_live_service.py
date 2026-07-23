from __future__ import annotations

import os
import random

import httpx
import pytest

from cross_talker.api import app, get_cross_talker
from cross_talker.config import Settings
from cross_talker.factory import build_cross_talker

pytestmark = pytest.mark.live


def generate_live_prompt() -> tuple[str, str]:
    """Return a prompt and seed; set LIVE_TEST_SEED to reproduce a selection."""
    seed = os.getenv("LIVE_TEST_SEED") or os.urandom(8).hex()
    generator = random.Random(seed)
    questions = [
        "Why do leaves usually appear green?",
        "How does a rainbow form?",
        "What causes ocean tides?",
        "Why does metal feel colder than wood at the same room temperature?",
        "How do bees communicate the location of food?",
        "What is the difference between weather and climate?",
        "Why are there seasons on Earth?",
        "How does a compass identify north?",
    ]
    formats = [
        "Answer in one short sentence.",
        "Answer in exactly two concise sentences.",
        "Answer for a curious twelve-year-old in no more than 50 words.",
        "Give a concise answer followed by one supporting fact.",
    ]
    return f"{generator.choice(questions)} {generator.choice(formats)}", seed


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1",
    reason="Set RUN_LIVE_TESTS=1 to make a billable OpenAI API request",
)
async def test_live_openai_request_through_http_service(tmp_path) -> None:
    prompt, seed = generate_live_prompt()
    print(f"\nLive prompt seed: {seed}\nLive prompt: {prompt}")
    settings = Settings(
        providers=["openai"],
        default_rounds=0,
        database_path=str(tmp_path / "live-service.db"),
    )
    assert settings.openai_api_key, "OPENAI_API_KEY must be configured in .env"

    service = build_cross_talker(settings)
    app.dependency_overrides[get_cross_talker] = lambda: service
    transport = httpx.ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test-service",
            timeout=90,
        ) as client:
            response = await client.post(
                "/v1/cross-talk",
                json={
                    "prompt": prompt,
                    "rounds": 0,
                    "providers": ["openai"],
                },
            )
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["prompt"] == prompt
            assert result["final_answers"][0]["provider"] == "openai"
            assert result["final_answers"][0]["content"]

            stored_response = await client.get(f"/v1/runs/{result['run_id']}")
            assert stored_response.status_code == 200
            exchange = stored_response.json()["exchanges"][0]
            assert exchange["status"] == "completed"
            assert exchange["provider"] == "openai"
            assert exchange["prompt_sent"] == prompt
            assert exchange["answer"]
            assert exchange["requested_at"]
            assert exchange["responded_at"]
    finally:
        app.dependency_overrides.clear()
