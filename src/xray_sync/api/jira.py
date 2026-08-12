from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx

from xray_sync.api.retry import api_retry, raise_for_api_error
from xray_sync.config import JiraEnvironmentConfig
from xray_sync.model.jira import JiraIssue, JiraIssueType, JiraProject


class JiraClient:
    def __init__(self, config: JiraEnvironmentConfig, *, timeout: float = 30.0) -> None:
        self.config = config
        token = base64.b64encode(f"{config.email}:{config.token}".encode()).decode()
        self._client = httpx.AsyncClient(
            base_url=str(config.url).rstrip("/"),
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {token}",
            },
        )

    async def __aenter__(self) -> JiraClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    @api_retry
    async def get_issue(self, key: str) -> JiraIssue:
        response = await self._client.get(f"/rest/api/3/issue/{key}")
        raise_for_api_error(response)
        return JiraIssue.model_validate(response.json())

    @api_retry
    async def get_project(self, key: str) -> JiraProject:
        response = await self._client.get(f"/rest/api/3/project/{key}")
        raise_for_api_error(response)
        return JiraProject.model_validate(response.json())

    @api_retry
    async def get_issue_types(self) -> list[JiraIssueType]:
        response = await self._client.get("/rest/api/3/issuetype")
        raise_for_api_error(response)
        return [JiraIssueType.model_validate(item) for item in response.json()]

    async def search_issues(self, jql: str) -> list[JiraIssue]:
        issues: list[JiraIssue] = []
        async for issue in self.iter_search_issues(jql):
            issues.append(issue)
        return issues

    async def iter_search_issues(
        self, jql: str, *, page_size: int = 100
    ) -> AsyncIterator[JiraIssue]:
        start_at = 0
        while True:
            page = await self._search_page(jql, start_at=start_at, max_results=page_size)
            for item in page.get("issues", []):
                yield JiraIssue.model_validate(item)
            start_at += len(page.get("issues", []))
            if start_at >= int(page.get("total", 0)) or not page.get("issues"):
                break

    @api_retry
    async def _search_page(
        self, jql: str, *, start_at: int, max_results: int
    ) -> dict[str, Any]:
        response = await self._client.get(
            "/rest/api/3/search",
            params={"jql": jql, "startAt": start_at, "maxResults": max_results},
        )
        raise_for_api_error(response)
        return cast(dict[str, Any], response.json())
