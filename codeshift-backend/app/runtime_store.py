import hashlib
import json
import os
from datetime import datetime, timezone

from .config import get_storage_dir


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def now_utc_iso():
    return datetime.now(timezone.utc).isoformat()


def get_logs_path():
    path = os.path.join(get_storage_dir(), "logs")
    _ensure_dir(path)
    return os.path.join(path, "requests.jsonl")


def get_idempotency_dir():
    path = os.path.join(get_storage_dir(), "idempotency")
    _ensure_dir(path)
    return path


def sha256_text(value: str):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


def append_request_log(entry: dict):
    with open(get_logs_path(), "a", encoding="utf-8") as handle:
        handle.write(stable_json(entry) + "\n")


def build_request_hash(payload: dict):
    return sha256_text(stable_json(payload))


def build_idempotency_path(idempotency_key: str):
    return os.path.join(get_idempotency_dir(), f"{sha256_text(idempotency_key)}.json")


def load_idempotency_record(idempotency_key: str):
    path = build_idempotency_path(idempotency_key)
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_idempotency_record(idempotency_key: str, record: dict):
    path = build_idempotency_path(idempotency_key)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, sort_keys=True, indent=2, default=_json_default)
