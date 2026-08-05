from __future__ import annotations

from cross_talker.models import ProviderAnswer

SYSTEM_PROMPT = """You are one participant in a multi-model review.
Answer accurately and independently. When reviewing peer answers, identify concrete errors,
retain correct insights, and provide your own corrected answer. Do not defer to consensus."""

MODEL_NAMES = {
    "anthropic": "Claude",
    "openai": "GPT",
}


def _model_name(provider: str) -> str:
    return MODEL_NAMES.get(provider.lower(), provider)


def build_review_prompt(
    original_prompt: str,
    reviewer: str,
    peer_answers: list[ProviderAnswer],
    round_number: int,
) -> str:
    reviewer_name = _model_name(reviewer)
    peer_names = ", ".join(_model_name(answer.provider) for answer in peer_answers)
    rendered = "\n\n".join(
        f"--- Answer from {_model_name(answer.provider)} ({answer.model}) ---\n{answer.content}"
        for answer in peer_answers
    )
    prefix = (
        f"This is what {peer_names} generated. YOU are {reviewer_name}, please evaluate "
        "this answer and re-align your next one based on this analysis."
    )
    return f"""{prefix}

Original question:
{original_prompt}

This is cross-check round {round_number}.
Review the other model answers below. Check their factual claims and reasoning, explain any
disagreement, then give your best standalone answer to the original question.

{rendered}"""


def build_conclusion_prompt(
    original_prompt: str,
    final_answers: list[ProviderAnswer],
) -> str:
    rendered = "\n\n".join(
        f"--- Final answer from {_model_name(answer.provider)} ({answer.model}) ---\n"
        f"{answer.content}"
        for answer in final_answers
    )
    return f"""Original question:
{original_prompt}

The participating models have completed their cross-checking. Synthesize their final answers
below into one evidence-aware conclusion for the user.

Your conclusion must:
- answer the original question directly and stand on its own;
- preserve the strongest supported insights from the responses;
- distinguish genuine consensus from unresolved disagreement;
- call out important uncertainty, assumptions, or missing evidence;
- never claim agreement when the responses conflict.

Do not describe this task or merely summarize each model in sequence. Produce the clearest
combined conclusion warranted by the responses.

{rendered}"""
