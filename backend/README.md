# NutriPilot API

FastAPI + PostgreSQL backend for NutriPilot.

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

API documentation is available at `http://localhost:8000/docs`.

Run the complete API, PostgreSQL and Redis development stack from the repository root:

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f api
```

Create the reproducible two-week demo account after the stack is healthy:

```powershell
$env:NUTRIPILOT_DEMO_PASSWORD = "replace-with-at-least-10-characters"
docker compose exec -e NUTRIPILOT_DEMO_PASSWORD api `
  python -m app.cli.seed_demo --anchor-date 2026-07-22
Remove-Item Env:NUTRIPILOT_DEMO_PASSWORD
```

Repeat with `--reset-existing` to atomically restore the dataset. The command refuses
to replace a non-demo account, rotates the user id on reset to invalidate old tokens,
and never accepts or prints the password as a CLI argument. Demo accounts cannot store
AI credentials or consume the server OpenAI key. See
[`docs/DEMO_ACCOUNT.md`](../docs/DEMO_ACCOUNT.md) for the data story, safety boundary,
verified results, and public-deployment limitations.

## Demo abuse protection and scheduled reset

Demo mutations and AI calls use separate Redis counters. The atomic Lua operation
increments the counter, initializes its TTL, and returns the remaining TTL used for the
HTTP 429 `Retry-After` header. Keys contain only the rotating demo user UUID and action,
not email, IP, query text, or nutrition data. Normal users bypass these demo buckets.

Resource quotas cap demo logs, private foods, conversations, and messages. Enable the
periodic reset by providing `NUTRIPILOT_DEMO_RESET_INTERVAL_MINUTES` and injecting
`NUTRIPILOT_DEMO_RESET_PASSWORD` through the deployment secret store. Every API replica
runs the scheduler, but a Redis `SET NX EX` lock with owner-token Lua release allows only
one reset. The task waits one full interval after startup instead of resetting on deploy.

Run one locked reset for an external scheduler or operational check:

```powershell
$env:NUTRIPILOT_DEMO_RESET_PASSWORD = "replace-with-at-least-10-characters"
docker compose exec -e NUTRIPILOT_DEMO_RESET_PASSWORD api `
  python -m app.cli.reset_demo --anchor-date 2026-07-22
Remove-Item Env:NUTRIPILOT_DEMO_RESET_PASSWORD
```

Development fails open if Redis is unavailable. Production validation requires
`NUTRIPILOT_DEMO_PROTECTION_FAIL_CLOSED=true`, causing protected demo operations to
return 503 instead of silently losing protection. See
[`docs/DEMO_PROTECTION.md`](../docs/DEMO_PROTECTION.md) for verified 429/403 behavior,
quota race limitations, and remaining registration abuse boundary.

Stop the containers without deleting the PostgreSQL volume:

```powershell
docker compose down
```

Run the opt-in concurrency tests against the Docker PostgreSQL API:

```powershell
$env:NUTRIPILOT_POSTGRES_E2E = "1"
pytest tests/test_postgres_concurrency.py -v
Remove-Item Env:NUTRIPILOT_POSTGRES_E2E
```

These tests create isolated accounts and verify concurrent idempotent inserts,
optimistic updates, and refresh-token replay handling. They are skipped by the
default SQLite test suite so CI does not silently depend on a local Docker daemon.

Run the reproducible PostgreSQL API performance baseline from the repository root:

```powershell
npm run load:test
```

The k6 workload uses 10 constant read VUs plus 5 write arrivals per second for 30
seconds. Override `DURATION`, `READ_VUS`, or `WRITE_RPS` by passing environment
variables to the `loadtest` container. Results and interpretation are documented in
[`docs/PERFORMANCE.md`](../docs/PERFORMANCE.md). This is a regression baseline, not a
production capacity claim.

## Quality checks

```powershell
ruff check app tests migrations scripts
ruff format --check app tests migrations scripts
pytest --cov=app
alembic upgrade head --sql
```

Export the committed API contract after changing routes or schemas:

```powershell
python scripts/export_openapi.py openapi.json
cd ..
npm run api:types
```

CI regenerates both artifacts and fails when the backend contract and mobile types drift.

## AI food-text provider

The default `rule_based` provider keeps local development deterministic. To use the
OpenAI Responses provider, configure the key only on the backend:

```powershell
$env:NUTRIPILOT_AI_PROVIDER = "openai"
$env:NUTRIPILOT_OPENAI_API_KEY = "your-server-side-key"
$env:NUTRIPILOT_OPENAI_MODEL = "gpt-5.6-luna"
```

Never put the API key in an `EXPO_PUBLIC_*` variable: those values are bundled into the
client. The provider uses strict structured output, an eight-second timeout by default,
at most two attempts for retryable failures, and a rule-based fallback. Input and output
prices are optional deployment settings; cost remains unpriced unless both are supplied.

- `POST /api/v1/ai/food-text:analyze`: return a confirmable structured draft.
- `POST /api/v1/ai/assistant:answer`: answer a single-turn question using user-scoped read-only tools.
- `GET/POST /api/v1/ai/assistant/conversations`: list or create user-owned conversations.
- `GET/DELETE /api/v1/ai/assistant/conversations/{id}`: read or delete an owned conversation.
- `POST /api/v1/ai/assistant/conversations/{id}/messages`: append an idempotent assistant turn.
- `POST /api/v1/ai/reports/weekly:generate`: generate a fact-grounded personalized weekly report.
- `GET /api/v1/ai/metrics`: return user-scoped call, latency, Token, fallback, and cost totals.

Tests use a mocked HTTP transport and do not require a real key. A passing test therefore
proves request/response handling and failure policy, not live model availability.

Run the versioned Chinese food-text evaluation set without a paid API:

```powershell
python scripts/run_ai_eval.py `
  --output evals/reports/rule_based_v1.json `
  --baseline evals/baselines/rule_based_v1.json
