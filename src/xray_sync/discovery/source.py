from __future__ import annotations

from typing import Any

from xray_sync.api.jira import JiraClient
from xray_sync.api.xray_graphql import XrayGraphQLClient
from xray_sync.model.execution import TestExecution
from xray_sync.model.precondition import Precondition
from xray_sync.model.repository import RepositoryTree
from xray_sync.model.snapshot import ProjectSnapshot
from xray_sync.model.test import TestStep, XrayTest
from xray_sync.model.test_plan import TestPlan
from xray_sync.model.test_set import TestSet


class SourceDiscovery:
    def __init__(self, jira: JiraClient, xray: XrayGraphQLClient) -> None:
        self.jira = jira
        self.xray = xray

    async def discover_project(self, project_key: str) -> ProjectSnapshot:
        project = await self.jira.get_project(project_key)
        snapshot = ProjectSnapshot(
            project_key=project_key,
            project=project,
            tests=await self.discover_tests(project_key),
            preconditions=await self.discover_preconditions(project_key),
            test_sets=await self.discover_test_sets(project_key),
            test_plans=await self.discover_test_plans(project_key),
            executions=await self.discover_test_executions(project_key),
            repository=RepositoryTree(project_key=project_key),
        )
        return snapshot

    async def discover_tests(self, project_key: str) -> dict[str, XrayTest]:
        query = """
        query GetTests($jql: String!, $limit: Int!, $start: Int!) {
          getTests(jql: $jql, limit: $limit, start: $start) {
            total
            results {
              issueId
              projectId
              testType { name }
              jira(fields: ["key"])
              unstructured
              gherkin
              folder { path }
              steps { id action data result }
              preconditions(limit: 100) { results { issueId jira(fields: ["key"]) } }
              testSets(limit: 100) { results { issueId jira(fields: ["key"]) } }
              testPlans(limit: 100) { results { issueId jira(fields: ["key"]) } }
            }
          }
        }
        """
        tests: dict[str, XrayTest] = {}
        async for item in self.xray.paginate(
            query,
            root_field="getTests",
            variables={"jql": f'project = "{project_key}"'},
        ):
            key = _jira_key(item)
            if not key:
                continue
            steps = [
                TestStep(
                    id=step.get("id"),
                    action=step.get("action"),
                    data=step.get("data"),
                    expected_result=step.get("result"),
                )
                for step in item.get("steps", [])
            ]
            tests[key] = XrayTest(
                jira_key=key,
                jira_id=item.get("issueId"),
                xray_id=item.get("issueId"),
                test_type=(item.get("testType") or {}).get("name"),
                unstructured=item.get("unstructured"),
                gherkin=item.get("gherkin"),
                folder_path=(item.get("folder") or {}).get("path"),
                steps=steps,
                preconditions=_connection_keys(item, "preconditions"),
                test_sets=_connection_keys(item, "testSets"),
                test_plans=_connection_keys(item, "testPlans"),
                raw=item,
            )
        return tests

    async def discover_preconditions(self, project_key: str) -> dict[str, Precondition]:
        query = """
        query GetPreconditions($jql: String!, $limit: Int!, $start: Int!) {
          getPreconditions(jql: $jql, limit: $limit, start: $start) {
            total
            results {
              issueId
              definition
              preconditionType { name }
              jira(fields: ["key"])
            }
          }
        }
        """
        items: dict[str, Precondition] = {}
        async for item in self.xray.paginate(
            query,
            root_field="getPreconditions",
            variables={"jql": f'project = "{project_key}"'},
        ):
            key = _jira_key(item)
            if key:
                items[key] = Precondition(
                    jira_key=key,
                    jira_id=item.get("issueId"),
                    xray_id=item.get("issueId"),
                    definition=item.get("definition"),
                    precondition_type=(item.get("preconditionType") or {}).get("name"),
                    raw=item,
                )
        return items

    async def discover_test_sets(self, project_key: str) -> dict[str, TestSet]:
        query = """
        query GetTestSets($jql: String!, $limit: Int!, $start: Int!) {
          getTestSets(jql: $jql, limit: $limit, start: $start) {
            total
            results {
              issueId
              jira(fields: ["key"])
              tests(limit: 100) { results { jira(fields: ["key"]) } }
            }
          }
        }
        """
        items: dict[str, TestSet] = {}
        async for item in self.xray.paginate(
            query,
            root_field="getTestSets",
            variables={"jql": f'project = "{project_key}"'},
        ):
            key = _jira_key(item)
            if key:
                items[key] = TestSet(
                    jira_key=key,
                    jira_id=item.get("issueId"),
                    xray_id=item.get("issueId"),
                    tests=_nested_test_keys(item),
                    raw=item,
                )
        return items

    async def discover_test_plans(self, project_key: str) -> dict[str, TestPlan]:
        query = """
        query GetTestPlans($jql: String!, $limit: Int!, $start: Int!) {
          getTestPlans(jql: $jql, limit: $limit, start: $start) {
            total
            results {
              issueId
              jira(fields: ["key"])
              tests(limit: 100) { results { jira(fields: ["key"]) } }
            }
          }
        }
        """
        items: dict[str, TestPlan] = {}
        async for item in self.xray.paginate(
            query,
            root_field="getTestPlans",
            variables={"jql": f'project = "{project_key}"'},
        ):
            key = _jira_key(item)
            if key:
                items[key] = TestPlan(
                    jira_key=key,
                    jira_id=item.get("issueId"),
                    xray_id=item.get("issueId"),
                    tests=_nested_test_keys(item),
                    raw=item,
                )
        return items

    async def discover_test_executions(self, project_key: str) -> dict[str, TestExecution]:
        query = """
        query GetTestExecutions($jql: String!, $limit: Int!, $start: Int!) {
          getTestExecutions(jql: $jql, limit: $limit, start: $start) {
            total
            results {
              issueId
              jira(fields: ["key"])
              tests(limit: 100) { results { jira(fields: ["key"]) } }
            }
          }
        }
        """
        items: dict[str, TestExecution] = {}
        async for item in self.xray.paginate(
            query,
            root_field="getTestExecutions",
            variables={"jql": f'project = "{project_key}"'},
        ):
            key = _jira_key(item)
            if key:
                items[key] = TestExecution(
                    jira_key=key,
                    jira_id=item.get("issueId"),
                    xray_id=item.get("issueId"),
                    tests=_nested_test_keys(item),
                    raw=item,
                )
        return items


def _jira_key(item: dict[str, Any]) -> str | None:
    jira = item.get("jira")
    if isinstance(jira, dict):
        key = jira.get("key")
        return str(key) if key else None
    return None


def _nested_test_keys(item: dict[str, Any]) -> list[str]:
    tests = item.get("tests") or {}
    results = tests.get("results") or []
    return sorted(key for result in results if (key := _jira_key(result)))


def _connection_keys(item: dict[str, Any], field: str) -> list[str]:
    connection = item.get(field) or {}
    results = connection.get("results") or []
    return sorted(key for result in results if (key := _jira_key(result)))
