# CodeShift

CodeShift is a lightweight code-conversion service with three surfaces:

- a Next.js playground for human testing
- a FastAPI backend for conversion requests
- a first-pass agent skill package for AI clients that need a stable conversion contract

The current system is optimized for single-file or snippet-sized conversions, not full-project migrations.

## Repository Layout

```text
codeshift-frontend/                 Next.js playground
codeshift-backend/                  FastAPI API and conversion engine
skills/code-conversion-skill/       Agent-facing skill package and references
```

## Current Capabilities

- Detects `python`, `cpp`, `java`, and `javascript` from filenames
- Applies lightweight deterministic conversion for:
  - simple string variables
  - direct print/log statements
  - basic `greet(...)` examples
  - simple string concatenation
- Falls back to an OpenAI-compatible API call when no lightweight rule matches
- Keeps provider API keys in memory for the current browser session instead of persisting them to local storage
- Exposes a skill-oriented API contract with:
  - `GET /v1/capabilities`
  - `POST /v1/convert`
  - `POST /test-provider`
- Supports optional `X-Idempotency-Key` on conversion requests
- Uses pluggable runtime storage for request logs, idempotency records, and rate-limit state, with Redis available for multi-instance coordination

## Skill/API Contract

The first-pass skill package lives at:

- [skills/code-conversion-skill/SKILL.md](skills/code-conversion-skill/SKILL.md)

Supporting references:

- [skills/code-conversion-skill/references/api.md](skills/code-conversion-skill/references/api.md)
- [skills/code-conversion-skill/references/supported-patterns.md](skills/code-conversion-skill/references/supported-patterns.md)
- [skills/code-conversion-skill/references/failure-modes.md](skills/code-conversion-skill/references/failure-modes.md)
- [skills/code-conversion-skill/references/examples.md](skills/code-conversion-skill/references/examples.md)
- [codeshift-backend/contract_snapshots/v1.5.json](codeshift-backend/contract_snapshots/v1.5.json) as the machine-readable contract snapshot

Current service contract version:

- `service_version = v1.5`

Current `GET /v1/capabilities` includes:

- supported languages and rule patterns
- current failure codes
- capability hint text
- request log retention days
- idempotency TTL days
- allowed provider names and base URL prefixes
- current rate-limit defaults
- current runtime storage backend and whether it is multi-instance safe

Current `POST /v1/convert` includes:

- `trace_id`
- `service_version`
- `execution_mode`
- `rule_match_type`
- `warnings`
- `capability_hint`
- `error_code` on failures
- `idempotency_key`
- `idempotent_replay`
- provider-policy and rate-limit rejection modes
- runtime storage unavailable rejection mode
- idempotency in-progress rejection mode

Current snapshot-backed contract coverage also includes:

- `POST /test-provider` success and failure response shapes
- `POST /load-file` success and invalid UTF-8 failure response shapes

## Local Development

### Backend

```bash
cd codeshift-backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Environment variables:

- `OPENAI_API_KEY`: required for AI fallback
- `OPENAI_BASE_URL`: optional OpenAI-compatible base URL
- `OPENAI_MODEL`: optional model override, defaults to `gpt-5.4-mini`
- `CODESHIFT_ALLOWED_ORIGINS`: optional comma-separated frontend origins for CORS
- `CODESHIFT_STORAGE_DIR`: optional runtime storage directory for logs and idempotency cache
- `CODESHIFT_REQUEST_LOG_RETENTION_DAYS`: optional request-log retention window, defaults to `7`
- `CODESHIFT_IDEMPOTENCY_TTL_DAYS`: optional idempotency cache TTL, defaults to `3`
- `CODESHIFT_ALLOWED_PROVIDER_NAMES`: optional provider-name allowlist
- `CODESHIFT_ALLOWED_BASE_URL_PREFIXES`: optional base-URL prefix allowlist
- `CODESHIFT_CONVERT_REQUESTS_PER_MINUTE`: optional convert request rate limit, defaults to `20`
- `CODESHIFT_PROVIDER_TEST_REQUESTS_PER_MINUTE`: optional provider test rate limit, defaults to `10`
- `CODESHIFT_RATE_LIMIT_WINDOW_SECONDS`: optional rate-limit window, defaults to `60`
- `CODESHIFT_RUNTIME_STORE_BACKEND`: `filesystem` or `redis`, defaults to `filesystem`
- `CODESHIFT_RUNTIME_STORE_REDIS_URL`: required when `CODESHIFT_RUNTIME_STORE_BACKEND=redis`
- `CODESHIFT_RUNTIME_STORE_KEY_PREFIX`: optional Redis key prefix, defaults to `codeshift`

### Frontend

```bash
cd codeshift-frontend
npm install
npm run dev
```

Optional environment variables:

- `NEXT_PUBLIC_API_URL`: backend base URL, defaults to `http://127.0.0.1:8000`

## Runtime Storage

Backend runtime storage supports two backends:

- `filesystem`: local files under `CODESHIFT_STORAGE_DIR`
- `redis`: shared runtime state for multi-instance deployments

Filesystem contents under `CODESHIFT_STORAGE_DIR`:

- `logs/requests.jsonl`: request event log
- `idempotency/*.json`: idempotency cache records
- `rate_limits/*.json`: rate-limit buckets

Storage policy:

- request logs are pruned by retention window
- idempotency records expire by TTL
- Redis rate limits use a shared fixed window per fingerprint and window start
- Redis idempotency keys use shared pending/completed records for cross-instance replay and in-progress protection
- Redis/runtime storage failures return `RUNTIME_STORE_UNAVAILABLE` instead of an unstructured 500 response
- request logs store `code_sha256` and `code_length`, not raw source code

## Deployment Notes

- Frontend preview deployments are handled by Vercel
- The current live demo is [code-shift-sigma.vercel.app](https://code-shift-sigma.vercel.app)
- The production frontend currently calls the Railway backend at `https://codeshift-production.up.railway.app`
- For deployed environments, set `CODESHIFT_ALLOWED_ORIGINS` to include every frontend origin that should call the backend
- If you deploy the backend separately, make sure the runtime storage path is writable

## Validation

```bash
cd codeshift-frontend && npm run lint
cd codeshift-frontend && npm run build
python3 -m py_compile codeshift-backend/main.py codeshift-backend/app/*.py
cd codeshift-backend && python3 -m unittest -v
```

## CI

GitHub Actions currently runs `Skill API Checks` for the skill/API branch work. The backend and frontend checks include snapshot-based contract regression checks before merge for `/v1/capabilities`, `/v1/convert`, `/test-provider`, and `/load-file`.

## Known Gaps

- Rule-based conversion still covers only lightweight code patterns
- Anything outside the supported lightweight patterns relies on AI fallback
- Filesystem runtime storage is still single-instance; use Redis backend for multi-instance coordination
- Request logging is shared in Redis, but long-term analytics/export is still not a durable observability pipeline
