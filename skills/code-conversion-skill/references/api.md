# API

Base URL depends on deployment. Current production frontend calls:

- `https://codeshift-production.up.railway.app`

## Endpoints

### `GET /v1/capabilities`

Returns the current lightweight support surface.

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

Current failure codes:

- `RULE_NOT_MATCHED`
- `AI_FALLBACK_FAILED`
- `INVALID_UTF8_FILE`
- `FILE_LOAD_FAILED`
- `PROVIDER_TEST_FAILED`
- `IDEMPOTENCY_KEY_REUSED`

Current rule match types:

- `direct_print`
- `string_variable_print`
- `greet_example`
- `string_concatenation`
- `lightweight_rule`

### `POST /test-provider`

Use only when validating provider reachability before a conversion.

## Runtime Storage

File-backed request logs and idempotency records are written under `CODESHIFT_STORAGE_DIR`.

- Request log file: `logs/requests.jsonl`
- Idempotency cache: `idempotency/*.json`
