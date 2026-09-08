"""Domain and API error contracts for SETU-DRR.

All errors conform to a standardized error envelope (PRD & Implementation Plan §35):
{
    "error": {
        "code": "HABITATION_NOT_FOUND",
        "message": "Habitation does not exist.",
        "request_id": "...",
        "details": {}
    }
}
"""

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Standardized machine-readable error codes."""
    INVALID_H3 = "INVALID_H3"
    INVALID_BBOX = "INVALID_BBOX"
    INVALID_RESOLUTION = "INVALID_RESOLUTION"
    INVALID_TIME = "INVALID_TIME"
    HABITATION_NOT_FOUND = "HABITATION_NOT_FOUND"
    SITE_NOT_FOUND = "SITE_NOT_FOUND"
    ADMIN_BOUNDARY_NOT_FOUND = "ADMIN_BOUNDARY_NOT_FOUND"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    SCENARIO_LIMIT_EXCEEDED = "SCENARIO_LIMIT_EXCEEDED"
    ALLOCATION_FAILED = "ALLOCATION_FAILED"
    PIPELINE_NOT_READY = "PIPELINE_NOT_READY"
    DATABASE_ERROR = "DATABASE_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base application exception for all domain and HTTP-mapped errors."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self, request_id: str | None = None) -> dict[str, Any]:
        """Formats the exception into the standard API error response format."""
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "request_id": request_id,
                "details": self.details,
            }
        }


class InvalidH3IndexError(AppError):
    def __init__(self, h3_index: str | int, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code=ErrorCode.INVALID_H3,
            message=f"Invalid H3 index: '{h3_index}'.",
            status_code=400,
            details={"h3_index": str(h3_index), **(details or {})},
        )


class HabitationNotFoundError(AppError):
    def __init__(self, habitation_id: str | int) -> None:
        super().__init__(
            code=ErrorCode.HABITATION_NOT_FOUND,
            message=f"Habitation with ID '{habitation_id}' was not found.",
            status_code=404,
            details={"habitation_id": str(habitation_id)},
        )


class SiteNotFoundError(AppError):
    def __init__(self, site_id: str | int) -> None:
        super().__init__(
            code=ErrorCode.SITE_NOT_FOUND,
            message=f"Candidate site with ID '{site_id}' was not found.",
            status_code=404,
            details={"site_id": str(site_id)},
        )


class AdminBoundaryNotFoundError(AppError):
    def __init__(self, admin_id: str | int) -> None:
        super().__init__(
            code=ErrorCode.ADMIN_BOUNDARY_NOT_FOUND,
            message=f"Admin boundary with ID/LGD '{admin_id}' was not found.",
            status_code=404,
            details={"admin_id": str(admin_id)},
        )


class PipelineNotReadyError(AppError):
    def __init__(self, dataset_name: str = "default") -> None:
        super().__init__(
            code=ErrorCode.PIPELINE_NOT_READY,
            message=f"Pipeline dataset '{dataset_name}' is not published or ready for serving.",
            status_code=503,
            details={"dataset_name": dataset_name},
        )


class InvalidBboxError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code=ErrorCode.INVALID_BBOX,
            message=message,
            status_code=400,
            details=details or {},
        )


class InvalidResolutionError(AppError):
    def __init__(self, res: int | str, allowed: list[int] = [6, 7, 8, 9]) -> None:
        super().__init__(
            code=ErrorCode.INVALID_RESOLUTION,
            message=f"Invalid H3 resolution '{res}'. Allowed resolutions are {allowed}.",
            status_code=400,
            details={"resolution": str(res), "allowed": allowed},
        )


class InvalidTimeError(AppError):
    def __init__(self, time_val: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code=ErrorCode.INVALID_TIME,
            message=f"Invalid timestamp format or out of bounds: '{time_val}'.",
            status_code=400,
            details={"time": time_val, **(details or {})},
        )


class DataUnavailableError(AppError):
    def __init__(self, message: str = "Requested data is unavailable.", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code=ErrorCode.DATA_UNAVAILABLE,
            message=message,
            status_code=404,
            details=details or {},
        )


class InvalidParametersError(AppError):
    def __init__(self, message: str = "Invalid request parameters.", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            message=message,
            status_code=422,
            details=details or {},
        )



class AllocationFailedError(AppError):
    def __init__(self, reason: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code=ErrorCode.ALLOCATION_FAILED,
            message=f"Allocation solver failed: {reason}",
            status_code=422,
            details=details,
        )


class UnauthenticatedError(AppError):
    def __init__(self, message: str = "Authentication required.", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code=ErrorCode.UNAUTHENTICATED,
            message=message,
            status_code=401,
            details=details or {},
        )


class ForbiddenError(AppError):
    def __init__(self, message: str = "Access forbidden.", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code=ErrorCode.FORBIDDEN,
            message=message,
            status_code=403,
            details=details or {},
        )


class RateLimitExceededError(AppError):
    """Raised when a client IP or account exceeds the permitted request rate (HTTP 429)."""

    def __init__(
        self,
        message: str = "Too many login attempts. Please try again later.",
        retry_after_seconds: int = 60,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details = {"retry_after_seconds": retry_after_seconds, **(details or {})}
        super().__init__(
            code=ErrorCode.RATE_LIMITED,
            message=message,
            status_code=429,
            details=merged_details,
        )

