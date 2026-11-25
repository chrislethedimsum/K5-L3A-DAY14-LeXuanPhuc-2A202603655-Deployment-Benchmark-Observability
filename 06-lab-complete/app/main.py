"""
Production AI Agent — Part 6 Final Project.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import sys
import time

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger = logging.getLogger("agent")
logger.setLevel(logging.INFO)
logger.handlers = [handler]
logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "startup",
        extra={
            "extra_fields": {
                "event": "startup",
                "environment": settings.environment,
                "port": settings.port,
            }
        },
    )
    yield
    logger.info("shutdown", extra={"extra_fields": {"event": "shutdown"}})
    try:
        r.close()
    except Exception:
        pass


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


@app.get("/health")
def health():
    """Liveness probe — luôn trả 200 kể cả khi Redis chưa kết nối được."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready")
def ready():
    """Readiness probe — trả 503 khi Redis không kết nối được."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis not available")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    started = time.perf_counter()
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)
    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    cost = record_cost(input_tokens, output_tokens)

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "ask_completed",
        extra={
            "extra_fields": {
                "event": "request",
                "path": "/ask",
                "status": 200,
                "ms": elapsed_ms,
                "cost_usd": cost,
            }
        },
    )
    return {
        "question": body.question,
        "answer": answer,
        "cost_usd": cost,
    }
