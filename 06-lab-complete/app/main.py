"""
Production AI Agent — Day 12 Final Lab.

Composes the separate concerns:
  - config.py        : 12-factor settings
  - auth.py          : API key verification
  - rate_limiter.py  : per-user sliding window (Redis or in-memory)
  - cost_guard.py    : per-user monthly budget (Redis or in-memory)
"""
import time
import signal
import logging
import json
import threading
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.auth import verify_api_key
from app.rate_limiter import check_rate_limit
from app.cost_guard import check_budget, record_usage, get_usage, estimate_cost

from utils.mock_llm import ask as llm_ask

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_is_shutting_down = False
_request_count = 0
_error_count = 0
_inflight = 0
_inflight_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready, _is_shutting_down
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "rate_limit": settings.rate_limit_per_minute,
        "monthly_budget_usd": settings.monthly_budget_usd,
    }))
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))
    yield
    _is_shutting_down = True
    _is_ready = False
    deadline = time.time() + 25
    while _inflight > 0 and time.time() < deadline:
        time.sleep(0.1)
    logger.info(json.dumps({"event": "shutdown", "remaining_inflight": _inflight}))


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count, _inflight
    start = time.time()
    _request_count += 1
    with _inflight_lock:
        _inflight += 1
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        duration_ms = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration_ms,
        }))
        return response
    except Exception:
        _error_count += 1
        raise
    finally:
        with _inflight_lock:
            _inflight -= 1


class AskRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64, description="Caller identifier")
    question: str = Field(..., min_length=1, max_length=2000)


class AskResponse(BaseModel):
    user_id: str
    question: str
    answer: str
    model: str
    timestamp: str


@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask  (X-API-Key required, body: {user_id, question})",
            "health": "GET /health",
            "ready": "GET /ready",
            "metrics": "GET /metrics (X-API-Key required)",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """Send a question to the AI agent. Requires X-API-Key header."""
    check_rate_limit(body.user_id)
    check_budget(body.user_id)

    logger.info(json.dumps({
        "event": "agent_call",
        "user_id": body.user_id,
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    answer = llm_ask(body.question)

    input_tokens = len(body.question.split()) * 2
    output_tokens = len(answer.split()) * 2
    new_total = record_usage(body.user_id, input_tokens, output_tokens)

    logger.info(json.dumps({
        "event": "usage",
        "user_id": body.user_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "monthly_spent_usd": round(new_total, 4),
    }))

    return AskResponse(
        user_id=body.user_id,
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Returns 503 during startup or shutdown drain."""
    if _is_shutting_down or not _is_ready:
        raise HTTPException(503, "Not ready")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(
    user_id: str,
    _key: str = Depends(verify_api_key),
):
    """Per-user usage + process metrics."""
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "inflight": _inflight,
        "usage": get_usage(user_id),
    }


def _handle_signal(signum, _frame):
    global _is_shutting_down
    _is_shutting_down = True
    logger.info(json.dumps({"event": "signal", "signum": signum, "action": "draining"}))


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
