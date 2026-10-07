from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.errors import LLMProviderError, LLMProviderUnavailableError


async def post_cloud_json(
    *, provider: str, url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    """Send one cloud request with bounded time and no credentials in error messages."""
    try:
        async with asyncio.timeout(timeout), httpx.AsyncClient(
            timeout=timeout, trust_env=False,
            headers={"Accept-Encoding": "gzip, deflate", **headers},
        ) as client:
            response = await client.post(url, json=payload)
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise LLMProviderUnavailableError(f"{provider} request timed out.") from exc
    except httpx.RequestError as exc:
        raise LLMProviderUnavailableError(
            f"Could not connect to {provider}. Check your network and HTTPS access."
        ) from exc

    if response.is_error:
        status = response.status_code
        try:
            body = response.json()
        except ValueError:
            body = {}
        error = body.get("error", {}) if isinstance(body, dict) else {}
        detail = str(error).lower()
        key_name = "GEMINI_API_KEY" if provider == "Gemini" else "OPENAI_API_KEY"
        if status == 401 or (status == 400 and "api key" in detail):
            message = f"{provider} rejected the API key. Check {key_name} in backend/.env."
        elif status == 403:
            message = f"{provider} denied access. Check API key permissions and regional availability."
        elif status == 404:
            model_name = "GEMINI_MODEL" if provider == "Gemini" else "OPENAI_MODEL"
            message = f"{provider} model unavailable. Check {model_name} in backend/.env."
        elif status == 429:
            message = (
                f"{provider} quota or rate limit reached. Check API usage and billing, or retry later."
            )
        elif status >= 500:
            raise LLMProviderUnavailableError(f"{provider} is temporarily unavailable. Retry later.")
        else:
            message = f"{provider} rejected the request (HTTP {status}). Check model settings and API access."
        raise LLMProviderError(message)

    try:
        data = response.json()
    except ValueError as exc:
        raise LLMProviderError(f"{provider} returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise LLMProviderError(f"{provider} returned an unexpected response.")
    return data
