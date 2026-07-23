# Cross Talker

Cross Talker is a Python service layer that sends one prompt to multiple language-model
providers, then asks each provider to critique the other providers' latest answers for a
configurable number of rounds.

It currently includes adapters for OpenAI-compatible chat completions and Anthropic Messages.
The core orchestration depends only on a tiny provider protocol, so Gemini, local models, or
other services can be added without changing the round-robin logic.

## How it works

1. Round 0 sends the original prompt to all selected providers concurrently.
2. Each cross-check round sends every model the latest answers from all *other* models.
3. The model must inspect factual claims and reasoning, then return a corrected standalone answer.
4. The API returns the full round history and the final answer from each provider.

Every run is also written to SQLite under `./data/cross_talker.db`. The audit record includes the original prompt, each exact
provider-specific prompt, every answer, provider and model names, iteration level, status, and UTC
request/response timestamps. Configure its location with `CROSS_TALKER_DATABASE_PATH`.

The service deliberately does not declare a single answer the winner yet. Consensus scoring,
fact-check tools, a judge model, persistence, and streaming are natural next layers, but keeping
the first foundation transparent makes disagreements inspectable.

## Setup

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Add API keys to `.env`, then start the service:

```bash
cross-talker
```

Interactive API docs are available at `http://localhost:8000/docs`.

Audit history is available through:

```text
GET /v1/runs
GET /v1/runs/{run_id}
```

## Local interaction browser

The React interface in `ui/` presents stored runs as a spreadsheet-style interaction ledger.
It groups exchanges by iteration level, color-codes providers, and opens the full prompt and answer
when a row is selected.

Start the Python API:

```bash
source .venv/bin/activate
cross-talker
```

In another terminal, start the UI:

```bash
cd ui
pnpm install
pnpm dev
```

Open `http://localhost:3000`. The UI reads history from `http://localhost:8000` by default.
Set `NEXT_PUBLIC_API_URL` before starting the UI if the API uses another address.

## Example

```bash
curl http://localhost:8000/v1/cross-talk \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "What is the capital of France, and why?",
    "rounds": 2,
    "providers": ["openai", "anthropic"]
  }'
```

`rounds: 0` returns only the independent initial answers. `rounds: 2` performs two subsequent
peer-review passes. The configured maximum prevents accidentally expensive requests.

## Use as a library

```python
from cross_talker import CrossTalker

# Any object with `name`, `model`, and async `complete(...)` works as a provider.
service = CrossTalker([provider_a, provider_b], default_rounds=2)
result = await service.ask("Your question")
```

## Add a provider

Implement this contract and pass instances into `CrossTalker`:

```python
class MyProvider:
    name = "my-provider"
    model = "my-model"

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> str:
        ...
```

For API configuration, register the adapter in `cross_talker.factory.build_cross_talker`.

## Development

```bash
pytest
ruff check .
```

The default suite exercises the HTTP API and SQLite persistence with a deterministic fake
provider. It never spends provider credits. To run the opt-in live test through the same HTTP
endpoint using the configured OpenAI account:

```bash
RUN_LIVE_TESTS=1 pytest tests/test_live_service.py -v -s
```

Set `NUM_PROMPTS` to run multiple independently generated prompts in the same test invocation:

```bash
NUM_PROMPTS=5 RUN_LIVE_TESTS=1 pytest tests/test_live_service.py -v -s
```

Each prompt creates its own persisted run in the configured `data/cross_talker.db`.
`NUM_PROMPTS` defaults to 1 and is limited to 20 to
guard against accidental provider charges. The live test verifies every API response and retrieves
each saved exchange through `GET /v1/runs/{run_id}`. It prints every prompt and its shared seed,
To use a disposable or alternate database, set `LIVE_TEST_DATABASE_PATH`. To replay the same
prompt sequence:

```bash
LIVE_TEST_SEED=<printed-seed> NUM_PROMPTS=5 RUN_LIVE_TESTS=1 \
  pytest tests/test_live_service.py -v -s
```

To run a live cross-talk test that pits OpenAI and Claude against each other, set the number of
peer-review levels with `CROSS_TALK_ROUNDS`:

```bash
CROSS_TALK_ROUNDS=2 RUN_CROSS_TALK_TESTS=1 \
  pytest tests/test_live_cross_talk.py -v -s
```

This produces two independent answers at level 0, then passes each answer to the other model for
the requested number of review levels. The test confirms that every engineered prompt contains
only the peer's previous answer and that all prompts, replies, providers, levels, and timestamps
are persisted to the configured `data/cross_talker.db`. The round count defaults to 2 and is
limited to 100. Because two providers are called at every level, 100 review levels generate 202
billable API calls including the two initial responses. Set `LIVE_TEST_DATABASE_PATH` if you
explicitly want a different database.
