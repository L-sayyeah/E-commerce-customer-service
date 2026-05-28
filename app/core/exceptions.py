import logging
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.request_context import get_trace_id

logger = logging.getLogger(__name__)

class AppException(Exception):
    def __init__(self, message: str, code: int = 400, status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    trace_id = get_trace_id()

    logger.warning(f"App exception | trace_id={trace_id} | code={exc.code} | message={exc.message}")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "data": None,
            "trace_id": trace_id
        }
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    trace_id = get_trace_id()
    logger.exception(f"Unhandled exception | trace_id={trace_id}")
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "Internal Server Error",
            "data": None,
            "trace_id": trace_id
        }
    )
