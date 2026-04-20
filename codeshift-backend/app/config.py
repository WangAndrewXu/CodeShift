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
