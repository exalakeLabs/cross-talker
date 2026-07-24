from __future__ import annotations

import pytest

from tests.live_prompt_bank import (
    generate_live_prompt,
    get_num_prompts,
    load_question_bank,
)


def test_num_prompts_defaults_to_one(monkeypatch) -> None:
    monkeypatch.delenv("NUM_PROMPTS", raising=False)

    assert get_num_prompts() == 1


def test_num_prompts_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("NUM_PROMPTS", "4")

    assert get_num_prompts() == 4


@pytest.mark.parametrize("value", ["0", "43", "not-a-number"])
def test_num_prompts_rejects_unsafe_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("NUM_PROMPTS", value)

    with pytest.raises(ValueError, match="NUM_PROMPTS"):
        get_num_prompts()


def test_seed_reproduces_prompt_sequence(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_TEST_SEED", "repeatable")

    first_sequence = [generate_live_prompt(index) for index in range(3)]
    second_sequence = [generate_live_prompt(index) for index in range(3)]

    assert first_sequence == second_sequence
    assert len({prompt for prompt, _ in first_sequence}) == 3


def test_question_bank_covers_multiple_domains() -> None:
    bank = load_question_bank()
    categories = {question["category"] for question in bank["questions"]}

    assert len(bank["questions"]) >= 40
    assert len(bank["response_styles"]) >= 8
    assert len(categories) >= 10


def test_generated_run_uses_each_question_once(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_TEST_SEED", "no-question-repeats")
    bank = load_question_bank()
    prompts = [
        generate_live_prompt(index)[0] for index in range(len(bank["questions"]))
    ]

    assert len(set(prompts)) == len(bank["questions"])
