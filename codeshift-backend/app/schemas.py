from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


class ConvertRequest(BaseModel):
    code: str
    filename: str
    source_language: str
    target_language: str
    allow_ai_fallback: bool = True


class CapabilityResponse(BaseModel):
    service: str
    version: str
    service_version: str
    supported_languages: list[str]
    rule_patterns: list[str]
    rule_summary: str
    default_execution_mode: str
    supports_ai_fallback: bool
    error_codes: list[str]
    capability_hint: str
    request_log_retention_days: int
    idempotency_ttl_days: int
    allowed_provider_names: list[str]
    allowed_base_url_prefixes: list[str]
    convert_requests_per_minute: int
    provider_test_requests_per_minute: int
    rate_limit_window_seconds: int
    runtime_storage_backend: str
    multi_instance_safe: bool


class BaseSkillResponse(BaseModel):
    success: bool
    message: str = ""
    error_code: str = ""
    capability_hint: str = ""
    service_version: str
    warnings: list[str] = Field(default_factory=list)
    trace_id: str


class LoadFileResponse(BaseSkillResponse):
    filename: str = ""
    content: str = ""
    language: str = ""


class ProviderTestResponse(BaseSkillResponse):
    provider_name: str = ""
    model: str = ""
    base_url: str = ""


class ConvertResponse(BaseSkillResponse):
    converted_code: str = ""
    source_language: str = ""
    target_language: str = ""
    filename: str = ""
    execution_mode: Literal[
        "rule_based",
        "rule_only_failed",
        "ai_fallback",
        "ai_fallback_failed",
        "idempotency_conflict",
        "idempotency_pending",
        "provider_policy_rejected",
        "rate_limited",
    ]
    rule_match_type: str = ""
    rule: str = ""
    idempotency_key: str = ""
    idempotent_replay: bool = False


@dataclass
class PrintOperation:
    kind: str
    value: str


@dataclass
class RuleProgram:
    variables: list[tuple[str, str]]
    outputs: list[PrintOperation]
