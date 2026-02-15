from __future__ import annotations

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Liveness probe — confirms the process is alive."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request, response: Response):
    """Readiness probe — confirms Redis and PostgreSQL are reachable."""
    # Check Redis
    try:
        await request.app.state.redis.ping()
    except Exception:
        response.status_code = 503
        return {"status": "not ready", "reason": "redis unreachable"}

    # Check PostgreSQL
    try:
        async with request.app.state.db_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        response.status_code = 503
        return {"status": "not ready", "reason": "database unreachable"}

    return {"status": "ready"}
