import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.agents.checkpoint import init_agent_checkpointer, close_agent_checkpointer
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import AppException, app_exception_handler, generic_exception_handler
from app.core.my_logging import setup_logging
from app.core.middleware import RequestLoggingMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_agent_checkpointer()
    logger.info("Application starting")
    yield
    logger.info("Application shutting down")
    await close_agent_checkpointer()


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan
)

app.add_middleware(RequestLoggingMiddleware)
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(AppException, generic_exception_handler)
app.include_router(api_router, prefix=settings.api_prefix)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "debug": settings.debug
    }


@app.get("/health/db")
async def database_health_check():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": result.scalar_one()
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
