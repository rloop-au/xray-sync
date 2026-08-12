from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from xray_sync.exceptions import ApiError, RateLimitError


def is_rate_limited(response: httpx.Response) -> bool:
    return response.status_code == 429


def raise_for_api_error(response: httpx.Response) -> None:
    if response.status_code == 429:
        retry_after = response.headers.get("retry-after")
        raise RateLimitError(
            "API rate limit exceeded",
            detail={"status_code": 429, "retry_after": retry_after},
        )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ApiError(
            f"API request failed with status {response.status_code}",
            detail={"status_code": response.status_code, "body": response.text[:2000]},
        ) from exc


api_retry = retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError, RateLimitError)),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
