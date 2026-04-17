"""
Per-user sliding-window rate limiter.

Primary store: Redis sorted set (scales across instances).
Fallback: in-memory deque per process (for local dev without Redis).
"""
import time
import logging
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

try:
    import redis  # type: ignore

    _redis = redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url else None
    if _redis is not None:
        _redis.ping()
        logger.info("rate_limiter: Redis backend active")
except Exception as e:
    logger.warning(f"rate_limiter: Redis unavailable ({e}) — falling back to in-memory")
    _redis = None

_memory_windows: dict[str, deque] = defaultdict(deque)


def check_rate_limit(user_id: str) -> None:
    """Raise 429 if user_id exceeded RATE_LIMIT_PER_MINUTE."""
    limit = settings.rate_limit_per_minute
    window_seconds = 60
    now = time.time()
    cutoff = now - window_seconds

    if _redis is not None:
        key = f"ratelimit:{user_id}"
        pipe = _redis.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        pipe.zadd(key, {f"{now}:{user_id}": now})
        pipe.expire(key, window_seconds + 5)
        _, count, _, _ = pipe.execute()
        current = int(count)
    else:
        window = _memory_windows[user_id]
        while window and window[0] < cutoff:
            window.popleft()
        current = len(window)
        window.append(now)

    if current >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {limit} req/min per user",
            headers={
                "Retry-After": "60",
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )
