from __future__ import annotations

from typing import Any

from xray_sync.discovery.source import (
    SourceDiscovery,
    _connection_keys,
    _jira_key,
    _nested_test_keys,
)
from xray_sync.exceptions import ApiError
from xray_sync.model.execution import TestExecution
from xray_sync.model.jira import JiraIssue
from xray_sync.model.snapshot import ProjectSnapshot
from xray_sync.model.test import XrayTest
from xray_sync.model.test_plan import TestPlan


class FakeJira:
    async def get_issue(self, key: str) -> JiraIssue:
        return JiraIssue(
            id={"LOY-123": "target-test-id", "ZSD-4764": "target-plan-id"}[key],
            key=key,
            fields={"issuetype": {"name": "Test Plan"}},
        )


class MissingExternalJira:
    async def get_issue(self, key: str) -> JiraIssue:
        raise ApiError("missing", detail={"status_code": 404})


class FakeXray:
    async def query(self, query: str, variables: dict[str, object] | None = None) -> dict:
        key = str((variables or {}).get("jql", "")).split('"')[1]
        if "getTests" in query:
            return {"getTests": {"results": [{"issueId": "target-test-id", "jira": {"key": key}}]}}
        return {"getTestPlans": {"results": [{"issueId": "target-plan-id", "jira": {"key": key}}]}}


class EmptyXray:
    async def query(self, query: str, variables: dict[str, object] | None = None) -> dict:
        if "getTests" in query:
            return {"getTests": {"results": []}}
        return {"getTestPlans": {"results": []}}


class ExternalExecutionTestXray:
    async def paginate(
        self,
        query: str,
        *,
        root_field: str,
        variables: dict[str, object] | None = None,
        **_: object,
    ):
        assert root_field == "getTests"
        assert variables == {"jql": 'key in ("LOY-1", "LOY-2")'}
        for key in ("LOY-1", "LOY-2"):
            yield {
                "issueId": f"target-{key}",
                "projectId": "external-project",
                "testType": {"name": "Manual"},
                "jira": {"key": key},
            }

    async def query(self, query: str, variables: dict[str, object] | None = None) -> dict:
        return {"getTestPlans": {"results": []}}


class ExternalTestPlanExecutionXray:
    async def paginate(
        self,
        query: str,
        *,
        root_field: str,
        variables: dict[str, object] | None = None,
        **_: object,
    ):
        assert root_field == "getTestExecutions"
        assert variables == {"jql": 'key in ("CST-2405", "CST-2406")'}
        for key in ("CST-2405", "CST-2406"):
            yield {
                "issueId": f"target-{key}",
                "jira": {"key": key},
            }

    async def query(self, query: str, variables: dict[str, object] | None = None) -> dict:
        return {"getTestPlans": {"results": []}}


class TestPlanExecutionXray:
    async def paginate(
        self,
        query: str,
        *,
        root_field: str,
        variables: dict[str, object] | None = None,
        **_: object,
    ):
        assert root_field == "getTestPlans"
        yield {
            "issueId": "plan-10",
            "jira": {"key": "ABC-10"},
            "tests": {"results": [_entry("ABC-1")]},
            "testExecutions": {"results": [_entry("ABC-20"), _entry("ABC-21")]},
        }


class TestRunStatusXray:
    async def query(self, query: str, variables: dict[str, object] | None = None) -> dict:
        assert variables == {"testExecIssueIds": ["execution-20"], "limit": 100, "start": 0}
        return {
            "getTestRuns": {
                "total": 1,
                "results": [
                    {
                        "id": "run-1",
                        "status": {"name": "PASSED"},
                        "test": _entry("ABC-1"),
                        "testExecution": _entry("ABC-20"),
                    }
                ],
            }
        }


def _entry(key: str) -> dict[str, Any]:
    return {"issueId": "10001", "jira": {"key": key}}


def test_jira_key_reads_nested_key() -> None:
    assert _jira_key(_entry("LOY-1")) == "LOY-1"


def test_jira_key_tolerates_null_entry() -> None:
    assert _jira_key(None) is None


