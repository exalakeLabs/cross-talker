from __future__ import annotations

from cross_talker.models import ProviderAnswer

SYSTEM_PROMPT = """You are one participant in a multi-model review.
Answer accurately and independently. When reviewing peer answers, identify concrete errors,
retain correct insights, and provide your own corrected answer. Do not defer to consensus."""


def build_review_prompt(
    original_prompt: str,
    reviewer: str,
    peer_answers: list[ProviderAnswer],
    round_number: int,
) -> str:
    rendered = "\n\n".join(
        f"--- Answer from {answer.provider} ({answer.model}) ---\n{answer.content}"
        for answer in peer_answers
    )
    return f"""Original question:
{original_prompt}

You are {reviewer}. This is cross-check round {round_number}.
Review the other model answers below. Check their factual claims and reasoning, explain any
disagreement, then give your best standalone answer to the original question.

{rendered}"""


def build_conclusion_prompt(
    original_prompt: str,
    final_answers: list[ProviderAnswer],
) -> str:
    rendered = "\n\n".join(
        f"--- Final answer from {answer.provider} ({answer.model}) ---\n{answer.content}"
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
