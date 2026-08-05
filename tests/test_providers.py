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