def test_jira_key_tolerates_null_jira_object() -> None:
    assert _jira_key({"issueId": "10001", "jira": None}) is None


def test_nested_test_keys_skips_null_entries() -> None:
    execution = {"tests": {"results": [_entry("LOY-2"), None, _entry("LOY-1")]}}

    assert _nested_test_keys(execution) == ["LOY-1", "LOY-2"]


def test_nested_test_keys_tolerates_null_connection() -> None:
    assert _nested_test_keys({"tests": None}) == []


def test_nested_test_keys_tolerates_null_results() -> None:
    assert _nested_test_keys({"tests": {"results": None}}) == []


def test_nested_test_keys_tolerates_missing_connection() -> None:
    assert _nested_test_keys({}) == []


def test_connection_keys_skips_null_entries() -> None:
    test = {"preconditions": {"results": [None, _entry("LOY-9")]}}

    assert _connection_keys(test, "preconditions") == ["LOY-9"]


async def test_discover_test_plans_reads_linked_test_executions() -> None:
    plans = await SourceDiscovery(FakeJira(), TestPlanExecutionXray()).discover_test_plans("ABC")

    assert plans["ABC-10"].executions == ["ABC-20", "ABC-21"]


async def test_discover_test_runs_reads_status_by_execution_and_test() -> None:
    runs = await SourceDiscovery(FakeJira(), TestRunStatusXray()).discover_test_runs(
        {"ABC-20": TestExecution(jira_key="ABC-20", xray_id="execution-20")}
    )

    assert runs["ABC-20:ABC-1"].id == "run-1"
    assert runs["ABC-20:ABC-1"].status == "PASSED"


async def test_enrich_referenced_containers_adds_cross_project_test_plans() -> None:
    reference = ProjectSnapshot(
        project_key="SUP",
        tests={
            "SUP-1": XrayTest(
                jira_key="SUP-1",
                test_plans=["ZSD-4764"],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="SUP",
        tests={"SUP-1": XrayTest(jira_key="SUP-1")},
    )

    await SourceDiscovery(FakeJira(), FakeXray()).enrich_referenced_containers(target, reference)

    assert target.test_plans["ZSD-4764"].xray_id == "target-plan-id"


async def test_enrich_referenced_containers_adds_cross_project_execution_tests() -> None:
    reference = ProjectSnapshot(
        project_key="CON",
        executions={
            "CON-10": TestExecution(
                jira_key="CON-10",
                tests=["CON-1", "LOY-1", "LOY-2"],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="CON",
        tests={"CON-1": XrayTest(jira_key="CON-1", xray_id="target-CON-1")},
    )

    await SourceDiscovery(FakeJira(), ExternalExecutionTestXray()).enrich_referenced_containers(
        target, reference
    )

    assert target.tests["LOY-1"].xray_id == "target-LOY-1"
    assert target.tests["LOY-2"].xray_id == "target-LOY-2"


async def test_enrich_referenced_containers_adds_cross_project_test_plan_executions() -> None:
    reference = ProjectSnapshot(
        project_key="LOY",
        test_plans={
            "LOY-10": TestPlan(
                jira_key="LOY-10",
                executions=["LOY-20", "CST-2405", "CST-2406"],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="LOY",
        executions={"LOY-20": TestExecution(jira_key="LOY-20", xray_id="target-LOY-20")},
    )

    await SourceDiscovery(FakeJira(), ExternalTestPlanExecutionXray()).enrich_referenced_containers(
        target, reference
    )

    assert target.executions["CST-2405"].xray_id == "target-CST-2405"
    assert target.executions["CST-2406"].xray_id == "target-CST-2406"


async def test_enrich_referenced_containers_skips_missing_external_project_plans() -> None:
    reference = ProjectSnapshot(
        project_key="CON",
        tests={
            "CON-1": XrayTest(
                jira_key="CON-1",
                test_plans=["CST-2570"],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="CON",
        tests={"CON-1": XrayTest(jira_key="CON-1")},
    )

    await SourceDiscovery(MissingExternalJira(), EmptyXray()).enrich_referenced_containers(
        target, reference
    )

    assert target.test_plans == {}
