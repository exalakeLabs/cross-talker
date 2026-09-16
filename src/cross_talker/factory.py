from __future__ import annotations

from cross_talker.config import Settings
from cross_talker.exceptions import ConfigurationError
from cross_talker.orchestrator import CrossTalker
from cross_talker.providers import AnthropicProvider, ModelProvider, OpenAIProvider
from cross_talker.storage import SQLiteRepository


def build_cross_talker(
    settings: Settings,
    *,
    repository: SQLiteRepository | None = None,
) -> CrossTalker:
    providers: list[ModelProvider] = []
    for name in settings.providers:
        if name == "openai":
            if not settings.openai_api_key:
                raise ConfigurationError("OPENAI_API_KEY is required when openai is enabled")
            providers.append(
                OpenAIProvider(
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                    base_url=settings.openai_base_url,
                    timeout=settings.request_timeout_seconds,
                    retries=settings.provider_retries,
                    max_output_tokens=settings.max_output_tokens,
                )
            )
        elif name == "anthropic":
            if not settings.anthropic_api_key:
                raise ConfigurationError(
                    "ANTHROPIC_API_KEY is required when anthropic is enabled"
                )
            providers.append(
                AnthropicProvider(
                    api_key=settings.anthropic_api_key,
                    model=settings.anthropic_model,
                    base_url=settings.anthropic_base_url,
                    timeout=settings.request_timeout_seconds,
                    retries=settings.provider_retries,
                    max_output_tokens=settings.max_output_tokens,
                )
            )
        else:
            raise ConfigurationError(f"Unsupported provider configured: {name}")

    return CrossTalker(
        providers,
        default_rounds=settings.default_rounds,
        max_rounds=settings.max_rounds,
        max_peer_answer_chars=settings.max_peer_answer_chars,
        max_conversation_chars=settings.max_conversation_chars,
        repository=repository or SQLiteRepository(settings.database_path),
    )
