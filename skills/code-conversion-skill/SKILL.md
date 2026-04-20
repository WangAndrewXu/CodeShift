---
name: code-conversion-skill
description: Use this skill when an agent needs to convert a single code snippet or small single-file example between Python, C++, Java, and JavaScript using CodeShift. Prefer it for lightweight rule-first conversion, capability checks, and controlled AI fallback through the CodeShift API.
---

# Code Conversion Skill

Use this skill for small code conversion tasks that fit a single snippet or single file. Do not use it for whole repositories, framework migrations, or build-system migrations.

## Trigger Conditions

Use this skill when the task is one of:

- Convert a small snippet from `python`, `cpp`, `java`, or `javascript` to another supported language
- Check what CodeShift currently supports before attempting a conversion
- Run a rule-first conversion and allow AI fallback only if the caller permits it
- Convert uploaded code text or a short file into another language with a stable JSON API

Do not use this skill when:

- The task spans multiple files or a whole repository
- The user expects AST-accurate or framework-aware migration
- The task requires package manager, build, runtime, or deployment migration

## Workflow

1. Read [references/api.md](references/api.md) for the HTTP contract.
2. If the task may be near the edge of current support, read [references/supported-patterns.md](references/supported-patterns.md).
3. Prefer `GET /v1/capabilities` before assuming support.
4. Use `POST /v1/convert` with `allow_ai_fallback=false` when deterministic conversion is required.
5. Use `POST /v1/convert` with `allow_ai_fallback=true` only when the caller allows model-based fallback.
6. If conversion fails, read [references/failure-modes.md](references/failure-modes.md) and report the failure mode clearly.

## Output Rules

- Preserve the API response fields that matter to the caller:
  - `success`
  - `converted_code`
  - `execution_mode`
  - `rule_match_type`
  - `message`
  - `rule`
  - `service_version`
  - `trace_id`
- On failures, also preserve `error_code` if present.
- If the service returns a rule-only failure, explain that the input exceeded lightweight support rather than claiming the service is broken.
- If AI fallback is disabled, do not silently retry with AI.

## Minimal Decision Policy

- Small snippet and supported language pair: use CodeShift.
- Rule-first requested: set `allow_ai_fallback=false`.
- Best-effort requested: set `allow_ai_fallback=true`.
- Unsupported or large-scale migration: decline to use this skill and switch to a broader engineering workflow.
