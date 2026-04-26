import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Protocol
from uuid import uuid4

from .config import (
    get_idempotency_ttl_days,
    get_rate_limit_window_seconds,
    get_request_log_retention_days,
    get_runtime_store_backend,
    get_runtime_store_key_prefix,
    get_runtime_store_redis_url,
    get_storage_dir,
)

try:
    import redis
except ImportError:  # pragma: no cover - optional dependency at runtime
    redis = None


class RuntimeStore(Protocol):
    def append_request_log(self, entry: dict) -> None: ...

    def build_request_hash(self, payload: dict) -> str: ...

    def load_idempotency_record(self, idempotency_key: str) -> dict | None: ...

    def reserve_idempotency_key(self, idempotency_key: str, request_hash: str) -> bool: ...

    def complete_idempotency_record(self, idempotency_key: str, request_hash: str, response: dict) -> None: ...

    def save_idempotency_record(self, idempotency_key: str, record: dict) -> None: ...

    def check_rate_limit(self, bucket: str, key: str, *, max_requests: int, window_seconds: int) -> dict: ...

    def backend_name(self) -> str: ...

    def is_multi_instance_safe(self) -> bool: ...


_backend_cache: RuntimeStore | None = None


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


@dataclass
class RateLimitWindow:
    allowed: bool
    limit: int
    remaining: int
    window_seconds: int
    retry_after_seconds: int

    def as_dict(self):
        return {
            "allowed": self.allowed,
            "limit": self.limit,
            "remaining": self.remaining,
            "window_seconds": self.window_seconds,
            "retry_after_seconds": self.retry_after_seconds,
        }


def now_utc():
    return datetime.now(timezone.utc)


def now_utc_iso():
    return now_utc().isoformat()


def parse_utc_iso(value: str):
    return datetime.fromisoformat(value)


def sha256_text(value: str):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


class FileRuntimeStore:
    def _get_logs_path(self):
        path = os.path.join(get_storage_dir(), "logs")
        _ensure_dir(path)
        return os.path.join(path, "requests.jsonl")

    def _get_idempotency_dir(self):
        path = os.path.join(get_storage_dir(), "idempotency")
        _ensure_dir(path)
        return path

    def _get_rate_limit_dir(self):
        path = os.path.join(get_storage_dir(), "rate_limits")
        _ensure_dir(path)
        return path

    def append_request_log(self, entry: dict) -> None:
        self.prune_request_logs()
        with open(self._get_logs_path(), "a", encoding="utf-8") as handle:
            handle.write(stable_json(entry) + "\n")

    def prune_request_logs(self):
        log_path = self._get_logs_path()
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

    def build_request_hash(self, payload: dict) -> str:
        return sha256_text(stable_json(payload))

    def build_idempotency_path(self, idempotency_key: str):
        return os.path.join(self._get_idempotency_dir(), f"{sha256_text(idempotency_key)}.json")

    def build_rate_limit_path(self, bucket: str, key: str):
        filename = f"{bucket}-{sha256_text(key)}.json"
        return os.path.join(self._get_rate_limit_dir(), filename)

    def prune_idempotency_records(self):
        idempotency_dir = self._get_idempotency_dir()
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

    def load_idempotency_record(self, idempotency_key: str):
        self.prune_idempotency_records()
        path = self.build_idempotency_path(idempotency_key)
        if not os.path.exists(path):
            return None

        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if parse_utc_iso(payload["expires_at"]) < now_utc():
            os.remove(path)
            return None

        return payload

    def reserve_idempotency_key(self, idempotency_key: str, request_hash: str) -> bool:
        self.prune_idempotency_records()
        path = self.build_idempotency_path(idempotency_key)
        payload = {
            "status": "pending",
            "request_hash": request_hash,
            "stored_at": now_utc_iso(),
            "expires_at": (now_utc() + timedelta(days=get_idempotency_ttl_days())).isoformat(),
        }
        try:
            with open(path, "x", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, indent=2, default=_json_default)
            return True
        except FileExistsError:
            return False

    def complete_idempotency_record(self, idempotency_key: str, request_hash: str, response: dict) -> None:
        existing = self.load_idempotency_record(idempotency_key)
        if existing is None:
            self.save_idempotency_record(idempotency_key, {"request_hash": request_hash, "response": response, "status": "completed"})
            return

        payload = {
            **existing,
            "status": "completed",
            "request_hash": request_hash,
            "response": response,
        }
        path = self.build_idempotency_path(idempotency_key)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2, default=_json_default)

    def save_idempotency_record(self, idempotency_key: str, record: dict):
        self.prune_idempotency_records()
        path = self.build_idempotency_path(idempotency_key)
        payload = {
            **record,
            "stored_at": now_utc_iso(),
            "expires_at": (now_utc() + timedelta(days=get_idempotency_ttl_days())).isoformat(),
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2, default=_json_default)

    def check_rate_limit(self, bucket: str, key: str, *, max_requests: int, window_seconds: int):
        path = self.build_rate_limit_path(bucket, key)
        now = now_utc()
        cutoff = now - timedelta(seconds=window_seconds)
        timestamps: list[str] = []

        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                raw_timestamps = payload.get("timestamps", [])
                timestamps = [timestamp for timestamp in raw_timestamps if parse_utc_iso(timestamp) >= cutoff]
            except (OSError, ValueError, json.JSONDecodeError, KeyError):
                timestamps = []

        allowed = len(timestamps) < max_requests
        if allowed:
            timestamps.append(now.isoformat())

        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"timestamps": timestamps}, handle, sort_keys=True, indent=2)

        result = RateLimitWindow(
            allowed=allowed,
            limit=max_requests,
            remaining=max(0, max_requests - len(timestamps)),
            window_seconds=window_seconds,
            retry_after_seconds=0 if allowed else window_seconds,
        )
        return result.as_dict()

    def backend_name(self):
        return "filesystem"

    def is_multi_instance_safe(self):
        return False


