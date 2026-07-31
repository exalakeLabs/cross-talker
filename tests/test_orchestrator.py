from __future__ import annotations

import pytest

from cross_talker.exceptions import ConfigurationError
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
    assert "beta answer 1" in alpha.prompts[1]
    assert "alpha answer 1" in beta.prompts[1]
    assert "alpha answer 1" not in alpha.prompts[1]


@pytest.mark.asyncio
async def test_cross_check_prompt_names_source_and_reviewer_models() -> None:
    gpt = FakeProvider("openai")
    claude = FakeProvider("anthropic")
    service = CrossTalker([gpt, claude], default_rounds=1)

    await service.ask("What is the capital of France?")

    assert claude.prompts[1].startswith(
        "This is what GPT generated. YOU are Claude, please evaluate this answer "
        "and re-align your next one based on this analysis."
    )
    assert gpt.prompts[1].startswith(
        "This is what Claude generated. YOU are GPT, please evaluate this answer "
        "and re-align your next one based on this analysis."
    )


@pytest.mark.asyncio
async def test_zero_rounds_returns_initial_answers() -> None:
    service = CrossTalker([FakeProvider("alpha"), FakeProvider("beta")])

    result = await service.ask("Hello", rounds=0)

    assert len(result.history) == 1
    assert all(answer.round == 0 for answer in result.final_answers)

    stored = await service.repository.get_run(result.run_id)
    assert stored is not None
    assert stored.status == "completed"
    assert len(stored.exchanges) == 2
    assert stored.exchanges[0].prompt_sent == "Hello"
    assert stored.exchanges[0].provider in {"alpha", "beta"}
    assert stored.exchanges[0].answer is not None
    assert stored.exchanges[0].requested_at.tzinfo is not None


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


@pytest.mark.asyncio
async def test_single_provider_rejects_cross_check_rounds() -> None:
    service = CrossTalker([FakeProvider("alpha")])

    with pytest.raises(ConfigurationError, match="require at least two"):
        await service.ask("Hello", rounds=1)
