from __future__ import annotations

from cross_talker.models import ProviderAnswer

SYSTEM_PROMPT = """You are one participant in a multi-model review.
Answer accurately and independently. When reviewing peer answers, identify concrete errors,
retain correct insights, and provide your own corrected answer. Do not defer to consensus."""

REVIEWER_NAMES = {
    "anthropic": "Claude",
    "openai": "GPT",
}

PROVIDER_NAMES = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
}


def _reviewer_name(provider: str) -> str:
    return REVIEWER_NAMES.get(provider.lower(), provider)


def _provider_name(provider: str) -> str:
    return PROVIDER_NAMES.get(provider.lower(), provider)


def build_review_prompt(
    original_prompt: str,
    reviewer: str,
    peer_answers: list[ProviderAnswer],
    round_number: int,
) -> str:
    reviewer_name = _reviewer_name(reviewer)
    peer_names = ", ".join(_provider_name(answer.provider) for answer in peer_answers)
    rendered = "\n\n".join(
        f"--- Response from {_provider_name(answer.provider)} ({answer.model}) ---\n"
        f"{answer.content}"
        for answer in peer_answers
    )
    prefix = (
        f"This is what {peer_names} responded to the original question. "
        f"You are {reviewer_name}. Evaluate the response below: identify any factual or "
        "reasoning errors, retain correct insights, and then provide your own improved, "
        "standalone answer to the original question."
    )
    return f"""{prefix}

Original question:
{original_prompt}

This is cross-check round {round_number}.

{rendered}"""


def build_recap_prompt(
    original_prompt: str, answers: list[ProviderAnswer]
) -> str:
    transcript = "\n\n".join(
        f"--- {answer.provider} / {answer.model} / level {answer.round} ---\n"
        f"{answer.content[:12_000]}"
        for answer in answers
    )
    return f"""Create a neutral recap of this multi-model discussion.

Original question:
{original_prompt}

Return only valid JSON with this exact structure:
{{
  "provider_emphases": [
    {{
      "provider": "provider name",
      "initial_position": "concise summary",
      "main_emphases": ["specific emphasis"],
      "evolution": "what changed after cross-checking",
      "final_conclusion": "concise final position"
    }}
  ],
  "agreements": ["specific claim supported by the providers"],
  "disagreements": [
    {{
      "topic": "disputed topic",
      "positions": {{"provider name": "position"}},
      "nature": "factual, interpretive, confidence, framing, or other"
    }}
  ],
  "overall_synthesis": "best-supported conclusion, without inventing consensus",
  "unresolved_questions": ["important unresolved question"]
}}

Distinguish genuine agreement from similar wording. If there is no meaningful disagreement,
return an empty disagreements list. Attribute positions accurately and do not add facts that
are absent from the transcript.

Transcript:
{transcript}"""
