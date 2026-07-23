from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ProviderAnswer(BaseModel):
    exchange_id: str
    provider: str
    model: str
    content: str
    round: int = Field(ge=0)
    prompt_sent: str
    requested_at: datetime
    responded_at: datetime


class RoundResult(BaseModel):
    round: int = Field(ge=0)
    answers: list[ProviderAnswer]


class CrossTalkRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=100_000)
    rounds: int | None = Field(default=None, ge=0)
    providers: list[str] | None = None

    @model_validator(mode="after")
    def validate_providers(self) -> CrossTalkRequest:
        if self.providers is not None:
            cleaned = [name.strip().lower() for name in self.providers if name.strip()]
            if len(cleaned) < 2:
                raise ValueError("At least two providers are required for cross-checking")
            if len(cleaned) != len(set(cleaned)):
                raise ValueError("Provider names must be unique")
            self.providers = cleaned
        return self


class CrossTalkResponse(BaseModel):
    run_id: str
    prompt: str
    created_at: datetime
    rounds_completed: int
    history: list[RoundResult]
    final_answers: list[ProviderAnswer]


class StoredExchange(BaseModel):
    exchange_id: str
    run_id: str
    provider: str
    model: str
    round: int
    prompt_sent: str
    answer: str | None
    status: str
    error: str | None
    requested_at: datetime
    responded_at: datetime | None


class StoredRun(BaseModel):
    run_id: str
    original_prompt: str
    rounds_requested: int
    status: str
    created_at: datetime
    completed_at: datetime | None
    exchanges: list[StoredExchange] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    configured_providers: list[str]
