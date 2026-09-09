from __future__ import annotations

from typing import Any

from xray_sync.api.jira import JiraClient
from xray_sync.api.xray_graphql import XrayGraphQLClient
from xray_sync.exceptions import ApiError
from xray_sync.model.execution import TestExecution
from xray_sync.model.precondition import Precondition
from xray_sync.model.repository import RepositoryTree
from xray_sync.model.snapshot import ProjectSnapshot
from xray_sync.model.test import TestStep, XrayTest
from xray_sync.model.test_plan import TestPlan
from xray_sync.model.test_run import TestRun
from xray_sync.model.test_set import TestSet


class SourceDiscovery:
    def __init__(self, jira: JiraClient, xray: XrayGraphQLClient) -> None:
        self.jira = jira
        self.xray = xray

    async def discover_project(self, project_key: str) -> ProjectSnapshot:
        project = await self.jira.get_project(project_key)
        tests = await self.discover_tests(project_key)
        executions = await self.discover_test_executions(project_key)
        snapshot = ProjectSnapshot(
            project_key=project_key,
            project=project,
            tests=tests,
            preconditions=await self.discover_preconditions(project_key),
            test_sets=await self.discover_test_sets(project_key),
            test_plans=await self.discover_test_plans(project_key),
            executions=executions,
            test_runs=await self.discover_test_runs(executions),
            repository=RepositoryTree(project_key=project_key),
        )
        return snapshot

    async def enrich_referenced_containers(
        self, snapshot: ProjectSnapshot, reference: ProjectSnapshot
    ) -> ProjectSnapshot:
        external_test_keys = _referenced_execution_test_keys(reference) - set(snapshot.tests)
        external_tests = await self._get_external_tests(snapshot.project_key, external_test_keys)
        for key, test in external_tests.items():
            snapshot.tests[key] = test
        external_execution_keys = _referenced_test_plan_execution_keys(reference) - set(
            snapshot.executions
        )
        external_executions = await self._get_external_test_executions(
            snapshot.project_key, external_execution_keys
        )
        for key, execution in external_executions.items():
            snapshot.executions[key] = execution
        for key in _referenced_keys(reference.tests, "preconditions") - set(snapshot.preconditions):
            issue = await self._get_external_container_issue(snapshot.project_key, key)
            if not issue:
                continue
            snapshot.preconditions[key] = Precondition(
                jira_key=issue.key,
                jira_id=issue.id,
                xray_id=issue.id,
                raw={"jira": issue.model_dump(mode="json")},
            )
        for key in _referenced_keys(reference.tests, "test_sets") - set(snapshot.test_sets):
            issue = await self._get_external_container_issue(snapshot.project_key, key)
            if not issue:
                continue
            snapshot.test_sets[key] = TestSet(
                jira_key=issue.key,
                jira_id=issue.id,
                xray_id=issue.id,
                raw={"jira": issue.model_dump(mode="json")},
            )
        for key in _referenced_keys(reference.tests, "test_plans") - set(snapshot.test_plans):
            test_plan = await self._get_external_test_plan(snapshot.project_key, key)
            if not test_plan:
                continue
            snapshot.test_plans[key] = test_plan
        return snapshot

    async def _get_external_tests(
        self, project_key: str, keys: set[str]
    ) -> dict[str, XrayTest]:
        external_keys = sorted(key for key in keys if _issue_project_key(key) != project_key)
        tests: dict[str, XrayTest] = {}
        for batch in _batches(external_keys, 50):
            jql_keys = ", ".join(f'"{key}"' for key in batch)
            async for item in self.xray.paginate(
                """
                query GetTestsByKeys($jql: String!, $limit: Int!, $start: Int!) {
                  getTests(jql: $jql, limit: $limit, start: $start) {
                    total
                    results {
                      issueId
                      projectId
                      testType { name }
                      jira(fields: ["key"])
                    }
                  }
                }
                """,
                root_field="getTests",
                variables={"jql": f"key in ({jql_keys})"},
                page_size=100,
            ):
                key = _jira_key(item)
                if not key:
                    continue
                tests[key] = XrayTest(
                    jira_key=key,
                    jira_id=item.get("issueId"),
                    xray_id=item.get("issueId"),
                    test_type=(item.get("testType") or {}).get("name"),
                    raw=item,
                )
        return tests

    async def _get_external_test_executions(
        self, project_key: str, keys: set[str]
    ) -> dict[str, TestExecution]:
        external_keys = sorted(key for key in keys if _issue_project_key(key) != project_key)
        executions: dict[str, TestExecution] = {}
        for batch in _batches(external_keys, 50):
            jql_keys = ", ".join(f'"{key}"' for key in batch)
            async for item in self.xray.paginate(
                """
                query GetTestExecutionsByKeys($jql: String!, $limit: Int!, $start: Int!) {
                  getTestExecutions(jql: $jql, limit: $limit, start: $start) {
                    total
                    results {
                      issueId
                      jira(fields: ["key"])
                    }
                  }
                }
                """,
                root_field="getTestExecutions",
                variables={"jql": f"key in ({jql_keys})"},
                page_size=100,
            ):
                key = _jira_key(item)
                if not key:
                    continue
                executions[key] = TestExecution(
                    jira_key=key,
                    jira_id=item.get("issueId"),
                    xray_id=item.get("issueId"),
                    raw=item,
                )
        return executions

    async def _get_external_container_issue(self, project_key: str, key: str) -> Any | None:
        try:
            return await self.jira.get_issue(key)
        except ApiError as exc:
            if exc.detail.get("status_code") == 404 and _issue_project_key(key) != project_key:
                return None
            raise

    async def _get_external_test_plan(self, project_key: str, key: str) -> TestPlan | None:
        if _issue_project_key(key) == project_key:
            issue = await self.jira.get_issue(key)
            return TestPlan(jira_key=issue.key, jira_id=issue.id, xray_id=issue.id)
        item = await self._get_xray_issue_by_key(
            "getTestPlans",
            """
            query GetTestPlansByKey($jql: String!, $limit: Int!, $start: Int!) {
              getTestPlans(jql: $jql, limit: $limit, start: $start) {
                total
                results { issueId jira(fields: ["key"]) }
              }
            }
            """,
            key,
        )
        if not item:
            return None
        jira_key = _jira_key(item)
        return TestPlan(
            jira_key=jira_key or key,
            jira_id=item.get("issueId"),
            xray_id=item.get("issueId"),
            raw=item,
        )

    async def _get_xray_issue_by_key(
        self, root_field: str, query: str, key: str
    ) -> dict[str, Any] | None:
        data = await self.xray.query(query, {"jql": f'key = "{key}"', "limit": 1, "start": 0})
        results = (data.get(root_field) or {}).get("results") or []
        return results[0] if results and isinstance(results[0], dict) else None

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
                for step in item.get("steps") or []
                if isinstance(step, dict)
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
              testExecutions(limit: 100) { results { jira(fields: ["key"]) } }
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
                    executions=_connection_keys(item, "testExecutions"),
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

    async def discover_test_runs(
        self, executions: dict[str, TestExecution]
    ) -> dict[str, TestRun]:
        execution_ids = [
            execution.xray_id for execution in executions.values() if execution.xray_id
        ]
        test_runs: dict[str, TestRun] = {}
        for batch in _batches(execution_ids, 50):
            start = 0
            while True:
                data = await self.xray.query(
                    """
                    query GetTestRuns(
                      $testExecIssueIds: [String],
                      $limit: Int!,
                      $start: Int
                    ) {
                      getTestRuns(
                        testExecIssueIds: $testExecIssueIds,
                        limit: $limit,
                        start: $start
                      ) {
                        total
                        results {
                          id
                          status { name }
                          test { jira(fields: ["key"]) }
                          testExecution { jira(fields: ["key"]) }
                        }
                      }
                    }
                    """,
                    {"testExecIssueIds": batch, "limit": 100, "start": start},
                )
                page = data.get("getTestRuns") or {}
                results = page.get("results") or []
                for item in results:
                    test_key = _jira_key(item.get("test"))
                    execution_key = _jira_key(item.get("testExecution"))
                    if not test_key or not execution_key:
                        continue
                    test_runs[f"{execution_key}:{test_key}"] = TestRun(
                        id=item["id"],
                        test_key=test_key,
                        execution_key=execution_key,
                        status=(item.get("status") or {}).get("name"),
                        raw=item,
                    )
                start += len(results)
                if start >= int(page.get("total") or 0) or not results:
                    break
        return test_runs


