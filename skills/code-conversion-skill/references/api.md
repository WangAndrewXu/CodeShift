# API

Base URL depends on deployment. Current production frontend calls:

- `https://codeshift-production.up.railway.app`

## Endpoints

### `GET /v1/capabilities`

Returns the current lightweight support surface, provider policy, and rate-limit settings.

Example response fields:

- `service`
- `version`
- `service_version`
- `supported_languages`
- `rule_patterns`
- `rule_summary`
- `default_execution_mode`
- `supports_ai_fallback`
- `error_codes`
- `capability_hint`
- `request_log_retention_days`
- `idempotency_ttl_days`
- `allowed_provider_names`
- `allowed_base_url_prefixes`
- `convert_requests_per_minute`
- `provider_test_requests_per_minute`
- `rate_limit_window_seconds`

### `POST /v1/convert`

Request body:

```json
{
  "code": "name = \"Alice\"\nprint(\"Hello, \" + name)\n",
  "filename": "demo.py",
  "source_language": "python",
  "target_language": "javascript",
  "allow_ai_fallback": false
}
```

Optional provider override headers:

- `X-API-Key`
- `X-Base-URL`
- `X-Model`
- `X-Provider-Name`
- `X-Idempotency-Key`

Response fields:

- `success`
- `converted_code`
- `message`
- `source_language`
- `target_language`
- `filename`
- `execution_mode`
- `rule_match_type`
- `rule`
- `warnings`
- `capability_hint`
- `service_version`
- `trace_id`
- `idempotency_key`
- `idempotent_replay`
- `error_code` on failures

Execution modes currently returned:

- `rule_based`
- `rule_only_failed`
- `ai_fallback`
- `ai_fallback_failed`
- `idempotency_conflict`
- `provider_policy_rejected`
- `rate_limited`

Current failure codes:

- `RULE_NOT_MATCHED`
- `AI_FALLBACK_FAILED`
- `INVALID_UTF8_FILE`
- `FILE_LOAD_FAILED`
- `PROVIDER_TEST_FAILED`
- `IDEMPOTENCY_KEY_REUSED`
- `PROVIDER_POLICY_REJECTED`
- `RATE_LIMIT_EXCEEDED`

Current rule match types:

- `direct_print`
- `string_variable_print`
- `greet_example`
- `string_concatenation`
- `lightweight_rule`

### `POST /test-provider`

Use only when validating provider reachability before a conversion.

Response fields:

- `success`
- `message`
- `error_code`
- `provider_name`
- `model`
- `base_url`
- `capability_hint`
- `service_version`
- `warnings`
- `trace_id`

### `POST /load-file`

Use when the client wants the backend to decode an uploaded source file and infer language from filename.

Response fields:

- `success`
- `message`
- `error_code`
- `filename`
- `content`
- `language`
- `capability_hint`
- `service_version`
- `warnings`
- `trace_id`

## Provider Policy

Current server-side policy allows only configured provider names and base URL prefixes.

Default provider names:

- `openai`
- `openai-compatible`
- `openrouter`

Default allowed base URL prefixes:

- `https://api.openai.com/v1`
- `https://openrouter.ai/api/v1`
- plus `OPENAI_BASE_URL` when configured on the server

## Rate Limits

Default rate limits are file-backed and enforced per client fingerprint.

- convert requests: `20` per `60` seconds
- provider test requests: `10` per `60` seconds

Environment controls:

- `CODESHIFT_CONVERT_REQUESTS_PER_MINUTE`
- `CODESHIFT_PROVIDER_TEST_REQUESTS_PER_MINUTE`
- `CODESHIFT_RATE_LIMIT_WINDOW_SECONDS`

## Runtime Storage

File-backed request logs and idempotency records are written under `CODESHIFT_STORAGE_DIR`.

- Request log file: `logs/requests.jsonl`
- Idempotency cache: `idempotency/*.json`
- Rate-limit buckets: `rate_limits/*.json`

Retention controls:

- `CODESHIFT_REQUEST_LOG_RETENTION_DAYS` defaults to `7`
- `CODESHIFT_IDEMPOTENCY_TTL_DAYS` defaults to `3`

## Contract Snapshots

The repository keeps the current contract snapshot at `codeshift-backend/contract_snapshots/v1.4.json`.

Use it as the canonical machine-readable reference for:

- required response keys
- expected capability defaults
- provider policy and rate-limit defaults
- success/failure shape regression checks for `/v1/convert`, `/test-provider`, and `/load-file`
