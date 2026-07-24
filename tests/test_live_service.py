from __future__ import annotations

import os

import httpx
import pytest

from cross_talker.api import app, get_cross_talker
from cross_talker.config import Settings
from cross_talker.factory import build_cross_talker
from tests.live_prompt_bank import generate_live_prompt, get_num_prompts

pytestmark = pytest.mark.live

@pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1",
    reason="Set RUN_LIVE_TESTS=1 to make a billable OpenAI API request",
)
async def test_live_openai_request_through_http_service() -> None:
    num_prompts = get_num_prompts()
    base_seed = os.getenv("LIVE_TEST_SEED") or os.urandom(8).hex()
    configured = Settings()
    settings = Settings(
        providers=["openai"],
        default_rounds=0,
        database_path=os.getenv("LIVE_TEST_DATABASE_PATH", configured.database_path),
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
            run_ids: set[str] = set()
            for iteration in range(num_prompts):
                prompt, seed = generate_live_prompt(iteration, base_seed)
                print(
                    f"\nLive prompt {iteration + 1}/{num_prompts}"
                    f"\nSeed: {seed}\nPrompt: {prompt}"
                )
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
                assert result["run_id"] not in run_ids
                run_ids.add(result["run_id"])
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

            assert len(run_ids) == num_prompts
    finally:
        app.dependency_overrides.clear()
