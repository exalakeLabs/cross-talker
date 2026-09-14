from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Iterable, Mapping
from time import perf_counter

import httpx

from cross_talker.exceptions import ConfigurationError, ProviderCallError
from cross_talker.models import CrossTalkResponse, ProviderAnswer, RoundResult, RunRecap
from cross_talker.prompts import SYSTEM_PROMPT, build_recap_prompt, build_review_prompt
from cross_talker.providers.base import ModelProvider
from cross_talker.storage import SQLiteRepository

logger = logging.getLogger("uvicorn.error")


class CrossTalker:
    """Distributes a prompt and iteratively cross-checks provider responses."""

    def __init__(
        self,
        providers: Iterable[ModelProvider],
        *,
        default_rounds: int = 1,
        max_rounds: int = 20,
        repository: SQLiteRepository | None = None,
    ) -> None:
        self._providers: Mapping[str, ModelProvider] = {
            provider.name.lower(): provider for provider in providers
        }
        if not self._providers:
            raise ConfigurationError("CrossTalker requires at least one provider")
        self.default_rounds = default_rounds
        self.max_rounds = max_rounds
        self.repository = repository or SQLiteRepository(":memory:")

    @property
    def provider_names(self) -> list[str]:
        return list(self._providers)

    async def ask(
        self,
        prompt: str,
        *,
        rounds: int | None = None,
        providers: list[str] | None = None,
    ) -> CrossTalkResponse:
        selected = self._select(providers)
        round_count = self.default_rounds if rounds is None else rounds
        if not 0 <= round_count <= self.max_rounds:
            raise ConfigurationError(f"rounds must be between 0 and {self.max_rounds}")
        if round_count > 0 and len(selected) < 2:
            raise ConfigurationError(
                "Cross-check rounds require at least two providers; use rounds=0 "
                "for a single-provider run"
            )

        run_id, created_at = await self.repository.create_run(prompt, round_count)
        try:
            initial = await self._run_initial(run_id, prompt, selected)
            history = [RoundResult(round=0, answers=initial)]
            latest = initial

            for round_number in range(1, round_count + 1):
                latest = await self._run_review(
                    run_id, prompt, selected, latest, round_number
                )
                history.append(RoundResult(round=round_number, answers=latest))
            await self._generate_recap(run_id, prompt, selected[0], history)
        except Exception:
            await self.repository.finish_run(run_id, "failed")
            raise
        await self.repository.finish_run(run_id, "completed")

        return CrossTalkResponse(
            run_id=run_id,
            prompt=prompt,
            created_at=created_at,
            rounds_completed=round_count,
            history=history,
            final_answers=latest,
        )

    async def _generate_recap(
        self,
        run_id: str,
        prompt: str,
        provider: ModelProvider,
        history: list[RoundResult],
    ) -> None:
        answers = [answer for level in history for answer in level.answers]
        recap_prompt = build_recap_prompt(prompt, answers)
        try:
            content = await provider.complete(
                recap_prompt,
                system_prompt=(
                    "You synthesize multi-model discussions faithfully. "
                    "Return only the requested JSON."
                ),
            )
            cleaned = content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.removeprefix("```json").removeprefix("```")
                cleaned = cleaned.removesuffix("```").strip()
            payload = json.loads(cleaned)
            payload["generated_by"] = provider.name
            recap = RunRecap.model_validate(payload)
            await self.repository.save_recap(run_id, recap)
            logger.info(
                "run_recap_completed run_id=%s provider=%s model=%s",
                run_id,
                provider.name,
                provider.model,
            )
        except Exception as exc:
            logger.exception(
                "run_recap_failed run_id=%s provider=%s model=%s error_type=%s error=%r",
                run_id,
                provider.name,
                provider.model,
                type(exc).__name__,
                exc,
            )
            await self.repository.save_recap(
                run_id,
                None,
                f"{type(exc).__name__}: {exc}",
            )

    def _select(self, names: list[str] | None) -> list[ModelProvider]:
        if names is None:
            selected = list(self._providers.values())
        else:
            missing = [name for name in names if name.lower() not in self._providers]
            if missing:
                raise ConfigurationError(f"Unknown providers: {', '.join(missing)}")
            selected = [self._providers[name.lower()] for name in names]
        if not selected:
            raise ConfigurationError("At least one provider is required")
        return selected

    async def _run_initial(
        self, run_id: str, prompt: str, providers: list[ModelProvider]
    ) -> list[ProviderAnswer]:
        return await self._gather(
            [
                self._call(run_id, provider, prompt, round_number=0)
                for provider in providers
            ]
        )

    async def _run_review(
        self,
        run_id: str,
        prompt: str,
        providers: list[ModelProvider],
        previous: list[ProviderAnswer],
        round_number: int,
    ) -> list[ProviderAnswer]:
        calls = []
        for provider in providers:
            peers = [answer for answer in previous if answer.provider != provider.name]
            review_prompt = build_review_prompt(prompt, provider.name, peers, round_number)
            calls.append(
                self._call(run_id, provider, review_prompt, round_number=round_number)
            )
        return await self._gather(calls)

    async def _call(
        self,
        run_id: str,
        provider: ModelProvider,
        prompt: str,
        *,
        round_number: int,
    ) -> ProviderAnswer:
        exchange_id, requested_at = await self.repository.begin_exchange(
            run_id, provider.name, provider.model, round_number, prompt
        )
        started_at = perf_counter()
        logger.info(
            "provider_call_started run_id=%s exchange_id=%s provider=%s model=%s round=%d",
            run_id,
            exchange_id,
            provider.name,
            provider.model,
            round_number,
        )
        try:
            content = await provider.complete(prompt, system_prompt=SYSTEM_PROMPT)
        except Exception as exc:
            elapsed_seconds = perf_counter() - started_at
            cause = exc.__cause__
            http_error = exc if isinstance(exc, httpx.HTTPStatusError) else cause
            if isinstance(http_error, httpx.HTTPStatusError):
                response = http_error.response
                response_detail = response.text[:2_000].replace("\n", "\\n")
                diagnostic_detail = (
                    f"error_type={type(exc).__name__}\n"
                    f"status_code={response.status_code}\n"
                    f"response_body={response_detail}"
                )
                logger.exception(
                    "provider_call_failed run_id=%s exchange_id=%s provider=%s model=%s "
                    "round=%d elapsed_seconds=%.3f error_type=%s status_code=%d "
                    "response_body=%r",
                    run_id,
                    exchange_id,
                    provider.name,
                    provider.model,
                    round_number,
                    elapsed_seconds,
                    type(exc).__name__,
                    response.status_code,
                    response_detail,
                )
            else:
                diagnostic_detail = (
                    f"error_type={type(exc).__name__}\n"
                    f"error={exc!r}\n"
                    f"cause_type={type(cause).__name__ if cause else None}\n"
                    f"cause={cause!r}"
                )
                logger.exception(
                    "provider_call_failed run_id=%s exchange_id=%s provider=%s model=%s "
                    "round=%d elapsed_seconds=%.3f error_type=%s error=%r "
                    "cause_type=%s cause=%r",
                    run_id,
                    exchange_id,
                    provider.name,
                    provider.model,
                    round_number,
                    elapsed_seconds,
                    type(exc).__name__,
                    exc,
                    type(cause).__name__ if cause else None,
                    cause,
                )
            await self.repository.fail_exchange(
                exchange_id, str(exc), diagnostic_detail
            )
            raise ProviderCallError(
                f"{provider.name} failed during round {round_number}: {exc}"
            ) from exc
        elapsed_seconds = perf_counter() - started_at
        logger.info(
            "provider_call_completed run_id=%s exchange_id=%s provider=%s model=%s "
            "round=%d elapsed_seconds=%.3f response_chars=%d",
            run_id,
            exchange_id,
            provider.name,
            provider.model,
            round_number,
            elapsed_seconds,
            len(content),
        )
        responded_at = await self.repository.finish_exchange(exchange_id, content)
        return ProviderAnswer(
            exchange_id=exchange_id,
            provider=provider.name,
            model=provider.model,
            content=content,
            round=round_number,
            prompt_sent=prompt,
            requested_at=requested_at,
            responded_at=responded_at,
        )

    async def _gather(
        self, calls: list[Awaitable[ProviderAnswer]]
    ) -> list[ProviderAnswer]:
        return list(await asyncio.gather(*calls))
