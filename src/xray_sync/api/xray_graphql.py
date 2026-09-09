from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from xray_sync.api.retry import api_retry, raise_for_api_error
from xray_sync.api.xray_auth import XrayAuthClient
from xray_sync.config import XrayEnvironmentConfig
from xray_sync.exceptions import ApiError


class XrayGraphQLClient:
    def __init__(
        self,
        config: XrayEnvironmentConfig,
        auth: XrayAuthClient,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.config = config
        self.auth = auth
        self._client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> XrayGraphQLClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request(query, variables)

    async def mutate(
        self, mutation: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._request(mutation, variables)

    @api_retry
    async def _request(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self.auth.token()
        response = await self._client.post(
            str(self.config.graphql_url),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": query, "variables": variables or {}},
        )
        raise_for_api_error(response)
        payload = response.json()
        errors = payload.get("errors")
        if errors:
            raise ApiError("Xray GraphQL returned errors", detail={"errors": errors})
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ApiError("Xray GraphQL response did not contain a data object", detail=payload)
        return data

    async def paginate(
        self,
        query: str,
        *,
        root_field: str,
        variables: dict[str, Any] | None = None,
        limit_variable: str = "limit",
        start_variable: str = "start",
        page_size: int = 100,
    ) -> AsyncIterator[dict[str, Any]]:
        start = 0
        while True:
            page_variables = dict(variables or {})
            page_variables[limit_variable] = page_size
            page_variables[start_variable] = start
            data = await self.query(query, page_variables)
            page = data.get(root_field) or {}
            results = page.get("results") or []
            for item in results:
                # Xray returns null entries for issues the caller cannot read, so skip
                # them here rather than in every consumer.
                if isinstance(item, dict):
                    yield item
            # Advance by the raw page length, including skipped entries, so pagination
            # still terminates.
            start += len(results)
            total = int(page.get("total", 0))
            if start >= total or not results:
                break
