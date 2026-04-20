from uuid import uuid4

from fastapi import FastAPI, File, Header, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import get_allowed_origins
from .providers import ai_convert_fallback, test_ai_connection
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
from .schemas import ConvertRequest

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def new_trace_id():
    return f"trace_{uuid4().hex[:12]}"


def build_capability_hint():
    return f"Supported lightweight patterns: {', '.join(SUPPORTED_RULE_PATTERNS)}."


@app.get("/")
async def root():
    return {
        "message": "CodeShift backend is running",
        "allowed_origins": get_allowed_origins(),
    }


@app.get("/v1/capabilities")
async def capabilities():
    return {
        "service": "codeshift",
        "version": "v1",
        "service_version": SERVICE_VERSION,
        "supported_languages": SUPPORTED_LANGUAGES,
        "rule_patterns": SUPPORTED_RULE_PATTERNS,
        "rule_summary": RULE_SUPPORT_SUMMARY,
        "default_execution_mode": "rule_first",
        "supports_ai_fallback": True,
        "error_codes": [
            "RULE_NOT_MATCHED",
            "AI_FALLBACK_FAILED",
            "INVALID_UTF8_FILE",
            "FILE_LOAD_FAILED",
            "PROVIDER_TEST_FAILED",
        ],
        "capability_hint": build_capability_hint(),
    }


@app.post("/load-file")
async def load_file(file: UploadFile = File(...)):
    trace_id = new_trace_id()
    try:
        raw = await file.read()
        content = raw.decode("utf-8")
        language = detect_language_from_filename(file.filename)

        return {
            "success": True,
            "filename": file.filename,
            "content": content,
            "language": language,
            "service_version": SERVICE_VERSION,
            "warnings": [],
            "trace_id": trace_id,
        }
    except UnicodeDecodeError:
        return {
            "success": False,
            "message": "This file is not valid UTF-8 text.",
            "error_code": "INVALID_UTF8_FILE",
            "capability_hint": "Upload UTF-8 text source files only.",
            "service_version": SERVICE_VERSION,
            "warnings": [],
            "trace_id": trace_id,
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"Failed to load file: {str(exc)}",
            "error_code": "FILE_LOAD_FAILED",
            "capability_hint": "Retry with a plain text source file and a supported extension.",
            "service_version": SERVICE_VERSION,
            "warnings": [],
            "trace_id": trace_id,
        }


@app.post("/test-provider")
async def test_provider(
    x_api_key: str | None = Header(default=None),
    x_base_url: str | None = Header(default=None),
    x_model: str | None = Header(default=None),
    x_provider_name: str | None = Header(default=None),
):
    trace_id = new_trace_id()
    success, message = test_ai_connection(
        api_key=x_api_key,
        base_url=x_base_url,
        model=x_model,
        provider_name=x_provider_name,
    )

    return {
        "success": success,
        "message": message,
        "error_code": "" if success else "PROVIDER_TEST_FAILED",
        "provider_name": x_provider_name or "",
        "model": x_model or "",
        "base_url": x_base_url or "",
        "capability_hint": "" if success else "Check API key, base URL, model, and provider availability.",
        "service_version": SERVICE_VERSION,
        "warnings": [],
        "trace_id": trace_id,
    }


@app.post("/convert")
@app.post("/v1/convert")
async def convert_code(
    data: ConvertRequest,
    x_api_key: str | None = Header(default=None),
    x_base_url: str | None = Header(default=None),
    x_model: str | None = Header(default=None),
    x_provider_name: str | None = Header(default=None),
):
    trace_id = new_trace_id()
    source_language = normalize_language(data.source_language)
    target_language = normalize_language(data.target_language)

    program = extract_rule_program(data.code, source_language)

    if program:
        converted = render_code(program, target_language)

        if converted is not None:
            rule_match_type = detect_rule_match_type(data.code, source_language, program)
            return {
                "success": True,
                "converted_code": converted,
                "message": f"Rule-based conversion used for {source_language} -> {target_language}",
                "source_language": source_language,
                "target_language": target_language,
                "filename": data.filename,
                "execution_mode": "rule_based",
                "rule_match_type": rule_match_type,
                "rule": RULE_SUPPORT_SUMMARY,
                "capability_hint": "",
                "service_version": SERVICE_VERSION,
                "warnings": [],
                "trace_id": trace_id,
            }

    if not data.allow_ai_fallback:
        return {
            "success": False,
            "converted_code": "",
            "message": (
                "No lightweight rule matched this code, and AI fallback is turned off. "
                "Try a simpler print/log example or enable AI fallback."
            ),
            "execution_mode": "rule_only_failed",
            "error_code": "RULE_NOT_MATCHED",
            "rule_match_type": "",
            "rule": (
                f"Rule-only mode: no rule matched for {source_language} -> {target_language}. "
                + RULE_SUPPORT_SUMMARY
            ),
            "capability_hint": build_capability_hint(),
            "service_version": SERVICE_VERSION,
            "warnings": [],
            "trace_id": trace_id,
        }

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
        return {
            "success": False,
            "converted_code": "",
            "message": ai_message,
            "execution_mode": "ai_fallback_failed",
            "error_code": "AI_FALLBACK_FAILED",
            "rule_match_type": "",
            "rule": (
                f"No lightweight rule matched for {source_language} -> {target_language}. "
                + RULE_SUPPORT_SUMMARY
            ),
            "capability_hint": build_capability_hint(),
            "service_version": SERVICE_VERSION,
            "warnings": [],
            "trace_id": trace_id,
        }

    return {
        "success": True,
        "converted_code": converted,
        "message": ai_message,
        "source_language": source_language,
        "target_language": target_language,
        "filename": data.filename,
        "execution_mode": "ai_fallback",
        "rule_match_type": "",
        "rule": ai_message,
        "capability_hint": "",
        "service_version": SERVICE_VERSION,
        "warnings": ["AI fallback was used instead of a lightweight deterministic rule."],
        "trace_id": trace_id,
    }
