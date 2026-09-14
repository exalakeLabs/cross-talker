from __future__ import annotations

import httpx
import pytest

from cross_talker.providers import AnthropicProvider, OpenAIProvider


@pytest.mark.parametrize(
    ("provider", "expected_message"),
    [
        (
            AnthropicProvider(api_key="test", model="test", timeout=12.5),
            "Anthropic request timed out after 12.5 seconds",
        ),
        (
            OpenAIProvider(api_key="test", model="test", timeout=12.5),
            "OpenAI request timed out after 12.5 seconds",
        ),
    ],
)
async def test_provider_timeout_has_actionable_message(
    provider, expected_message, monkeypatch
) -> None:
    request = httpx.Request("POST", "https://example.test")

    class TimeoutClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.ReadTimeout("", request=request)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: TimeoutClient())

    with pytest.raises(TimeoutError, match=expected_message):
        await provider.complete("Question")


@pytest.mark.parametrize(
    ("provider", "response_body", "expected_token_field"),
    [
        (
            OpenAIProvider(
                api_key="test", model="test", retries=1, max_output_tokens=777
            ),
            {"choices": [{"message": {"content": "recovered"}}]},
            "max_completion_tokens",
        ),
        (
            AnthropicProvider(
                api_key="test", model="test", retries=1, max_output_tokens=777
            ),
            {"content": [{"type": "text", "text": "recovered"}]},
            "max_tokens",
        ),
    ],
)
async def test_provider_retries_timeout_and_bounds_output(
    provider, response_body, expected_token_field, monkeypatch
) -> None:
    calls: list[dict] = []
    request = httpx.Request("POST", "https://example.test")

    class TimeoutThenSuccessClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, *args, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise httpx.ReadTimeout("", request=request)
            return httpx.Response(200, json=response_body, request=request)

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: TimeoutThenSuccessClient())
    monkeypatch.setattr("asyncio.sleep", no_sleep)

    assert await provider.complete("Question") == "recovered"
    assert len(calls) == 2
    assert calls[-1]["json"][expected_token_field] == 777