```

The report separates request success from Schema validity and records entity
precision/recall/F1, amount/unit/meal accuracy, exact-match rate, P50/P95 latency,
Tokens, optional cost, model, and Prompt version. Real OpenAI evaluation requires both
`--provider openai` and `--allow-paid-api`; its key is read only from
`NUTRIPILOT_OPENAI_API_KEY`, never from a command-line argument. See
[`docs/AI_EVALUATION.md`](../docs/AI_EVALUATION.md) for definitions and current results.

Authenticated users can alternatively configure their own key through the API:

- `GET /api/v1/ai/credentials`: return configured status and the final four characters.
- `PUT /api/v1/ai/credentials`: encrypt and replace the current user's key.
- `DELETE /api/v1/ai/credentials`: idempotently remove the current user's key.

User keys are encrypted with AES-GCM before PostgreSQL storage. The authenticated user id
is associated data, so ciphertext cannot be moved to another account and still decrypt.
Set `NUTRIPILOT_CREDENTIAL_ENCRYPTION_KEY` to a high-entropy secret in production; the API
rejects the development default in production mode. The backend must decrypt a key while
calling the model, so this is encrypted server-side storage, not end-to-end encryption.
Use HTTPS in every non-local environment and never log request bodies for this endpoint.

## Tool Calling assistant

The assistant exposes only `get_today_summary`, `get_weekly_trend`, and `search_food` to
the model. Tool arguments use strict JSON Schemas, while the authenticated `user_id` is
injected by the server and cannot be selected by the model. The first model round must
call a tool, parallel calls are disabled, and the loop is capped at three tool rounds.
Every successful answer returns human-readable evidence and call telemetry. Missing or
invalid OpenAI credentials fall back to the same deterministic read-only tool runner.
See [`docs/TOOL_CALLING_ASSISTANT.md`](../docs/TOOL_CALLING_ASSISTANT.md) for the security
boundary, sequence, tests, and current limitations.

Conversation and message state is stored in PostgreSQL while Responses requests keep
`store: false`. Each request includes at most eight recent messages and 6,000 characters;
facts must be refreshed through tools on every turn. A client-generated message id makes
completed request retries idempotent, and the API rejects the same id with different
content. See [`docs/CONVERSATION_STATE.md`](../docs/CONVERSATION_STATE.md).

## Health endpoints

- `GET /api/v1/health/live`: process liveness; does not query dependencies.
- `GET /api/v1/health/ready`: readiness; returns 503 when PostgreSQL is unavailable.

## Observability

Every HTTP response includes `X-Request-ID`. The JSON request log contains only a fixed
allowlist of operational fields; raw URL, path parameters, query strings, headers,
bodies, IP addresses, user IDs, and exception messages are excluded. Uvicorn's raw
access log is disabled because it includes query strings.

Sentry is opt-in. Configure `NUTRIPILOT_SENTRY_DSN`, an explicit
`NUTRIPILOT_SENTRY_TRACES_SAMPLE_RATE`, and `NUTRIPILOT_RELEASE` in the deployment
environment. Request bodies, local variables, and default PII remain disabled, and a
`before_send` scrubber removes request details again before transmission. See
[`docs/OBSERVABILITY.md`](../docs/OBSERVABILITY.md) for the privacy boundary and pending
production alert validation.

## Authentication endpoints

- `GET /api/v1/meta/config`: expose the public registration policy to clients.
- `POST /api/v1/auth/register`: create an account and return an access/refresh token pair.
- `POST /api/v1/auth/login`: verify credentials and create a new token family.
- `POST /api/v1/auth/refresh`: rotate a refresh token; replay revokes its active family.
- `POST /api/v1/auth/logout`: idempotently revoke a refresh token.
- `GET /api/v1/users/me`: return the authenticated user for a Bearer access token.

Passwords are hashed with Argon2id. Access tokens expire after 15 minutes by default;
opaque refresh tokens expire after 30 days and only their SHA-256 digests are stored.

Public deployments can set `NUTRIPILOT_PUBLIC_REGISTRATION_ENABLED=false`. Login and
registration use separate Redis fixed-window counters keyed by an HMAC of the normalized
email, plus a shared visitor counter derived from the trusted client address, so Redis
never stores the raw email or IP. Successful login clears only its account counter; the
visitor counter remains to prevent a known credential from resetting the network budget.
Production configuration requires `NUTRIPILOT_AUTH_PROTECTION_FAIL_CLOSED=true` whenever
authentication protection is enabled. This is application-layer abuse mitigation, not a
WAF or DDoS substitute; see [`docs/AUTH_PERIMETER.md`](../docs/AUTH_PERIMETER.md).

`X-Forwarded-For` is considered only when the immediate TCP peer belongs to
`NUTRIPILOT_TRUSTED_PROXY_CIDRS`. The chain is parsed from right to left and malformed or
oversized values fall back to the peer. Uvicorn runs with `--no-proxy-headers` so it
cannot rewrite the peer before this check. Configure `NUTRIPILOT_ALLOWED_HOSTS` explicitly
in production.

Validate deployment configuration without connecting to dependencies:

```powershell
python -m app.cli.production_preflight --portfolio --behind-proxy
```

The API image runs as the unprivileged `nutripilot` user. CI builds the Docker image and
asserts that its runtime UID is not zero. HTTPS should terminate at the deployment
gateway; see [`docs/PRODUCTION_GATEWAY.md`](../docs/PRODUCTION_GATEWAY.md).

## Diet domain endpoints

- `GET/PUT /api/v1/users/me/profile`: read or upsert the current user's profile and targets.
- `GET/POST /api/v1/foods`: search visible foods or create a private catalog food.
- `POST /api/v1/logs`: create a log using a stable client id; safe retries return HTTP 200.
- `GET /api/v1/logs`: list the current user's logs within a bounded date range.
- `GET/PUT/DELETE /api/v1/logs/{id}`: read, replace, or delete an owned log.
- `GET /api/v1/stats/daily`: aggregate the current user's daily nutrition and meal totals.
- `GET /api/v1/sync/changes`: cursor-paginated upserts and deletion tombstones for the current user.

Log creation uses `(user_id, client_id)` as an idempotency boundary. Updates and deletes
require an expected version and return HTTP 409 on optimistic concurrency conflicts.

## Database migrations

Create a candidate migration after changing SQLAlchemy models:

```powershell
alembic revision --autogenerate -m "describe change"
```

Autogenerated migrations must always be reviewed before running them.

`pyproject.toml` declares accepted dependency ranges. The two lock files record the exact
development and runtime environments used by CI and Docker.
