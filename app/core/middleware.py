import logging
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import trace_id_context

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("X-Trace-ID") or str(uuid4())
        token = trace_id_context.set(trace_id)
        request.state.trace_id = trace_id

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.exception(
                f"Request failed | trace_id={trace_id} | method={request.method} | path={request.url.path} | "
                f"duration_ms={duration_ms}")
            raise

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Trace-ID"] = trace_id

        logger.info(
            f"Request completed |trace_id={trace_id} | method={request.method} | path={request.url.path} | statude_code={response.status_code} | duration_ms={duration_ms}")
        trace_id_context.reset(token)
        return response