def _jira_key(item: Any) -> str | None:
    """Read a Jira key from a connection entry.

    Xray returns null entries for issues the caller cannot read - a Test Execution
    referencing a deleted or permission-filtered Test, for example - so entries that
    are not objects are treated as keyless rather than raising.
    """
    if not isinstance(item, dict):
        return None
    jira = item.get("jira")
    if isinstance(jira, dict):
        key = jira.get("key")
        return str(key) if key else None
    return None


def _nested_test_keys(item: dict[str, Any]) -> list[str]:
    return _connection_keys(item, "tests")


def _connection_keys(item: dict[str, Any], field: str) -> list[str]:
    connection = item.get(field)
    if not isinstance(connection, dict):
        return []
    results = connection.get("results")
    if not isinstance(results, list):
        return []
    return sorted(key for result in results if (key := _jira_key(result)))


def _referenced_keys(tests: dict[str, XrayTest], field: str) -> set[str]:
    keys: set[str] = set()
    for test in tests.values():
        values = getattr(test, field)
        keys.update(values)
    return keys


def _referenced_execution_test_keys(snapshot: ProjectSnapshot) -> set[str]:
    keys: set[str] = set()
    for execution in snapshot.executions.values():
        keys.update(execution.tests)
    return keys


def _referenced_test_plan_execution_keys(snapshot: ProjectSnapshot) -> set[str]:
    keys: set[str] = set()
    for test_plan in snapshot.test_plans.values():
        keys.update(test_plan.executions)
    return keys


def _batches(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _issue_project_key(issue_key: str) -> str:
    return issue_key.split("-", 1)[0]
