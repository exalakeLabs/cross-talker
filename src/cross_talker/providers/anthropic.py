from __future__ import annotations

import asyncio

import httpx


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.anthropic.com/v1",
        timeout: float = 120.0,
        retries: int = 1,
        max_output_tokens: int = 2_048,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._retries = retries
        self._max_output_tokens = max_output_tokens

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> str:
        payload: dict[str, object] = {
            "model": self.model,
            "max_tokens": self._max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self._timeout, connect=min(10.0, self._timeout))
                ) as client:
                    response = await client.post(
                        f"{self._base_url}/messages",
                        headers={
                            "x-api-key": self._api_key,
                            "anthropic-version": "2023-06-01",
                        },
                        json=payload,
                    )
                    response.raise_for_status()
                    blocks = response.json()["content"]
                    return "\n".join(block["text"] for block in blocks if block["type"] == "text")
            except httpx.TimeoutException as exc:
                if attempt < self._retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise TimeoutError(
                    f"Anthropic request timed out after {self._timeout:g} seconds "
                    f"({self._retries + 1} attempts)"
                ) from exc

        raise RuntimeError("unreachable")
