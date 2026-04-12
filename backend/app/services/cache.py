"""Runtime cache layer.

Supports two backends behind the same interface:

1. **RedisCache** — when ``MARKET_AI_REDIS_URL`` is configured and the
   ``redis`` package is installed.  Shared across processes, coordination-
   friendly.
2. **InMemoryCache** — lightweight local-process fallback.  Used when Redis
   is unavailable, not configured, or the connection fails.

The module auto-selects the best available backend at import time and
exposes it through ``get_cache()`` / ``get_cache_status()``.
"""

import copy
import json
import logging
import time
from threading import RLock

from backend.app.core.logging_utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# In-memory cache (always available)
# ---------------------------------------------------------------------------

class InMemoryCache:
    """Thread-safe in-process cache with TTL support."""

    def __init__(self):
        self._data = {}
        self._lock = RLock()

    @staticmethod
    def _clone(value):
        try:
            return copy.deepcopy(value)
        except Exception:
            return value

    def get(self, key):
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if expires_at is not None and expires_at < time.time():
                self._data.pop(key, None)
                return None
            return self._clone(value)

    def set(self, key, value, ttl_seconds=None):
        expires_at = None if ttl_seconds is None else time.time() + ttl_seconds
        with self._lock:
            self._data[key] = (expires_at, self._clone(value))
        return self._clone(value)

    def delete(self, key):
        with self._lock:
            self._data.pop(key, None)

    def delete_prefix(self, prefix):
        prefix_text = str(prefix or "")
        if not prefix_text:
            return
        with self._lock:
            keys = [key for key in self._data if str(key).startswith(prefix_text)]
            for key in keys:
                self._data.pop(key, None)

    def stats(self):
        now = time.time()
        with self._lock:
            active_entries = 0
            expired_entries = 0
            for expires_at, _ in self._data.values():
                if expires_at is not None and expires_at < now:
                    expired_entries += 1
                    continue
                active_entries += 1
        return {
            "provider": "in_memory",
            "backend": "local_process_memory",
            "ready": True,
            "shared_across_processes": False,
            "supports_remote_coordination": False,
            "redis_ready": False,
            "entries": active_entries,
            "expired_entries": expired_entries,
        }

    def get_or_set(self, key, factory, ttl_seconds=None):
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        return self.set(key, value, ttl_seconds=ttl_seconds)


# ---------------------------------------------------------------------------
# Redis cache
# ---------------------------------------------------------------------------

class RedisCache:
    """Redis-backed cache with the same interface as InMemoryCache.

    Serializes values as JSON.  Falls back gracefully on connection errors:
    individual operations return None / no-op rather than raising.
    """

    def __init__(self, redis_url: str, connect_timeout: int = 5, socket_timeout: int = 5):
        import redis as redis_lib  # type: ignore[import-untyped]
        self._client = redis_lib.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=connect_timeout,
            socket_timeout=socket_timeout,
        )
        self._ready = False
        self._last_error: str | None = None
        try:
            self._client.ping()
            self._ready = True
            logger.info("cache.redis_connected", extra={"url": _mask_url(redis_url)})
        except Exception as exc:
            self._last_error = str(exc)[:200]
            logger.warning("cache.redis_connect_failed", extra={"error": self._last_error})

    def _serialize(self, value):
        try:
            return json.dumps(value, default=str)
        except Exception:
            return json.dumps(str(value))

    def _deserialize(self, raw):
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return raw

    def get(self, key):
        try:
            raw = self._client.get(f"mc:{key}")
            return self._deserialize(raw)
        except Exception:
            return None

    def set(self, key, value, ttl_seconds=None):
        try:
            serialized = self._serialize(value)
            if ttl_seconds:
                self._client.setex(f"mc:{key}", int(ttl_seconds), serialized)
            else:
                self._client.set(f"mc:{key}", serialized)
        except Exception:
            pass
        return value

    def delete(self, key):
        try:
            self._client.delete(f"mc:{key}")
        except Exception:
            pass

    def delete_prefix(self, prefix):
        prefix_text = str(prefix or "")
        if not prefix_text:
            return
        try:
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor, match=f"mc:{prefix_text}*", count=100)
                if keys:
                    self._client.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            pass

    def stats(self):
        info: dict = {}
        try:
            info = self._client.info("keyspace")
            self._ready = True
        except Exception as exc:
            self._ready = False
            self._last_error = str(exc)[:200]

        db_info = info.get("db0", {})
        entries = db_info.get("keys", 0) if isinstance(db_info, dict) else 0

        return {
            "provider": "redis",
            "backend": "redis",
            "ready": self._ready,
            "shared_across_processes": True,
            "supports_remote_coordination": True,
            "redis_ready": self._ready,
            "redis_last_error": self._last_error,
            "entries": entries,
            "expired_entries": 0,
        }

    def get_or_set(self, key, factory, ttl_seconds=None):
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value, ttl_seconds=ttl_seconds)
        return value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask_url(url: str) -> str:
    """Mask password in URL for logging."""
    if "@" in url:
        parts = url.split("@", 1)
        prefix = parts[0]
        if ":" in prefix:
            scheme_user = prefix.rsplit(":", 1)[0]
            return f"{scheme_user}:***@{parts[1]}"
    return url


