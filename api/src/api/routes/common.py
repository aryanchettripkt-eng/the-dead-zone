"""Reusable OpenAPI error response declarations and helpers for API routes."""

from typing import Any
from core.schemas.common import ErrorEnvelope

COMMON_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    400: {
        "model": ErrorEnvelope,
        "description": "Bad Request - Invalid parameters or malformed input format.",
    },
    401: {
        "model": ErrorEnvelope,
        "description": "Unauthenticated - Missing, invalid, expired, or revoked session cookie.",
    },
    403: {
        "model": ErrorEnvelope,
        "description": "Forbidden - Insufficient permissions or role.",
    },
    404: {
        "model": ErrorEnvelope,
        "description": "Not Found - Requested resource, cell, or entity does not exist.",
    },
    422: {
        "model": ErrorEnvelope,
        "description": "Validation Error - Request parameter or payload validation failed.",
    },
    429: {
        "model": ErrorEnvelope,
        "description": "Too Many Requests - Rate limit exceeded. Please try again later.",
    },
    500: {
        "model": ErrorEnvelope,
        "description": "Internal Server Error - An unexpected system or database error occurred.",
    },
    503: {
        "model": ErrorEnvelope,
        "description": "Service Unavailable - No valid serving version is active. Pipeline data is not ready.",
    },
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """Builds an OpenAPI responses dictionary for the specified HTTP error status codes."""
    return {code: COMMON_ERROR_RESPONSES[code] for code in status_codes if code in COMMON_ERROR_RESPONSES}
