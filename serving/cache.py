"""
Redis response cache for the /search endpoint.

Key: SHA-256 of (symptoms + status_filter + max_results).
TTL: 24 hours. Stores the full JSON response body.

Usage:
    cache = ResponseCache()
    cached = cache.get(symptoms, status_filter, max_results)
    if cached is None:
        result = expensive_search(...)
        cache.set(symptoms, status_filter, max_results, result)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import redis

logger = logging.getLogger(__name__)

TTL_SECONDS = 86_400  # 24 hours


class ResponseCache:
    """Redis-backed cache with query fingerprint keys."""

    def __init__(self) -> None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self._client: redis.Redis = redis.from_url(redis_url, decode_responses=True)

    def _key(self, symptoms: str, status_filter: str, max_results: int) -> str:
        fingerprint = f"{symptoms.lower().strip()}|{status_filter}|{max_results}"
        return "ctsearch:" + hashlib.sha256(fingerprint.encode()).hexdigest()

    def get(self, symptoms: str, status_filter: str, max_results: int) -> dict[str, Any] | None:
        try:
            raw = self._client.get(self._key(symptoms, status_filter, max_results))
            if raw:
                return json.loads(raw)  # type: ignore[return-value]
        except Exception as exc:
            logger.warning("Cache get failed: %s", exc)
        return None

    def set(
        self,
        symptoms: str,
        status_filter: str,
        max_results: int,
        data: dict[str, Any],
    ) -> None:
        try:
            key = self._key(symptoms, status_filter, max_results)
            self._client.set(key, json.dumps(data), ex=TTL_SECONDS)
        except Exception as exc:
            logger.warning("Cache set failed: %s", exc)

    def delete(self, symptoms: str, status_filter: str, max_results: int) -> None:
        try:
            self._client.delete(self._key(symptoms, status_filter, max_results))
        except Exception as exc:
            logger.warning("Cache delete failed: %s", exc)

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False
