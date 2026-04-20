# Examples

## Rule-only conversion

Input:

```json
{
  "code": "name = \"Alice\"\nprint(\"Hello, \" + name)\n",
  "filename": "demo.py",
  "source_language": "python",
  "target_language": "javascript",
  "allow_ai_fallback": false
}
```

Typical output:

```json
{
  "success": true,
  "converted_code": "console.log(\"Hello, Alice\");\n",
  "execution_mode": "rule_based",
  "rule_match_type": "string_concatenation",
  "warnings": [],
  "capability_hint": "",
  "service_version": "v1.2",
  "trace_id": "trace_123abc456def",
  "idempotency_key": "convert-demo-1",
  "idempotent_replay": false
}
```

## Rule miss without AI

Input:

```json
{
  "code": "print(\"Hello, \" + get_name())\n",
  "filename": "demo.py",
  "source_language": "python",
  "target_language": "javascript",
  "allow_ai_fallback": false
}
```

Typical output:

```json
{
  "success": false,
  "execution_mode": "rule_only_failed",
  "error_code": "RULE_NOT_MATCHED",
  "warnings": [],
  "capability_hint": "Supported lightweight patterns: simple string variables, direct print/log statements, basic greet(...) examples, simple string concatenation.",
  "service_version": "v1.2",
  "trace_id": "trace_123abc456def",
  "idempotency_key": "",
  "idempotent_replay": false
}
```

## AI fallback conversion

Typical output:

```json
{
  "success": true,
  "execution_mode": "ai_fallback",
  "rule_match_type": "",
  "warnings": [
    "AI fallback was used instead of a lightweight deterministic rule."
  ],
  "capability_hint": "",
  "service_version": "v1.2",
  "trace_id": "trace_123abc456def",
  "idempotency_key": "convert-demo-2",
  "idempotent_replay": false
}
```

## Idempotent replay

If the caller resubmits the same request with the same `X-Idempotency-Key`, the service returns the stored response payload again and marks it as a replay:

```json
{
  "success": true,
  "execution_mode": "rule_based",
  "warnings": [
    "Response replayed from idempotency store."
  ],
  "service_version": "v1.2",
  "trace_id": "trace_123abc456def",
  "idempotency_key": "convert-demo-1",
  "idempotent_replay": true
}
```
