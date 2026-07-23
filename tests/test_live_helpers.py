from __future__ import annotations

import pytest

from tests.test_live_service import generate_live_prompt, get_num_prompts


def test_num_prompts_defaults_to_one(monkeypatch) -> None:
    monkeypatch.delenv("NUM_PROMPTS", raising=False)

    assert get_num_prompts() == 1


def test_num_prompts_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("NUM_PROMPTS", "4")

    assert get_num_prompts() == 4


@pytest.mark.parametrize("value", ["0", "21", "not-a-number"])
def test_num_prompts_rejects_unsafe_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("NUM_PROMPTS", value)

    with pytest.raises(ValueError, match="NUM_PROMPTS"):
        get_num_prompts()


def test_seed_reproduces_prompt_sequence(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_TEST_SEED", "repeatable")

    first_sequence = [generate_live_prompt(index) for index in range(3)]
    second_sequence = [generate_live_prompt(index) for index in range(3)]

    assert first_sequence == second_sequence