# ---------------------------------------------------------------------------
# Singleton + auto-select
# ---------------------------------------------------------------------------

_CACHE: InMemoryCache | RedisCache | None = None
_FALLBACK_CACHE = InMemoryCache()


def _build_cache() -> InMemoryCache | RedisCache:
    """Select the best available cache backend."""
    from backend.app.config import REDIS_URL, REDIS_ENABLED, REDIS_CONNECT_TIMEOUT, REDIS_SOCKET_TIMEOUT

    if REDIS_ENABLED and REDIS_URL:
        try:
            import redis as _redis_check  # noqa: F401
            cache = RedisCache(
                REDIS_URL,
                connect_timeout=REDIS_CONNECT_TIMEOUT,
                socket_timeout=REDIS_SOCKET_TIMEOUT,
            )
            if cache._ready:
                return cache
            # Redis configured but not reachable — fall back
            logger.warning("cache.redis_not_reachable_falling_back")
        except ImportError:
            logger.warning("cache.redis_package_not_installed_falling_back")
        except Exception as exc:
            logger.warning("cache.redis_init_failed", extra={"error": str(exc)[:200]})

    return InMemoryCache()


def get_cache() -> InMemoryCache | RedisCache:
    global _CACHE
    if _CACHE is None:
        _CACHE = _build_cache()
    return _CACHE


def reset_cache() -> InMemoryCache | RedisCache:
    """Force re-initialization of the cache backend.

    Useful after runtime configuration changes (e.g., Redis URL updated via settings).
    """
    global _CACHE
    _CACHE = _build_cache()
    return _CACHE


def get_cache_status() -> dict:
    """Return cache backend status with configuration context."""
    from backend.app.config import REDIS_URL, REDIS_ENABLED

    stats = get_cache().stats()
    stats["configured_url"] = bool(REDIS_URL)
    stats["configured_enabled"] = REDIS_ENABLED
    stats["runtime_mode"] = "redis" if stats.get("provider") == "redis" else "in_memory"
    stats["fallback_reason"] = None
    if REDIS_ENABLED and REDIS_URL and stats.get("provider") != "redis":
        stats["fallback_reason"] = "Redis configured but not reachable"
    elif not REDIS_ENABLED:
        stats["fallback_reason"] = "Redis not enabled (MARKET_AI_REDIS_ENABLED=0)"
    elif not REDIS_URL:
        stats["fallback_reason"] = "Redis URL not configured (MARKET_AI_REDIS_URL empty)"
    return stats
