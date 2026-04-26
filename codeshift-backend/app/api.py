from uuid import uuid4

from fastapi import FastAPI, File, Header, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.params import Header as HeaderParam
from pydantic import BaseModel

from .config import (
    get_allowed_base_url_prefixes,
    get_allowed_origins,
    get_allowed_provider_names,
    get_convert_requests_per_minute,
    get_idempotency_ttl_days,
    get_provider_test_requests_per_minute,
    get_rate_limit_window_seconds,
    get_request_log_retention_days,
)
from .provider_policy import build_provider_policy_hint, validate_provider_request
from .providers import ai_convert_fallback, test_ai_connection
from .runtime_store import (
    append_request_log,
    build_request_hash,
    check_rate_limit,
    load_idempotency_record,
    now_utc_iso,
    save_idempotency_record,
    sha256_text,
)
from .rule_engine import (
    RULE_SUPPORT_SUMMARY,
    SERVICE_VERSION,
    SUPPORTED_LANGUAGES,
    SUPPORTED_RULE_PATTERNS,
    detect_language_from_filename,
    detect_rule_match_type,
    extract_rule_program,
    normalize_language,
    render_code,
)
from .schemas import (
    CapabilityResponse,
    ConvertRequest,
    ConvertResponse,
    LoadFileResponse,
    ProviderTestResponse,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


ERROR_CODES = [
    "RULE_NOT_MATCHED",
    "AI_FALLBACK_FAILED",
    "INVALID_UTF8_FILE",
    "FILE_LOAD_FAILED",
    "PROVIDER_TEST_FAILED",
    "IDEMPOTENCY_KEY_REUSED",
    "PROVIDER_POLICY_REJECTED",
    "RATE_LIMIT_EXCEEDED",
]


def new_trace_id():
    return f"trace_{uuid4().hex[:12]}"


def build_capability_hint():
    return f"Supported lightweight patterns: {', '.join(SUPPORTED_RULE_PATTERNS)}."


def normalize_optional_header(value: str | None):
    if isinstance(value, HeaderParam):
        return None
    return value


def as_payload(response: BaseModel | dict):
    if isinstance(response, BaseModel):
        return response.model_dump(mode="json")
    return response


def summarize_code_payload(code: str):
    return {
        "code_sha256": sha256_text(code),
        "code_length": len(code),
    }


def build_client_fingerprint(
    request: Request,
    *,
    provider_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
):
    parts = [request.client.host if request.client else "unknown"]
    if provider_name:
        parts.append(provider_name.strip().lower())
    if base_url:
        parts.append(base_url.strip())
    if api_key:
        parts.append(sha256_text(api_key))
    return "|".join(parts)


def build_rate_limit_warning(limit_result: dict):
    return (
        f"Rate limit reached. Retry after {limit_result['retry_after_seconds']} seconds "
        f"within a {limit_result['window_seconds']}-second window."
    )


def log_api_event(
    endpoint: str,
    trace_id: str,
    response: BaseModel | dict,
    *,
    request: dict | None = None,
    metadata: dict | None = None,
):
    payload = as_payload(response)
    append_request_log(
        {
            "timestamp": now_utc_iso(),
            "endpoint": endpoint,
            "trace_id": trace_id,
            "success": bool(payload.get("success", False)),
            "error_code": payload.get("error_code", ""),
            "execution_mode": payload.get("execution_mode", ""),
            "service_version": payload.get("service_version", SERVICE_VERSION),
            "request": request or {},
            "metadata": metadata or {},
        }
    )


def maybe_store_idempotent_response(
    idempotency_key: str | None,
    request_hash: str,
    response: BaseModel | dict,
):
    if not idempotency_key:
        return

    save_idempotency_record(
        idempotency_key,
        {
            "request_hash": request_hash,
            "response": as_payload(response),
        },
    )


def idempotency_response_fields(idempotency_key: str | None, replay: bool):
    return {
        "idempotency_key": idempotency_key or "",
        "idempotent_replay": replay,
    }


def idempotency_log_metadata(idempotency_key: str | None, request_hash: str, replay: bool):
    return {
        **idempotency_response_fields(idempotency_key, replay),
        "request_hash": request_hash,
    }


@app.get("/")
async def root():
    return {
        "message": "CodeShift backend is running",
        "allowed_origins": get_allowed_origins(),
    }


@app.get("/v1/capabilities", response_model=CapabilityResponse)
async def capabilities():
    return CapabilityResponse(
        service="codeshift",
        version="v1",
        service_version=SERVICE_VERSION,
        supported_languages=SUPPORTED_LANGUAGES,
        rule_patterns=SUPPORTED_RULE_PATTERNS,
        rule_summary=RULE_SUPPORT_SUMMARY,
        default_execution_mode="rule_first",
        supports_ai_fallback=True,
        error_codes=ERROR_CODES,
        capability_hint=build_capability_hint(),
        request_log_retention_days=get_request_log_retention_days(),
        idempotency_ttl_days=get_idempotency_ttl_days(),
        allowed_provider_names=get_allowed_provider_names(),
        allowed_base_url_prefixes=get_allowed_base_url_prefixes(),
        convert_requests_per_minute=get_convert_requests_per_minute(),
        provider_test_requests_per_minute=get_provider_test_requests_per_minute(),
        rate_limit_window_seconds=get_rate_limit_window_seconds(),
    )


@app.post("/load-file", response_model=LoadFileResponse)
async def load_file(file: UploadFile = File(...)):
    trace_id = new_trace_id()
    try:
        raw = await file.read()
        content = raw.decode("utf-8")
        language = detect_language_from_filename(file.filename)

        response = LoadFileResponse(
            success=True,
            filename=file.filename,
            content=content,
            language=language,
            service_version=SERVICE_VERSION,
            warnings=[],
            trace_id=trace_id,
        )
        log_api_event(
            "/load-file",
            trace_id,
            response,
            metadata={
                "filename": file.filename,
                "language": language,
                "bytes_read": len(raw),
            },
        )
        return response
    except UnicodeDecodeError:
        response = LoadFileResponse(
            success=False,
            message="This file is not valid UTF-8 text.",
            error_code="INVALID_UTF8_FILE",
            capability_hint="Upload UTF-8 text source files only.",
            service_version=SERVICE_VERSION,
            warnings=[],
            trace_id=trace_id,
        )
        log_api_event(
            "/load-file",
            trace_id,
            response,
            metadata={"filename": file.filename},
        )
        return response
    except Exception as exc:
        response = LoadFileResponse(
            success=False,
            message=f"Failed to load file: {str(exc)}",
            error_code="FILE_LOAD_FAILED",
            capability_hint="Retry with a plain text source file and a supported extension.",
            service_version=SERVICE_VERSION,
            warnings=[],
            trace_id=trace_id,
        )
        log_api_event(
            "/load-file",
            trace_id,
            response,
            metadata={"filename": getattr(file, "filename", "")},
        )
        return response


@app.post("/test-provider", response_model=ProviderTestResponse)
async def test_provider(
    request: Request,
    x_api_key: str | None = Header(default=None),
    x_base_url: str | None = Header(default=None),
    x_model: str | None = Header(default=None),
    x_provider_name: str | None = Header(default=None),
):
    x_api_key = normalize_optional_header(x_api_key)
    x_base_url = normalize_optional_header(x_base_url)
    x_model = normalize_optional_header(x_model)
    x_provider_name = normalize_optional_header(x_provider_name)
    trace_id = new_trace_id()

    allowed, policy_message = validate_provider_request(x_provider_name, x_base_url)
    if not allowed:
        response = ProviderTestResponse(
            success=False,
            message=policy_message,
            error_code="PROVIDER_POLICY_REJECTED",
            provider_name=x_provider_name or "",
            model=x_model or "",
            base_url=x_base_url or "",
            capability_hint=build_provider_policy_hint(),
            service_version=SERVICE_VERSION,
            warnings=[],
            trace_id=trace_id,
        )
        log_api_event(
            "/test-provider",
            trace_id,
            response,
            metadata={
                "provider_name": x_provider_name or "",
                "base_url": x_base_url or "",
                "policy_rejected": True,
            },
        )
        return response

    fingerprint = build_client_fingerprint(
        request,
        provider_name=x_provider_name,
        base_url=x_base_url,
        api_key=x_api_key,
    )
    rate_result = check_rate_limit(
        "provider-test",
        fingerprint,
        max_requests=get_provider_test_requests_per_minute(),
        window_seconds=get_rate_limit_window_seconds(),
    )
    if not rate_result["allowed"]:
        response = ProviderTestResponse(
            success=False,
            message=build_rate_limit_warning(rate_result),
            error_code="RATE_LIMIT_EXCEEDED",
            provider_name=x_provider_name or "",
            model=x_model or "",
            base_url=x_base_url or "",
            capability_hint="Wait for the current rate-limit window to reset before retrying.",
            service_version=SERVICE_VERSION,
            warnings=[],
            trace_id=trace_id,
        )
        log_api_event(
            "/test-provider",
            trace_id,
            response,
            metadata={
                "provider_name": x_provider_name or "",
                "base_url": x_base_url or "",
                "rate_limit": rate_result,
            },
        )
        return response

    success, message = test_ai_connection(
        api_key=x_api_key,
        base_url=x_base_url,
        model=x_model,
        provider_name=x_provider_name,
    )

    response = ProviderTestResponse(
        success=success,
        message=message,
        error_code="" if success else "PROVIDER_TEST_FAILED",
        provider_name=x_provider_name or "",
        model=x_model or "",
        base_url=x_base_url or "",
        capability_hint="" if success else "Check API key, base URL, model, and provider availability.",
        service_version=SERVICE_VERSION,
        warnings=[],
        trace_id=trace_id,
    )
    log_api_event(
        "/test-provider",
        trace_id,
        response,
        metadata={
            "provider_name": x_provider_name or "",
            "model": x_model or "",
            "base_url": x_base_url or "",
            "api_key_present": bool(x_api_key),
            "rate_limit": rate_result,
        },
    )
    return response


@app.post("/convert", response_model=ConvertResponse)
@app.post("/v1/convert", response_model=ConvertResponse)
async def convert_code(
    data: ConvertRequest,
    request: Request,
    x_api_key: str | None = Header(default=None),
    x_base_url: str | None = Header(default=None),
    x_model: str | None = Header(default=None),
    x_provider_name: str | None = Header(default=None),
    x_idempotency_key: str | None = Header(default=None),
):
    x_api_key = normalize_optional_header(x_api_key)
    x_base_url = normalize_optional_header(x_base_url)
    x_model = normalize_optional_header(x_model)
    x_provider_name = normalize_optional_header(x_provider_name)
    x_idempotency_key = normalize_optional_header(x_idempotency_key)
    trace_id = new_trace_id()
    source_language = normalize_language(data.source_language)
    target_language = normalize_language(data.target_language)
    request_summary = {
        "filename": data.filename,
        "source_language": source_language,
        "target_language": target_language,
        "allow_ai_fallback": data.allow_ai_fallback,
        **summarize_code_payload(data.code),
    }

    allowed, policy_message = validate_provider_request(x_provider_name, x_base_url)
    if not allowed:
        response = ConvertResponse(
            success=False,
            converted_code="",
            source_language="",
            target_language="",
            filename="",
            message=policy_message,
            execution_mode="provider_policy_rejected",
            error_code="PROVIDER_POLICY_REJECTED",
            rule_match_type="",
            rule="",
            capability_hint=build_provider_policy_hint(),
            service_version=SERVICE_VERSION,
            warnings=[],
            trace_id=trace_id,
            **idempotency_response_fields(x_idempotency_key, False),
        )
        log_api_event(
            "/v1/convert",
            trace_id,
            response,
            request=request_summary,
            metadata={"provider_name": x_provider_name or "", "base_url": x_base_url or ""},
        )
        return response

    fingerprint = build_client_fingerprint(
        request,
        provider_name=x_provider_name,
        base_url=x_base_url,
        api_key=x_api_key,
    )
    rate_result = check_rate_limit(
        "convert",
        fingerprint,
        max_requests=get_convert_requests_per_minute(),
        window_seconds=get_rate_limit_window_seconds(),
    )
    if not rate_result["allowed"]:
        response = ConvertResponse(
            success=False,
            converted_code="",
            source_language="",
            target_language="",
            filename="",
            message=build_rate_limit_warning(rate_result),
            execution_mode="rate_limited",
            error_code="RATE_LIMIT_EXCEEDED",
            rule_match_type="",
            rule="",
            capability_hint="Wait for the rate-limit window to reset or reduce request frequency.",
            service_version=SERVICE_VERSION,
            warnings=[],
            trace_id=trace_id,
            **idempotency_response_fields(x_idempotency_key, False),
        )
        log_api_event(
            "/v1/convert",
            trace_id,
            response,
            request=request_summary,
            metadata={"rate_limit": rate_result},
        )
        return response

    request_hash = build_request_hash(
        {
            "request": data.model_dump(mode="json"),
            "provider": {
                "base_url": x_base_url or "",
                "model": x_model or "",
                "provider_name": x_provider_name or "",
                "api_key_sha256": sha256_text(x_api_key) if x_api_key else "",
            },
        }
    )

    if x_idempotency_key:
        existing_record = load_idempotency_record(x_idempotency_key)
        if existing_record is not None:
            if existing_record.get("request_hash") != request_hash:
                response = ConvertResponse(
                    success=False,
                    converted_code="",
                    source_language="",
                    target_language="",
                    filename="",
                    message="This idempotency key was already used with a different convert request.",
                    execution_mode="idempotency_conflict",
                    error_code="IDEMPOTENCY_KEY_REUSED",
                    rule_match_type="",
                    rule="",
                    capability_hint="Retry with a new idempotency key when request contents change.",
                    service_version=SERVICE_VERSION,
                    warnings=[],
                    trace_id=trace_id,
                    **idempotency_response_fields(x_idempotency_key, False),
                )
                log_api_event(
                    "/v1/convert",
                    trace_id,
                    response,
                    request=request_summary,
                    metadata=idempotency_log_metadata(x_idempotency_key, request_hash, False),
                )
                return response

            replay_payload = ConvertResponse(**existing_record["response"]).model_dump(mode="json")
            replay_payload.update(idempotency_response_fields(x_idempotency_key, True))
            replay_warnings = list(replay_payload.get("warnings", []))
            replay_note = "Response replayed from idempotency store."
            if replay_note not in replay_warnings:
                replay_warnings.append(replay_note)
            replay_payload["warnings"] = replay_warnings
            replay_response = ConvertResponse(**replay_payload)
            log_api_event(
                "/v1/convert",
                replay_response.trace_id,
                replay_response,
                request=request_summary,
                metadata=idempotency_log_metadata(x_idempotency_key, request_hash, True),
            )
            return replay_response

    program = extract_rule_program(data.code, source_language)

    if program:
        converted = render_code(program, target_language)

        if converted is not None:
            rule_match_type = detect_rule_match_type(data.code, source_language, program)
            response = ConvertResponse(
                success=True,
                converted_code=converted,
                message=f"Rule-based conversion used for {source_language} -> {target_language}",
                source_language=source_language,
                target_language=target_language,
                filename=data.filename,
                execution_mode="rule_based",
                rule_match_type=rule_match_type,
                rule=RULE_SUPPORT_SUMMARY,
                capability_hint="",
                service_version=SERVICE_VERSION,
                warnings=[],
                trace_id=trace_id,
                **idempotency_response_fields(x_idempotency_key, False),
            )
            maybe_store_idempotent_response(x_idempotency_key, request_hash, response)
            log_api_event(
                "/v1/convert",
                trace_id,
                response,
                request=request_summary,
                metadata={**idempotency_log_metadata(x_idempotency_key, request_hash, False), "rate_limit": rate_result},
            )
            return response

    if not data.allow_ai_fallback:
        response = ConvertResponse(
            success=False,
            converted_code="",
            source_language="",
            target_language="",
            filename="",
            message=(
                "No lightweight rule matched this code, and AI fallback is turned off. "
                "Try a simpler print/log example or enable AI fallback."
            ),
            execution_mode="rule_only_failed",
            error_code="RULE_NOT_MATCHED",
            rule_match_type="",
            rule=(
                f"Rule-only mode: no rule matched for {source_language} -> {target_language}. "
                + RULE_SUPPORT_SUMMARY
            ),
            capability_hint=build_capability_hint(),
            service_version=SERVICE_VERSION,
            warnings=[],
            trace_id=trace_id,
            **idempotency_response_fields(x_idempotency_key, False),
        )
        maybe_store_idempotent_response(x_idempotency_key, request_hash, response)
        log_api_event(
            "/v1/convert",
            trace_id,
            response,
            request=request_summary,
            metadata={**idempotency_log_metadata(x_idempotency_key, request_hash, False), "rate_limit": rate_result},
        )
        return response

    converted, ai_message = ai_convert_fallback(
        data.code,
        source_language,
        target_language,
        api_key=x_api_key,
        base_url=x_base_url,
        model=x_model,
        provider_name=x_provider_name,
    )

    if converted is None:
        response = ConvertResponse(
            success=False,
            converted_code="",
            source_language="",
            target_language="",
            filename="",
            message=ai_message,
            execution_mode="ai_fallback_failed",
            error_code="AI_FALLBACK_FAILED",
            rule_match_type="",
            rule=(
                f"No lightweight rule matched for {source_language} -> {target_language}. "
                + RULE_SUPPORT_SUMMARY
            ),
            capability_hint=build_capability_hint(),
            service_version=SERVICE_VERSION,
            warnings=[],
            trace_id=trace_id,
            **idempotency_response_fields(x_idempotency_key, False),
        )
        maybe_store_idempotent_response(x_idempotency_key, request_hash, response)
        log_api_event(
            "/v1/convert",
            trace_id,
            response,
            request=request_summary,
            metadata={**idempotency_log_metadata(x_idempotency_key, request_hash, False), "rate_limit": rate_result},
        )
        return response

    response = ConvertResponse(
        success=True,
        converted_code=converted,
        message=ai_message,
        source_language=source_language,
        target_language=target_language,
        filename=data.filename,
        execution_mode="ai_fallback",
        rule_match_type="",
        rule=ai_message,
        capability_hint="",
        service_version=SERVICE_VERSION,
        warnings=["AI fallback was used instead of a lightweight deterministic rule."],
        trace_id=trace_id,
        **idempotency_response_fields(x_idempotency_key, False),
    )
    maybe_store_idempotent_response(x_idempotency_key, request_hash, response)
    log_api_event(
        "/v1/convert",
        trace_id,
        response,
        request=request_summary,
        metadata={**idempotency_log_metadata(x_idempotency_key, request_hash, False), "rate_limit": rate_result},
    )
    return response
