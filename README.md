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
4. After the final review round, a lead model receives every final response and synthesizes one
   standalone conclusion that preserves consensus, exposes disagreements, and states uncertainty.
5. The API returns the full round history, each provider's final answer, and the synthesis.

Every run is also written to SQLite under `./data/cross_talker.db`. The audit record includes the original prompt, each exact
provider-specific prompt, every answer, the conclusion synthesis and its complete input prompt,
provider and model names, exchange kind, iteration level, status, and UTC request/response
timestamps. Configure its location with `CROSS_TALKER_DATABASE_PATH`.

The synthesis is not treated as an opaque declaration of truth. Its source responses remain in
the audit ledger, and the UI lets users inspect the exact prompt used to produce it. External
fact-check tools, confidence scoring, and streaming remain natural future layers.

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

The React interface in `ui/` presents stored runs as a spreadsheet-style interaction ledger. A
conclusion panel summarizes each completed interaction, while the evidence table retains every
provider response by review level. Selecting **Inspect synthesis inputs** reveals the exact final
responses supplied to the synthesis engine. Selecting **Export training record (.jsonl)** downloads
a portable record containing a conventional user/assistant message pair plus Cross Talker
provenance: the run identifier, final provider responses, synthesis input, provider/model names,
review depth, and timestamps. The export stays in the browser; the API does not write arbitrary
paths on the host machine.

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

To stop both local services listening on ports 3000 and 8000:

```bash
./scripts/reset.sh
```

The reset script attempts a graceful shutdown and only forces termination if a process remains
after five seconds. It is safe to run when one or both services are already stopped.

### HTTPS on the local network

Start both services with HTTPS and expose them to other devices on the `192.168.4.x` local
network:

```bash
./scripts/dev-network.sh
```

The script generates a 30-day development certificate under `.certs/`, binds both services to all
network interfaces, and prints the detected LAN URL. For example:

```text
https://192.168.4.25:3000
```

The API is available on the same hostname at port 8000. The UI derives that API address from the
hostname used in the browser, so a phone or another computer does not attempt to connect to its own
`localhost`.

Because this is a self-signed development certificate, import and trust `.certs/dev.crt` on each
device before opening the URL. Set `CROSS_TALKER_LAN_IP` when automatic address detection chooses
the wrong network interface:

```bash
CROSS_TALKER_LAN_IP=192.168.4.25 ./scripts/dev-network.sh
```

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

`rounds: 0` skips peer review but still produces a conclusion from the independent answer set.
`rounds: 2` performs two peer-review passes followed by one synthesis call. The configured maximum
prevents accidentally expensive requests.

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
Prompts are selected from `tests/data/live_questions.json`, which spans factual, quantitative,
analytical, practical, ethical, and creative topics with varied response styles. `NUM_PROMPTS`
defaults to 1 and is limited to the 42 questions in the bank to
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

Use `NUM_PROMPTS` to create multiple cross-talk runs, each with a different generated prompt:

```bash
NUM_PROMPTS=10 CROSS_TALK_ROUNDS=5 RUN_CROSS_TALK_TESTS=1 \
  pytest tests/test_live_cross_talk.py -v -s
```

`RUN_CROSS_TALK_TESTS` is an enable flag and must be `1`; it is not the run count. This produces
two independent answers at level 0, then passes each answer to the other model for the requested
number of review levels, followed by one synthesis call. The test confirms that every engineered prompt contains
only the peer's previous answer and that all prompts, replies, providers, levels, and timestamps
are persisted to the configured `data/cross_talker.db`. The round count defaults to 2 and is
limited to 100. Because two providers are called at every level and the lead provider performs the
final synthesis, 100 review levels generate 203 billable API calls including the two initial
responses. Set `LIVE_TEST_DATABASE_PATH` if you
explicitly want a different database.
