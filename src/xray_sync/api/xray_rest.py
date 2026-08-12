from __future__ import annotations

from typing import Any

import httpx

from xray_sync.api.retry import api_retry, raise_for_api_error
from xray_sync.api.xray_auth import XrayAuthClient
from xray_sync.config import XrayEnvironmentConfig


class XrayRestClient:
    def __init__(
        self,
        config: XrayEnvironmentConfig,
        auth: XrayAuthClient,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.config = config
        self.auth = auth
        self._client = httpx.AsyncClient(base_url=str(config.rest_url).rstrip("/"), timeout=timeout)

    async def __aenter__(self) -> XrayRestClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    @api_retry
    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        token = await self.auth.token()
        response = await self._client.request(
            method,
            path,
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        raise_for_api_error(response)
        if response.content:
            return response.json()
        return None
