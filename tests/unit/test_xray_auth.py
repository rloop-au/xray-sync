from __future__ import annotations

import respx
from httpx import Response

from xray_sync.api.xray_auth import XrayAuthClient
from xray_sync.config import XrayEnvironmentConfig


@respx.mock
async def test_authenticate_accepts_string_token(monkeypatch) -> None:
    monkeypatch.setenv("XRAY_CLIENT_ID", "id")
    monkeypatch.setenv("XRAY_CLIENT_SECRET", "secret")
    config = XrayEnvironmentConfig(
        client_id_env="XRAY_CLIENT_ID",
        client_secret_env="XRAY_CLIENT_SECRET",
    )
    respx.post("https://xray.cloud.getxray.app/api/v2/authenticate").mock(
        return_value=Response(200, json="token-value")
    )

    async with XrayAuthClient(config) as client:
        token = await client.authenticate()

    assert token == "token-value"


@respx.mock
async def test_token_is_cached(monkeypatch) -> None:
    monkeypatch.setenv("XRAY_CLIENT_ID", "id")
    monkeypatch.setenv("XRAY_CLIENT_SECRET", "secret")
    config = XrayEnvironmentConfig(
        client_id_env="XRAY_CLIENT_ID",
        client_secret_env="XRAY_CLIENT_SECRET",
    )
    route = respx.post("https://xray.cloud.getxray.app/api/v2/authenticate").mock(
        return_value=Response(200, json="token-value")
    )

    async with XrayAuthClient(config) as client:
        assert await client.token() == "token-value"
        assert await client.token() == "token-value"

    assert route.call_count == 1
