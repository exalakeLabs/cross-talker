from __future__ import annotations

import json
import logging

import pytest

from cross_talker.exceptions import ConfigurationError, ProviderCallError
from cross_talker.orchestrator import CrossTalker


class FakeProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.model = f"{name}-test"
        self.prompts: list[str] = []

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> str:
        self.prompts.append(prompt)
        return f"{self.name} answer {len(self.prompts)}"


@pytest.mark.asyncio
async def test_distributes_and_cross_checks_answers() -> None:
    alpha = FakeProvider("alpha")
    beta = FakeProvider("beta")
    service = CrossTalker([alpha, beta], default_rounds=1)

    result = await service.ask("What is the capital of France?")

    assert result.rounds_completed == 1
    assert len(result.history) == 2
    assert [answer.provider for answer in result.final_answers] == ["alpha", "beta"]
    assert result.run_id
    assert result.conclusion.provider == "alpha"
    assert result.conclusion.round == 2
    assert result.conclusion.content == "alpha answer 3"
    assert "beta answer 1" in alpha.prompts[1]
    assert "alpha answer 1" in beta.prompts[1]
    assert "alpha answer 1" not in alpha.prompts[1]
    assert "alpha answer 2" in alpha.prompts[2]
    assert "beta answer 2" in alpha.prompts[2]


@pytest.mark.asyncio
async def test_cross_check_prompt_names_source_and_reviewer_models() -> None:
    gpt = FakeProvider("openai")
    claude = FakeProvider("anthropic")
    service = CrossTalker([gpt, claude], default_rounds=1)

    await service.ask("What is the capital of France?")

    assert claude.prompts[1].startswith(
        "This is what OpenAI responded to the original question. You are Claude. "
        "Evaluate the response below:"
    )
    assert gpt.prompts[1].startswith(
        "This is what Anthropic responded to the original question. You are GPT. "
        "Evaluate the response below:"
    )
    assert "--- Response from OpenAI (openai-test) ---" in claude.prompts[1]
    assert "--- Response from Anthropic (anthropic-test) ---" in gpt.prompts[1]


@pytest.mark.asyncio
async def test_cross_check_truncates_oversized_peer_answers() -> None:
    class VerboseProvider(FakeProvider):
        async def complete(
            self, prompt: str, *, system_prompt: str | None = None
        ) -> str:
            self.prompts.append(prompt)
            return "x" * 2_000

    alpha = VerboseProvider("alpha")
    beta = VerboseProvider("beta")
    service = CrossTalker(
        [alpha, beta], default_rounds=1, max_peer_answer_chars=1_000
    )

    await service.ask("Keep the peer context bounded")

    assert "x" * 1_000 in alpha.prompts[1]
    assert "x" * 1_001 not in alpha.prompts[1]
    assert "[Peer response truncated; 1,000 characters omitted.]" in alpha.prompts[1]


@pytest.mark.asyncio
async def test_provider_failure_logs_diagnostic_context(caplog) -> None:
    class TimingOutProvider(FakeProvider):
        async def complete(
            self, prompt: str, *, system_prompt: str | None = None
        ) -> str:
            try:
                raise RuntimeError("socket stalled")
            except RuntimeError as exc:
                raise TimeoutError("request timed out after 60 seconds") from exc

    provider = TimingOutProvider("anthropic")
    service = CrossTalker([provider])

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        with pytest.raises(ProviderCallError):
            await service.ask("Hello", rounds=0)

    log_text = caplog.text
    assert "provider_call_started" in log_text
    assert "provider_call_failed" in log_text
    assert "provider=anthropic" in log_text
    assert "model=anthropic-test" in log_text
    assert "round=0" in log_text
    assert "error_type=TimeoutError" in log_text
    assert "cause_type=RuntimeError" in log_text
    assert "socket stalled" in log_text


@pytest.mark.asyncio
async def test_generates_and_persists_structured_run_recap() -> None:
    class RecappingProvider(FakeProvider):
        async def complete(
            self, prompt: str, *, system_prompt: str | None = None
        ) -> str:
            self.prompts.append(prompt)
            if prompt.startswith("Create a neutral recap"):
                return json.dumps(
                    {
                        "provider_emphases": [
                            {
                                "provider": self.name,
                                "initial_position": "An initial position",
                                "main_emphases": ["Evidence"],
                                "evolution": "The position became more precise",
                                "final_conclusion": "A final conclusion",
                            }
                        ],
                        "agreements": ["A shared claim"],
                        "disagreements": [],
                        "overall_synthesis": "The evidence supports the conclusion.",
                        "unresolved_questions": ["What evidence is still missing?"],
                    }
                )
            return f"{self.name} answer {len(self.prompts)}"

    provider = RecappingProvider("openai")
    service = CrossTalker([provider])

    result = await service.ask("Hello", rounds=0)
    stored = await service.repository.get_run(result.run_id)

    assert stored is not None
    assert stored.recap is not None
    assert stored.recap.generated_by == "openai"
    assert stored.recap.agreements == ["A shared claim"]
    assert stored.recap_error is None


@pytest.mark.asyncio
async def test_zero_rounds_returns_initial_answers() -> None:
    service = CrossTalker([FakeProvider("alpha"), FakeProvider("beta")])

    result = await service.ask("Hello", rounds=0)

    assert len(result.history) == 1
    assert all(answer.round == 0 for answer in result.final_answers)
    assert result.conclusion.round == 1

    stored = await service.repository.get_run(result.run_id)
    assert stored is not None
    assert stored.status == "completed"
    assert len(stored.exchanges) == 3
    assert stored.exchanges[0].prompt_sent == "Hello"
    assert stored.exchanges[0].provider in {"alpha", "beta"}
    assert stored.exchanges[0].answer is not None
    assert stored.exchanges[0].requested_at.tzinfo is not None
    assert stored.exchanges[-1].kind == "conclusion"


@pytest.mark.asyncio
async def test_rejects_rounds_over_limit() -> None:
    service = CrossTalker(
        [FakeProvider("alpha"), FakeProvider("beta")],
        max_rounds=2,
    )

    with pytest.raises(ConfigurationError, match="between 0 and 2"):
        await service.ask("Hello", rounds=3)


@pytest.mark.asyncio
async def test_single_provider_supports_initial_answer_only() -> None:
    service = CrossTalker([FakeProvider("alpha")])

    result = await service.ask("Hello", rounds=0)

    assert len(result.final_answers) == 1
    assert result.conclusion.provider == "alpha"


@pytest.mark.asyncio
async def test_single_provider_rejects_cross_check_rounds() -> None:
    service = CrossTalker([FakeProvider("alpha")])

    with pytest.raises(ConfigurationError, match="require at least two"):
        await service.ask("Hello", rounds=1)