class RedisRuntimeStore:
    def __init__(self, client, prefix: str):
        self.client = client
        self.prefix = prefix

    def _key(self, *parts: str):
        return ":".join([self.prefix, *parts])

    def append_request_log(self, entry: dict) -> None:
        now = now_utc()
        score = now.timestamp()
        member = f"{entry.get('trace_id', uuid4().hex)}|{stable_json(entry)}"
        key = self._key("logs", "requests")
        cutoff = (now - timedelta(days=get_request_log_retention_days())).timestamp()
        pipe = self.client.pipeline()
        pipe.zadd(key, {member: score})
        pipe.zremrangebyscore(key, "-inf", cutoff)
        pipe.expire(key, max(1, get_request_log_retention_days() * 24 * 60 * 60))
        pipe.execute()

    def build_request_hash(self, payload: dict) -> str:
        return sha256_text(stable_json(payload))

    def _idempotency_key(self, idempotency_key: str):
        return self._key("idempotency", sha256_text(idempotency_key))

    def load_idempotency_record(self, idempotency_key: str):
        raw = self.client.get(self._idempotency_key(idempotency_key))
        if not raw:
            return None
        return json.loads(raw)

    def reserve_idempotency_key(self, idempotency_key: str, request_hash: str) -> bool:
        ttl_seconds = max(1, get_idempotency_ttl_days() * 24 * 60 * 60)
        payload = {
            "status": "pending",
            "request_hash": request_hash,
            "stored_at": now_utc_iso(),
            "expires_at": (now_utc() + timedelta(seconds=ttl_seconds)).isoformat(),
        }
        return bool(
            self.client.set(
                self._idempotency_key(idempotency_key),
                stable_json(payload),
                ex=ttl_seconds,
                nx=True,
            )
        )

    def complete_idempotency_record(self, idempotency_key: str, request_hash: str, response: dict) -> None:
        key = self._idempotency_key(idempotency_key)
        ttl = self.client.ttl(key)
        ttl_seconds = ttl if isinstance(ttl, int) and ttl > 0 else max(1, get_idempotency_ttl_days() * 24 * 60 * 60)
        payload = {
            "status": "completed",
            "request_hash": request_hash,
            "response": response,
            "stored_at": now_utc_iso(),
            "expires_at": (now_utc() + timedelta(seconds=ttl_seconds)).isoformat(),
        }
        self.client.set(key, stable_json(payload), ex=ttl_seconds)

    def save_idempotency_record(self, idempotency_key: str, record: dict):
        ttl_seconds = max(1, get_idempotency_ttl_days() * 24 * 60 * 60)
        payload = {
            **record,
            "stored_at": now_utc_iso(),
            "expires_at": (now_utc() + timedelta(seconds=ttl_seconds)).isoformat(),
        }
        self.client.set(self._idempotency_key(idempotency_key), stable_json(payload), ex=ttl_seconds)

    def check_rate_limit(self, bucket: str, key: str, *, max_requests: int, window_seconds: int):
        now = now_utc()
        now_ts = int(now.timestamp())
        window_start = now_ts - (now_ts % window_seconds)
        redis_key = self._key("rate_limit", bucket, sha256_text(key), str(window_start))
        count = self.client.incr(redis_key)
        if count == 1:
            self.client.expire(redis_key, window_seconds)
        ttl = self.client.ttl(redis_key)
        allowed = count <= max_requests
        remaining = max(0, max_requests - min(count, max_requests))
        return RateLimitWindow(
            allowed=allowed,
            limit=max_requests,
            remaining=remaining,
            window_seconds=window_seconds,
            retry_after_seconds=0 if allowed else max(1, ttl if isinstance(ttl, int) and ttl > 0 else window_seconds),
        ).as_dict()

    def backend_name(self):
        return "redis"

    def is_multi_instance_safe(self):
        return True


