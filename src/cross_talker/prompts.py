from __future__ import annotations

from cross_talker.models import ProviderAnswer

SYSTEM_PROMPT = """You are one participant in a multi-model conversation.
Answer accurately, engage directly with the other participants, correct concrete errors, and
advance the discussion with useful new reasoning. Do not defer to consensus."""

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


def build_conversation_prompt(
    original_prompt: str,
    speaker: str,
    conversation: list[ProviderAnswer],
    round_number: int,
    max_peer_answer_chars: int = 8_000,
    max_conversation_chars: int = 24_000,
) -> str:
    speaker_name = _reviewer_name(speaker)
    rendered = _render_conversation(
        conversation,
        max_message_chars=max_peer_answer_chars,
        max_conversation_chars=max_conversation_chars,
    )
    return f"""You are {speaker_name}. Continue the conversation below with the other model.
Respond directly to the latest message, address disagreements or open questions, and advance the
discussion toward a more accurate and useful answer. Do not restart with an isolated answer or
merely summarize the transcript.

Original question:
{original_prompt}

Conversation round {round_number}, your turn:

{rendered}"""


def _bounded_answer(content: str, limit: int) -> str:
    if len(content) <= limit:
        return content
    omitted = len(content) - limit
    return f"{content[:limit]}\n\n[Message truncated; {omitted:,} characters omitted.]"


def _render_conversation(
    answers: list[ProviderAnswer],
    *,
    max_message_chars: int,
    max_conversation_chars: int,
) -> str:
    blocks = [
        f"--- {_provider_name(answer.provider)} ({answer.model}), round {answer.round} ---\n"
        f"{_bounded_answer(answer.content, max_message_chars)}"
        for answer in answers
    ]
    selected: list[str] = []
    used = 0
    for block in reversed(blocks):
        separator = 2 if selected else 0
        remaining = max_conversation_chars - used - separator
        if remaining <= 0:
            break
        selected.append(block if len(block) <= remaining else block[-remaining:])
        used += min(len(block), remaining) + separator
        if len(block) > remaining:
            break
    selected.reverse()
    omitted = len(blocks) - len(selected)
    prefix = f"[{omitted} earlier conversation messages omitted.]\n\n" if omitted else ""
    return prefix + "\n\n".join(selected)


def build_conclusion_prompt(
    original_prompt: str,
    final_answers: list[ProviderAnswer],
) -> str:
    rendered = "\n\n".join(
        f"--- Final answer from {_provider_name(answer.provider)} ({answer.model}) ---\n"
        f"{_bounded_answer(answer.content, 8_000)}"
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


def build_recap_prompt(original_prompt: str, answers: list[ProviderAnswer]) -> str:
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
