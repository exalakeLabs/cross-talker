from __future__ import annotations

import asyncio

import httpx


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self._timeout, connect=min(10.0, self._timeout))
                ) as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json={
                            "model": self.model,
                            "messages": messages,
                            "max_completion_tokens": self._max_output_tokens,
                        },
                    )
                    response.raise_for_status()
                    return response.json()["choices"][0]["message"]["content"]
            except httpx.TimeoutException as exc:
                if attempt < self._retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise TimeoutError(
                    f"OpenAI request timed out after {self._timeout:g} seconds "
                    f"({self._retries + 1} attempts)"
                ) from exc

        raise RuntimeError("unreachable")
