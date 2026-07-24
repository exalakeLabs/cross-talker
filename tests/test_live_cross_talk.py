from __future__ import annotations

import os

import httpx
import pytest

from cross_talker.api import app, get_cross_talker
from cross_talker.config import Settings
from cross_talker.factory import build_cross_talker
from tests.live_prompt_bank import generate_live_prompt, get_num_prompts

pytestmark = pytest.mark.live


def get_cross_talk_rounds() -> int:
    raw_value = os.getenv("CROSS_TALK_ROUNDS", "2")
    try:
        rounds = int(raw_value)
    except ValueError as exc:
        raise ValueError("CROSS_TALK_ROUNDS must be an integer") from exc
    if not 1 <= rounds <= 100:
        raise ValueError("CROSS_TALK_ROUNDS must be between 1 and 100")
    return rounds


@pytest.mark.skipif(
    os.getenv("RUN_CROSS_TALK_TESTS") != "1",
    reason="Set RUN_CROSS_TALK_TESTS=1 to call both OpenAI and Anthropic",
)
async def test_live_models_cross_check_each_other() -> None:
    rounds = get_cross_talk_rounds()
    num_prompts = get_num_prompts()
    base_seed = os.getenv("LIVE_TEST_SEED") or os.urandom(8).hex()
    print(f"\nCross-talk seed: {base_seed}\nCross-talk rounds: {rounds}")

    configured = Settings()
    settings = Settings(
        providers=["openai", "anthropic"],
        default_rounds=rounds,
        max_rounds=100,
        database_path=os.getenv("LIVE_TEST_DATABASE_PATH", configured.database_path),
    )
    assert settings.openai_api_key, "OPENAI_API_KEY must be configured in .env"
    assert settings.anthropic_api_key, "ANTHROPIC_API_KEY must be configured in .env"

    service = build_cross_talker(settings)
    app.dependency_overrides[get_cross_talker] = lambda: service
    transport = httpx.ASGITransport(app=app)

    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test-service",
            timeout=120,
        ) as client:
            run_ids: set[str] = set()
            for iteration in range(num_prompts):
                prompt, _ = generate_live_prompt(iteration, base_seed)
                print(
                    f"\nCross-talk run {iteration + 1}/{num_prompts}"
                    f"\nOriginal prompt: {prompt}"
                )
                response = await client.post(
                    "/v1/cross-talk",
                    json={
                        "prompt": prompt,
                        "rounds": rounds,
                        "providers": ["openai", "anthropic"],
                    },
                )
                assert response.status_code == 200, response.text
                result = response.json()
                assert result["run_id"] not in run_ids
                run_ids.add(result["run_id"])

                assert result["rounds_completed"] == rounds
                assert len(result["history"]) == rounds + 1
                for level in result["history"]:
                    assert {answer["provider"] for answer in level["answers"]} == {
                        "openai",
                        "anthropic",
                    }
                    assert all(
                        answer["round"] == level["round"] for answer in level["answers"]
                    )
                    assert all(answer["content"] for answer in level["answers"])

                # Every reviewer receives only the peer's immediately preceding answer.
                for level_number in range(1, rounds + 1):
                    previous = {
                        answer["provider"]: answer["content"]
                        for answer in result["history"][level_number - 1]["answers"]
                    }
                    current = {
                        answer["provider"]: answer
                        for answer in result["history"][level_number]["answers"]
                    }
                    assert previous["anthropic"] in current["openai"]["prompt_sent"]
                    assert previous["openai"] not in current["openai"]["prompt_sent"]
                    assert previous["openai"] in current["anthropic"]["prompt_sent"]
                    assert previous["anthropic"] not in current["anthropic"]["prompt_sent"]

                stored_response = await client.get(f"/v1/runs/{result['run_id']}")
                assert stored_response.status_code == 200
                stored = stored_response.json()
                assert stored["status"] == "completed"
                assert stored["rounds_requested"] == rounds
                assert len(stored["exchanges"]) == 2 * (rounds + 1)

                for level_number in range(rounds + 1):
                    saved_level = [
                        exchange
                        for exchange in stored["exchanges"]
                        if exchange["round"] == level_number
                    ]
                    assert {exchange["provider"] for exchange in saved_level} == {
                        "openai",
                        "anthropic",
                    }
                    assert all(
                        exchange["status"] == "completed" for exchange in saved_level
                    )
                    assert all(exchange["prompt_sent"] for exchange in saved_level)
                    assert all(exchange["answer"] for exchange in saved_level)
                    assert all(exchange["requested_at"] for exchange in saved_level)
                    assert all(exchange["responded_at"] for exchange in saved_level)

                print(f"Persisted run ID: {result['run_id']}")

            assert len(run_ids) == num_prompts
            print(f"SQLite database: {settings.database_path}")
    finally:
        app.dependency_overrides.clear()
