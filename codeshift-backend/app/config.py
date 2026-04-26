import os
import tempfile


def get_allowed_origins():
    raw = os.getenv("CODESHIFT_ALLOWED_ORIGINS", "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def get_storage_dir():
    configured = os.getenv("CODESHIFT_STORAGE_DIR", "").strip()
    if configured:
        return configured

    return os.path.join(tempfile.gettempdir(), "codeshift-runtime")


def _get_positive_int(name: str, default: int):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError:
        return default

    return value if value > 0 else default


def get_request_log_retention_days():
    return _get_positive_int("CODESHIFT_REQUEST_LOG_RETENTION_DAYS", 7)


def get_idempotency_ttl_days():
    return _get_positive_int("CODESHIFT_IDEMPOTENCY_TTL_DAYS", 3)


def get_convert_requests_per_minute():
    return _get_positive_int("CODESHIFT_CONVERT_REQUESTS_PER_MINUTE", 20)


def get_provider_test_requests_per_minute():
    return _get_positive_int("CODESHIFT_PROVIDER_TEST_REQUESTS_PER_MINUTE", 10)


def get_rate_limit_window_seconds():
    return _get_positive_int("CODESHIFT_RATE_LIMIT_WINDOW_SECONDS", 60)


def get_allowed_provider_names():
    raw = os.getenv("CODESHIFT_ALLOWED_PROVIDER_NAMES", "").strip()
    if raw:
        return [value.strip().lower() for value in raw.split(",") if value.strip()]

    return ["openai", "openai-compatible", "openrouter"]


def get_allowed_base_url_prefixes():
    raw = os.getenv("CODESHIFT_ALLOWED_BASE_URL_PREFIXES", "").strip()
    values: list[str] = []
    if raw:
        values.extend([value.strip() for value in raw.split(",") if value.strip()])
    else:
        values.extend([
            "https://api.openai.com/v1",
            "https://openrouter.ai/api/v1",
        ])

    configured_base = os.getenv("OPENAI_BASE_URL", "").strip()
    if configured_base and configured_base not in values:
        values.append(configured_base)

    return values


def get_runtime_store_backend():
    return os.getenv("CODESHIFT_RUNTIME_STORE_BACKEND", "filesystem").strip().lower() or "filesystem"


def get_runtime_store_redis_url():
    return os.getenv("CODESHIFT_RUNTIME_STORE_REDIS_URL", "").strip()


def get_runtime_store_key_prefix():
    return os.getenv("CODESHIFT_RUNTIME_STORE_KEY_PREFIX", "codeshift").strip() or "codeshift"
