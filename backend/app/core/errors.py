from __future__ import annotations

from fastapi import HTTPException, status


class AppError(Exception):
    """Base application exception."""


class ConfigurationError(AppError):
    """Raised when required configuration is missing or invalid."""


class LLMProviderError(AppError):
    """Raised when an LLM provider fails."""


class LLMProviderUnavailableError(LLMProviderError):
    """Raised when a selected LLM provider is unavailable."""


def http_503(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message)


def http_500(message: str = "Unexpected internal server error.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message)
