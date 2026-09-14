from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from cross_talker.api import app, get_cross_talker, get_repository
from cross_talker.orchestrator import CrossTalker
from cross_talker.storage import SQLiteRepository


class FakeProvider:
    name = "test-provider"
    model = "test-model"

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> str:
        return "The sky appears blue because shorter blue wavelengths are scattered strongly."


@pytest.fixture
async def api_client(tmp_path) -> AsyncIterator[httpx.AsyncClient]:
    service = CrossTalker(
        [FakeProvider()],
        default_rounds=0,
        repository=SQLiteRepository(tmp_path / "service-test.db"),
    )
    app.dependency_overrides[get_cross_talker] = lambda: service
    app.dependency_overrides[get_repository] = lambda: service.repository
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test-service",
    ) as client:
        yield client
    app.dependency_overrides.clear()


async def test_http_request_is_persisted_and_retrievable(
    api_client: httpx.AsyncClient,
) -> None:
    prompt = "Explain why the sky appears blue in three sentences."

    response = await api_client.post(
        "/v1/cross-talk",
        json={
            "prompt": prompt,
            "rounds": 0,
            "providers": ["test-provider"],
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["prompt"] == prompt
    assert result["rounds_completed"] == 0
    assert result["final_answers"][0]["provider"] == "test-provider"
    assert result["final_answers"][0]["model"] == "test-model"
    assert result["final_answers"][0]["round"] == 0
    assert result["final_answers"][0]["content"]
    assert result["conclusion"]["content"]
    assert result["conclusion"]["provider"] == "test-provider"

    stored_response = await api_client.get(f"/v1/runs/{result['run_id']}")

    assert stored_response.status_code == 200
    stored = stored_response.json()
    assert stored["status"] == "completed"
    assert stored["original_prompt"] == prompt
    assert len(stored["exchanges"]) == 2

    exchange = stored["exchanges"][0]
    assert exchange["provider"] == "test-provider"
    assert exchange["model"] == "test-model"
    assert exchange["round"] == 0
    assert exchange["prompt_sent"] == prompt
    assert exchange["answer"]
    assert exchange["diagnostic_detail"] is None
    assert exchange["requested_at"]
    assert exchange["responded_at"]
    assert exchange["kind"] == "response"
    assert stored["exchanges"][-1]["kind"] == "conclusion"

    list_response = await api_client.get("/v1/runs", params={"limit": 10})

    assert list_response.status_code == 200
    assert any(run["run_id"] == result["run_id"] for run in list_response.json())
