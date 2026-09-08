"""API middlewares for request tracking, structured logging, and error handling."""

import time
import uuid
import logging
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.errors import AppError, ErrorCode

logger = logging.getLogger("setu_api")


class RequestIdAndLoggingMiddleware(BaseHTTPMiddleware):
    """Generates X-Request-ID, attaches it to request state, and logs request lifecycle."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            process_time = (time.perf_counter() - start_time) * 1000.0

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"

            logger.info(
                f"method={request.method} path={request.url.path} "
                f"status={response.status_code} latency_ms={process_time:.2f} "
                f"request_id={request_id}"
            )
            return response

        except AppError as exc:
            process_time = (time.perf_counter() - start_time) * 1000.0
            logger.warning(
                f"method={request.method} path={request.url.path} "
                f"app_error={exc.code} latency_ms={process_time:.2f} "
                f"request_id={request_id} msg={exc.message}"
            )
            error_dict = exc.to_dict(request_id=request_id)
            res = JSONResponse(status_code=exc.status_code, content=error_dict)
            res.headers["X-Request-ID"] = request_id
            return res

        except Exception as exc:
            process_time = (time.perf_counter() - start_time) * 1000.0
            logger.exception(
                f"method={request.method} path={request.url.path} "
                f"status=500 latency_ms={process_time:.2f} "
                f"request_id={request_id} unhandled_error={exc}"
            )
            error_dict = {
                "error": {
                    "code": ErrorCode.INTERNAL_ERROR.value,
                    "message": "An internal server error occurred.",
                    "request_id": request_id,
                    "details": {},
                }
            }
            res = JSONResponse(status_code=500, content=error_dict)
            res.headers["X-Request-ID"] = request_id
            return res
