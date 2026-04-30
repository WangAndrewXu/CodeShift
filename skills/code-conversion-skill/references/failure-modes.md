# Failure Modes

## `rule_only_failed`

Error code:

- `RULE_NOT_MATCHED`

Meaning:

- No lightweight rule matched
- AI fallback was disabled

Recommended agent behavior:

- Tell the caller the input exceeded current lightweight support
- Suggest enabling AI fallback or simplifying the example

## `ai_fallback_failed`

Error code:

- `AI_FALLBACK_FAILED`

Meaning:

- Rule engine did not match
- AI fallback was attempted
- Provider call failed or returned an unusable result

Recommended agent behavior:

- Surface the backend message directly
- Do not claim deterministic conversion succeeded
- If relevant, suggest testing the provider with `POST /test-provider`

## Provider test failure

Error code:

- `PROVIDER_TEST_FAILED`

Meaning:

- `POST /test-provider` was called
- The provider could not be reached or returned an invalid response

## Idempotency key reuse

Error code:

- `IDEMPOTENCY_KEY_REUSED`

Meaning:

- `POST /v1/convert` was retried with an existing `X-Idempotency-Key`
- The request body or provider configuration changed

Recommended agent behavior:

- Generate a new idempotency key whenever request contents change
- Reuse the same key only for exact retry semantics

## Runtime storage unavailable

Error code:

- `RUNTIME_STORE_UNAVAILABLE`

Meaning:

- The backend could not read or write runtime state for rate limits or idempotency
- In Redis mode, this usually means the Redis URL, credentials, or network path is invalid

Recommended agent behavior:

- Treat the request as not completed
- Retry only after the operator confirms runtime storage has recovered
- Preserve `trace_id` when reporting the failure

## Traceability

Every API response now includes `trace_id`.

Recommended agent behavior:

- Preserve `trace_id` in logs or surfaced debugging output
- Include it when reporting backend failures or asking for operator support

## Unsupported scale

If the user asks for repository-wide or framework migration, do not route through this skill. Use a broader engineering workflow instead.
