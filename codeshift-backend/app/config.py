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
