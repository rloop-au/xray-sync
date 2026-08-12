from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from xray_sync.api.retry import api_retry, raise_for_api_error
from xray_sync.config import XrayEnvironmentConfig
from xray_sync.exceptions import AuthenticationError


class XrayAuthClient:
    def __init__(self, config: XrayEnvironmentConfig, *, timeout: float = 30.0) -> None:
        self.config = config
        self._client = httpx.AsyncClient(timeout=timeout)
        self._token: str | None = None
        self._expires_at: datetime | None = None

    async def __aenter__(self) -> XrayAuthClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def token(self) -> str:
        if self._token and self._expires_at and datetime.now(UTC) < self._expires_at:
            return self._token
        return await self.authenticate()

    @api_retry
    async def authenticate(self) -> str:
        response = await self._client.post(
            str(self.config.auth_url),
            json={"client_id": self.config.client_id, "client_secret": self.config.client_secret},
        )
        raise_for_api_error(response)
        data = response.json()
        if isinstance(data, str):
            token = data.strip('"')
        elif isinstance(data, dict) and isinstance(data.get("token"), str):
            token = data["token"]
        else:
            raise AuthenticationError("Xray authentication response did not contain a token")
        self._token = token
        self._expires_at = datetime.now(UTC) + timedelta(minutes=50)
        return token
