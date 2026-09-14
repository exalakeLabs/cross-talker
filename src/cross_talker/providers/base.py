from __future__ import annotations

from typing import Protocol


class ModelProvider(Protocol):
    """The small contract every model adapter must implement."""

    name: str
    model: str

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> str:
        """Return plain text for a prompt."""
        ...
