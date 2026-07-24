from __future__ import annotations

import json
import os
import random
from functools import lru_cache
from pathlib import Path
from typing import TypedDict


class Question(TypedDict):
    category: str
    text: str


class QuestionBank(TypedDict):
    questions: list[Question]
    response_styles: list[str]


QUESTION_BANK_PATH = Path(__file__).parent / "data" / "live_questions.json"


@lru_cache
def load_question_bank() -> QuestionBank:
    with QUESTION_BANK_PATH.open(encoding="utf-8") as question_file:
        return json.load(question_file)


def generate_live_prompt(
    iteration: int = 0,
    base_seed: str | None = None,
) -> tuple[str, str]:
    """Select a reproducible, non-repeating question and response style."""
    selected_seed = base_seed or os.getenv("LIVE_TEST_SEED") or os.urandom(8).hex()
    bank = load_question_bank()
    generator = random.Random(selected_seed)
    questions = list(bank["questions"])
    response_styles = list(bank["response_styles"])
    generator.shuffle(questions)
    generator.shuffle(response_styles)
    question = questions[iteration % len(questions)]
    response_style = response_styles[iteration % len(response_styles)]
    return f"{question['text']} {response_style}", selected_seed


def get_num_prompts() -> int:
    raw_value = os.getenv("NUM_PROMPTS", "1")
    try:
        count = int(raw_value)
    except ValueError as exc:
        raise ValueError("NUM_PROMPTS must be an integer") from exc
    maximum = len(load_question_bank()["questions"])
    if not 1 <= count <= maximum:
        raise ValueError(f"NUM_PROMPTS must be between 1 and {maximum}")
    return count
