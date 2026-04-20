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

## Traceability

Every API response now includes `trace_id`.

Recommended agent behavior:

- Preserve `trace_id` in logs or surfaced debugging output
- Include it when reporting backend failures or asking for operator support

## Unsupported scale

If the user asks for repository-wide or framework migration, do not route through this skill. Use a broader engineering workflow instead.
