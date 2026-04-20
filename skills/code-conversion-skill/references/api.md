# API

Base URL depends on deployment. Current production frontend calls:

- `https://codeshift-production.up.railway.app`

## Endpoints

### `GET /v1/capabilities`

Returns the current lightweight support surface.

Example response fields:

- `service`
- `version`
- `supported_languages`
- `rule_patterns`
- `rule_summary`
- `default_execution_mode`
- `supports_ai_fallback`
- `error_codes`

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

Response fields:

- `success`
- `converted_code`
- `message`
- `source_language`
- `target_language`
- `filename`
- `execution_mode`
- `rule`
- `trace_id`
- `error_code` on failures

Execution modes currently returned:

- `rule_based`
- `rule_only_failed`
- `ai_fallback`
- `ai_fallback_failed`

Current failure codes:

- `RULE_NOT_MATCHED`
- `AI_FALLBACK_FAILED`
- `INVALID_UTF8_FILE`
- `FILE_LOAD_FAILED`

### `POST /test-provider`

Use only when validating provider reachability before a conversion.
