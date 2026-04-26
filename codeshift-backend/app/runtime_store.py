import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from .config import (
    get_idempotency_ttl_days,
    get_request_log_retention_days,
    get_storage_dir,
)


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def now_utc():
    return datetime.now(timezone.utc)


def now_utc_iso():
    return now_utc().isoformat()


def parse_utc_iso(value: str):
    return datetime.fromisoformat(value)


def get_logs_path():
    path = os.path.join(get_storage_dir(), "logs")
    _ensure_dir(path)
    return os.path.join(path, "requests.jsonl")


def get_idempotency_dir():
    path = os.path.join(get_storage_dir(), "idempotency")
    _ensure_dir(path)
    return path


def get_rate_limit_dir():
    path = os.path.join(get_storage_dir(), "rate_limits")
    _ensure_dir(path)
    return path


def sha256_text(value: str):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


def append_request_log(entry: dict):
    prune_request_logs()
    with open(get_logs_path(), "a", encoding="utf-8") as handle:
        handle.write(stable_json(entry) + "\n")


def prune_request_logs():
    log_path = get_logs_path()
    if not os.path.exists(log_path):
        return

    cutoff = now_utc() - timedelta(days=get_request_log_retention_days())
    kept_lines = []
    changed = False

    with open(log_path, "r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                timestamp = parse_utc_iso(payload["timestamp"])
            except (KeyError, ValueError, json.JSONDecodeError):
                changed = True
                continue

            if timestamp >= cutoff:
                kept_lines.append(stable_json(payload) + "\n")
            else:
                changed = True

    if changed:
        with open(log_path, "w", encoding="utf-8") as handle:
            handle.writelines(kept_lines)


def build_request_hash(payload: dict):
    return sha256_text(stable_json(payload))


def build_idempotency_path(idempotency_key: str):
    return os.path.join(get_idempotency_dir(), f"{sha256_text(idempotency_key)}.json")


def build_rate_limit_path(bucket: str, key: str):
    filename = f"{bucket}-{sha256_text(key)}.json"
    return os.path.join(get_rate_limit_dir(), filename)


def prune_idempotency_records():
    idempotency_dir = get_idempotency_dir()
    now = now_utc()

    for name in os.listdir(idempotency_dir):
        if not name.endswith(".json"):
            continue

        path = os.path.join(idempotency_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            expires_at = parse_utc_iso(payload["expires_at"])
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            os.remove(path)
            continue

        if expires_at < now:
            os.remove(path)


def load_idempotency_record(idempotency_key: str):
    prune_idempotency_records()
    path = build_idempotency_path(idempotency_key)
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if parse_utc_iso(payload["expires_at"]) < now_utc():
        os.remove(path)
        return None

    return payload


def save_idempotency_record(idempotency_key: str, record: dict):
    prune_idempotency_records()
    path = build_idempotency_path(idempotency_key)
    payload = {
        **record,
        "stored_at": now_utc_iso(),
        "expires_at": (now_utc() + timedelta(days=get_idempotency_ttl_days())).isoformat(),
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, indent=2, default=_json_default)


def check_rate_limit(bucket: str, key: str, *, max_requests: int, window_seconds: int):
    path = build_rate_limit_path(bucket, key)
    now = now_utc()
    cutoff = now - timedelta(seconds=window_seconds)
    timestamps: list[str] = []

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            raw_timestamps = payload.get("timestamps", [])
            timestamps = [
                timestamp
                for timestamp in raw_timestamps
                if parse_utc_iso(timestamp) >= cutoff
            ]
        except (OSError, ValueError, json.JSONDecodeError, KeyError):
            timestamps = []

    allowed = len(timestamps) < max_requests
    if allowed:
        timestamps.append(now.isoformat())

    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"timestamps": timestamps}, handle, sort_keys=True, indent=2)

    return {
        "allowed": allowed,
        "limit": max_requests,
        "remaining": max(0, max_requests - len(timestamps)),
        "window_seconds": window_seconds,
        "retry_after_seconds": 0 if allowed else window_seconds,
    }
