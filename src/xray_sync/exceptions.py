from __future__ import annotations

from typing import Any


class XraySyncError(Exception):
    """Base exception for all xray-sync failures."""

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail = detail or {}


class AuthenticationError(XraySyncError):
    pass


class MappingError(XraySyncError):
    pass


class ApiError(XraySyncError):
    pass


class RateLimitError(ApiError):
    pass


class IntegrityError(XraySyncError):
    pass


class PlanError(XraySyncError):
    pass


class ConfigurationError(XraySyncError):
    pass
