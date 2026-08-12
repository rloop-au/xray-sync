from __future__ import annotations

import pytest
import respx
from httpx import Response

from xray_sync.api.xray_auth import XrayAuthClient
from xray_sync.api.xray_graphql import XrayGraphQLClient
from xray_sync.config import XrayEnvironmentConfig
from xray_sync.exceptions import ApiError


@respx.mock
async def test_graphql_extracts_data(monkeypatch) -> None:
    monkeypatch.setenv("XRAY_CLIENT_ID", "id")
    monkeypatch.setenv("XRAY_CLIENT_SECRET", "secret")
    config = XrayEnvironmentConfig(
        client_id_env="XRAY_CLIENT_ID",
        client_secret_env="XRAY_CLIENT_SECRET",
    )
    respx.post("https://xray.cloud.getxray.app/api/v2/authenticate").mock(
        return_value=Response(200, json="token-value")
    )
    respx.post("https://xray.cloud.getxray.app/api/v2/graphql").mock(
        return_value=Response(200, json={"data": {"__typename": "Query"}})
    )

    async with XrayAuthClient(config) as auth:
        async with XrayGraphQLClient(config, auth) as graphql:
            data = await graphql.query("query { __typename }")

    assert data == {"__typename": "Query"}


@respx.mock
async def test_graphql_errors_raise_api_error(monkeypatch) -> None:
    monkeypatch.setenv("XRAY_CLIENT_ID", "id")
    monkeypatch.setenv("XRAY_CLIENT_SECRET", "secret")
    config = XrayEnvironmentConfig(
        client_id_env="XRAY_CLIENT_ID",
        client_secret_env="XRAY_CLIENT_SECRET",
    )
    respx.post("https://xray.cloud.getxray.app/api/v2/authenticate").mock(
        return_value=Response(200, json="token-value")
    )
    respx.post("https://xray.cloud.getxray.app/api/v2/graphql").mock(
        return_value=Response(200, json={"errors": [{"message": "bad query"}]})
    )

    async with XrayAuthClient(config) as auth:
        async with XrayGraphQLClient(config, auth) as graphql:
            with pytest.raises(ApiError):
                await graphql.query("query { nope }")
