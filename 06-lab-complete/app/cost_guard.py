"""
Per-user monthly budget guard.

Tracks USD spend per user per calendar month. Raises 402 when the user's
monthly spend would exceed MONTHLY_BUDGET_USD.

Primary store: Redis string keyed by user_id + YYYY-MM.
Fallback: in-memory dict (single-process only).
"""
import time
import logging
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

PRICE_PER_1K_INPUT = 0.00015
PRICE_PER_1K_OUTPUT = 0.0006

try:
    import redis  # type: ignore

    _redis = redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url else None
    if _redis is not None:
        _redis.ping()
        logger.info("cost_guard: Redis backend active")
except Exception as e:
    logger.warning(f"cost_guard: Redis unavailable ({e}) — falling back to in-memory")
    _redis = None

_memory_spend: dict[str, float] = defaultdict(float)


def _month_key(user_id: str) -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"budget:{user_id}:{month}"


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1000) * PRICE_PER_1K_INPUT + (output_tokens / 1000) * PRICE_PER_1K_OUTPUT


def _get_spend(user_id: str) -> float:
    key = _month_key(user_id)
    if _redis is not None:
        val = _redis.get(key)
        return float(val) if val else 0.0
    return _memory_spend[key]


def check_budget(user_id: str) -> None:
    """Raise 402 Payment Required if the user has exhausted their monthly budget."""
    spent = _get_spend(user_id)
    if spent >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Monthly budget exceeded",
                "used_usd": round(spent, 4),
                "budget_usd": settings.monthly_budget_usd,
                "resets_at": "start of next month (UTC)",
            },
        )


def record_usage(user_id: str, input_tokens: int, output_tokens: int) -> float:
    """Add cost to the user's monthly counter. Returns new total."""
    cost = estimate_cost(input_tokens, output_tokens)
    key = _month_key(user_id)

    if _redis is not None:
        new_total = _redis.incrbyfloat(key, cost)
        _redis.expire(key, 32 * 24 * 3600)
        return float(new_total)

    _memory_spend[key] += cost
    return _memory_spend[key]


def get_usage(user_id: str) -> dict:
    spent = _get_spend(user_id)
    return {
        "user_id": user_id,
        "month": datetime.now(timezone.utc).strftime("%Y-%m"),
        "spent_usd": round(spent, 4),
        "budget_usd": settings.monthly_budget_usd,
        "remaining_usd": round(max(0.0, settings.monthly_budget_usd - spent), 4),
        "used_pct": round(spent / settings.monthly_budget_usd * 100, 1) if settings.monthly_budget_usd else 0,
    }
