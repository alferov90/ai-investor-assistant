import json
import logging
from typing import Any

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    global _redis
    if _redis is None:
        try:
            client = redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            _redis = client
        except redis.RedisError as exc:
            logger.warning("Redis unavailable: %s", exc)
            _redis = None
    return _redis


def cache_get(key: str) -> Any | None:
    client = get_redis()
    if not client:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw else None
    except (redis.RedisError, json.JSONDecodeError):
        return None


def cache_set(key: str, value: Any, ttl: int) -> None:
    client = get_redis()
    if not client:
        return
    try:
        client.setex(key, ttl, json.dumps(value))
    except redis.RedisError:
        pass