class InMemoryRuntimeStore:
    def __init__(self):
        self.logs: list[dict] = []
        self.idempotency: dict[str, dict] = {}
        self.rate_limits: dict[tuple[str, str], list[datetime]] = {}

    def append_request_log(self, entry: dict) -> None:
        cutoff = now_utc() - timedelta(days=get_request_log_retention_days())
        self.logs = [item for item in self.logs if parse_utc_iso(item["timestamp"]) >= cutoff]
        self.logs.append(entry)

    def build_request_hash(self, payload: dict) -> str:
        return sha256_text(stable_json(payload))

    def load_idempotency_record(self, idempotency_key: str):
        payload = self.idempotency.get(idempotency_key)
        if not payload:
            return None
        if parse_utc_iso(payload["expires_at"]) < now_utc():
            self.idempotency.pop(idempotency_key, None)
            return None
        return payload

    def reserve_idempotency_key(self, idempotency_key: str, request_hash: str) -> bool:
        if self.load_idempotency_record(idempotency_key) is not None:
            return False
        self.idempotency[idempotency_key] = {
            "status": "pending",
            "request_hash": request_hash,
            "stored_at": now_utc_iso(),
            "expires_at": (now_utc() + timedelta(days=get_idempotency_ttl_days())).isoformat(),
        }
        return True

    def complete_idempotency_record(self, idempotency_key: str, request_hash: str, response: dict) -> None:
        self.idempotency[idempotency_key] = {
            "status": "completed",
            "request_hash": request_hash,
            "response": response,
            "stored_at": now_utc_iso(),
            "expires_at": (now_utc() + timedelta(days=get_idempotency_ttl_days())).isoformat(),
        }

    def save_idempotency_record(self, idempotency_key: str, record: dict) -> None:
        self.idempotency[idempotency_key] = {
            **record,
            "stored_at": now_utc_iso(),
            "expires_at": (now_utc() + timedelta(days=get_idempotency_ttl_days())).isoformat(),
        }

    def check_rate_limit(self, bucket: str, key: str, *, max_requests: int, window_seconds: int):
        now = now_utc()
        cutoff = now - timedelta(seconds=window_seconds)
        bucket_key = (bucket, key)
        timestamps = [item for item in self.rate_limits.get(bucket_key, []) if item >= cutoff]
        allowed = len(timestamps) < max_requests
        if allowed:
            timestamps.append(now)
        self.rate_limits[bucket_key] = timestamps
        return RateLimitWindow(
            allowed=allowed,
            limit=max_requests,
            remaining=max(0, max_requests - len(timestamps)),
            window_seconds=window_seconds,
            retry_after_seconds=0 if allowed else window_seconds,
        ).as_dict()

    def backend_name(self):
        return "memory"

    def is_multi_instance_safe(self):
        return False


def build_runtime_store() -> RuntimeStore:
    backend_name = get_runtime_store_backend()
    if backend_name == "redis":
        redis_url = get_runtime_store_redis_url()
        if not redis_url:
            raise RuntimeError("CODESHIFT_RUNTIME_STORE_REDIS_URL must be set when using redis runtime storage.")
        if redis is None:
            raise RuntimeError("redis package is required for redis runtime storage.")
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        return RedisRuntimeStore(client, get_runtime_store_key_prefix())
    if backend_name == "memory":
        return InMemoryRuntimeStore()
    return FileRuntimeStore()


def get_runtime_store() -> RuntimeStore:
    global _backend_cache
    if _backend_cache is None:
        _backend_cache = build_runtime_store()
    return _backend_cache


def reset_runtime_store_cache():
    global _backend_cache
    _backend_cache = None


def append_request_log(entry: dict):
    get_runtime_store().append_request_log(entry)


def build_request_hash(payload: dict):
    return get_runtime_store().build_request_hash(payload)


def load_idempotency_record(idempotency_key: str):
    return get_runtime_store().load_idempotency_record(idempotency_key)


def reserve_idempotency_key(idempotency_key: str, request_hash: str):
    return get_runtime_store().reserve_idempotency_key(idempotency_key, request_hash)


def complete_idempotency_record(idempotency_key: str, request_hash: str, response: dict):
    get_runtime_store().complete_idempotency_record(idempotency_key, request_hash, response)


def save_idempotency_record(idempotency_key: str, record: dict):
    get_runtime_store().save_idempotency_record(idempotency_key, record)


def check_rate_limit(bucket: str, key: str, *, max_requests: int, window_seconds: int):
    return get_runtime_store().check_rate_limit(bucket, key, max_requests=max_requests, window_seconds=window_seconds)


def get_runtime_storage_backend_name():
    return get_runtime_store().backend_name()


def runtime_storage_is_multi_instance_safe():
    return get_runtime_store().is_multi_instance_safe()


def build_idempotency_path(idempotency_key: str):
    store = get_runtime_store()
    if isinstance(store, FileRuntimeStore):
        return store.build_idempotency_path(idempotency_key)
    raise RuntimeError("build_idempotency_path is only available for filesystem runtime storage.")


def prune_request_logs():
    store = get_runtime_store()
    if isinstance(store, FileRuntimeStore):
        return store.prune_request_logs()
    return None
