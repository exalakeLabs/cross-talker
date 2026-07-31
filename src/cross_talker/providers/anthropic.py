from __future__ import annotations

import httpx


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.anthropic.com/v1",
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> str:
        payload: dict[str, object] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
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
            raise TimeoutError(
                f"Anthropic request timed out after {self._timeout:g} seconds"
            ) from exc
