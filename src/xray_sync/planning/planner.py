from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from xray_sync.exceptions import MappingError, PlanError
from xray_sync.model.execution import TestExecution
from xray_sync.model.snapshot import ProjectSnapshot
from xray_sync.model.test import TestStep, XrayTest
from xray_sync.planning.operation import SyncOperation, SyncPlan

OP_UPDATE_TEST_STEP = "UPDATE_TEST_STEP"
OP_ADD_TEST_STEP = "ADD_TEST_STEP"
OP_ADD_TESTS_TO_PRECONDITION = "ADD_TESTS_TO_PRECONDITION"
OP_ADD_TESTS_TO_TEST_SET = "ADD_TESTS_TO_TEST_SET"
OP_ADD_TESTS_TO_TEST_PLAN = "ADD_TESTS_TO_TEST_PLAN"
OP_ADD_TESTS_TO_TEST_EXECUTION = "ADD_TESTS_TO_TEST_EXECUTION"
OP_ADD_TESTS_TO_FOLDER = "ADD_TESTS_TO_FOLDER"


class Planner:
    def empty_read_only_plan(
        self, *, source_environment: str, target_environment: str, project_key: str
    ) -> SyncPlan:
        return SyncPlan(
            source_environment=source_environment,
            target_environment=target_environment,
            project_key=project_key,
            operations=[],
        )

    def build_plan(
        self,
        *,
        source_environment: str,
        target_environment: str,
        source: ProjectSnapshot,
        target: ProjectSnapshot,
    ) -> SyncPlan:
        if source.project_key != target.project_key:
            raise PlanError(
                "Source and target snapshots are for different projects",
                detail={"source": source.project_key, "target": target.project_key},
            )

        plan = SyncPlan(
            source_environment=source_environment,
            target_environment=target_environment,
            project_key=source.project_key,
        )
        missing = sorted(key for key in source.tests if key not in target.tests)
        if missing:
            raise MappingError(
                "Target is missing Jira/Xray Test issues copied from source",
                detail={"missing_tests": missing},
            )

        for key in sorted(source.tests):
            self._plan_test_definition(plan, source.tests[key], target.tests[key])
            self._plan_test_relationships(plan, source.tests[key], target)
        self._plan_execution_memberships(plan, source, target)
        return plan

    def _plan_test_definition(
        self, plan: SyncPlan, source_test: XrayTest, target_test: XrayTest
    ) -> None:
        if _step_values(source_test.steps) == _step_values(target_test.steps):
            return
        if source_test.test_type and source_test.test_type.lower() != "manual":
            plan.operations.append(
                _operation(
                    plan,
                    "UNSUPPORTED_TEST_DEFINITION_DIFF",
                    "Test",
                    source_key=source_test.jira_key,
                    target_key=target_test.jira_key,
                    payload={
                        "reason": "Only Manual test step sync is implemented for apply",
                        "source_test_type": source_test.test_type,
                        "target_test_type": target_test.test_type,
                    },
                )
            )
            return
        if len(target_test.steps) > len(source_test.steps):
            raise PlanError(
                "Target has extra test steps; deletion/replacement is not supported",
                detail={"test": source_test.jira_key},
            )

        for index, source_step in enumerate(source_test.steps):
            if index < len(target_test.steps):
                target_step = target_test.steps[index]
                if _step_value(source_step) != _step_value(target_step):
                    if not target_step.id:
                        raise PlanError(
                            "Cannot update target step without a target step id",
                            detail={"test": target_test.jira_key, "step_index": index},
                        )
                    plan.operations.append(
                        _operation(
                            plan,
                            OP_UPDATE_TEST_STEP,
                            "TestStep",
                            source_key=source_test.jira_key,
                            target_key=target_test.jira_key,
                            payload={
                                "target_step_id": target_step.id,
                                "step": _step_payload(source_step),
                                "step_index": index,
                            },
                        )
                    )
            else:
                if not target_test.xray_id:
                    raise PlanError(
                        "Cannot add target step without a target Test issue id",
                        detail={"test": target_test.jira_key},
                    )
                plan.operations.append(
                    _operation(
                        plan,
                        OP_ADD_TEST_STEP,
                        "TestStep",
                        source_key=source_test.jira_key,
                        target_key=target_test.jira_key,
                        payload={
                            "target_issue_id": target_test.xray_id,
                            "step": _step_payload(source_step),
                            "step_index": index,
                        },
                    )
                )

    def _plan_test_relationships(
        self, plan: SyncPlan, source_test: XrayTest, target: ProjectSnapshot
    ) -> None:
        target_test = target.tests[source_test.jira_key]
        self._plan_relationship(
            plan,
            action=OP_ADD_TESTS_TO_PRECONDITION,
            container_type="Precondition",
            source_container_keys=source_test.preconditions,
            target_container_keys=target_test.preconditions,
            target_containers=target.preconditions,
            target_test=target_test,
        )
        self._plan_relationship(
            plan,
            action=OP_ADD_TESTS_TO_TEST_SET,
            container_type="TestSet",
            source_container_keys=source_test.test_sets,
            target_container_keys=target_test.test_sets,
            target_containers=target.test_sets,
            target_test=target_test,
        )
        self._plan_relationship(
            plan,
            action=OP_ADD_TESTS_TO_TEST_PLAN,
            container_type="TestPlan",
            source_container_keys=source_test.test_plans,
            target_container_keys=target_test.test_plans,
            target_containers=target.test_plans,
            target_test=target_test,
        )
        self._plan_relationship(
            plan,
            action=OP_ADD_TESTS_TO_TEST_EXECUTION,
            container_type="TestExecution",
            source_container_keys=source_test.test_executions,
            target_container_keys=target_test.test_executions,
            target_containers=target.executions,
            target_test=target_test,
        )

        if source_test.folder_path and source_test.folder_path != target_test.folder_path:
            if not target_test.xray_id:
                raise PlanError(
                    "Cannot move target test to folder without a target Test issue id",
                    detail={"test": target_test.jira_key},
                )
            plan.operations.append(
                _operation(
                    plan,
                    OP_ADD_TESTS_TO_FOLDER,
                    "RepositoryFolder",
                    source_key=source_test.jira_key,
                    target_key=target_test.jira_key,
                    payload={
                        "project_id": target_test.raw.get("projectId"),
                        "path": source_test.folder_path,
                        "target_test_issue_ids": [target_test.xray_id],
                    },
                )
            )

    def _plan_relationship(
        self,
        plan: SyncPlan,
        *,
        action: str,
        container_type: str,
        source_container_keys: Iterable[str],
        target_container_keys: Iterable[str],
        target_containers: dict[str, Any],
        target_test: XrayTest,
    ) -> None:
        missing_keys = sorted(set(source_container_keys) - set(target_container_keys))
        for container_key in missing_keys:
            container = target_containers.get(container_key)
            if not container or not container.xray_id:
                raise MappingError(
                    f"Target is missing required {container_type} issue",
                    detail={"missing": container_key, "for_test": target_test.jira_key},
                )
            if not target_test.xray_id:
                raise MappingError(
                    "Target Test is missing Xray/Jira issue id",
                    detail={"missing": target_test.jira_key},
                )
            plan.operations.append(
                _operation(
                    plan,
                    action,
                    container_type,
                    source_key=container_key,
                    target_key=container_key,
                    payload={
                        "container_issue_id": container.xray_id,
                        "target_test_issue_ids": [target_test.xray_id],
                        "target_test_keys": [target_test.jira_key],
                    },
                )
            )

    def _plan_execution_memberships(
        self, plan: SyncPlan, source: ProjectSnapshot, target: ProjectSnapshot
    ) -> None:
        missing_executions = sorted(
            key for key in source.executions if key not in target.executions
        )
        if missing_executions:
            raise MappingError(
                "Target is missing Jira/Xray Test Execution issues copied from source",
                detail={"missing_test_executions": missing_executions},
            )

        for execution_key in sorted(source.executions):
            source_execution = source.executions[execution_key]
            target_execution = target.executions[execution_key]
            self._plan_execution_membership(
                plan,
                source_execution=source_execution,
                target_execution=target_execution,
                target=target,
            )

    def _plan_execution_membership(
        self,
        plan: SyncPlan,
        *,
        source_execution: TestExecution,
        target_execution: TestExecution,
        target: ProjectSnapshot,
    ) -> None:
        missing_test_keys = sorted(set(source_execution.tests) - set(target_execution.tests))
        for test_key in missing_test_keys:
            target_test = target.tests.get(test_key)
            if not target_test or not target_test.xray_id:
                raise MappingError(
                    "Target is missing required Test issue for Test Execution membership",
                    detail={"missing": test_key, "for_execution": target_execution.jira_key},
                )
            if not target_execution.xray_id:
                raise MappingError(
                    "Target Test Execution is missing Xray/Jira issue id",
                    detail={"missing": target_execution.jira_key},
                )
            plan.operations.append(
                _operation(
                    plan,
                    OP_ADD_TESTS_TO_TEST_EXECUTION,
                    "TestExecution",
                    source_key=source_execution.jira_key,
                    target_key=target_execution.jira_key,
                    payload={
                        "container_issue_id": target_execution.xray_id,
                        "target_test_issue_ids": [target_test.xray_id],
                        "target_test_keys": [target_test.jira_key],
                    },
                )
            )


def _operation(
    plan: SyncPlan,
    action: str,
    entity_type: str,
    *,
    source_key: str | None,
    target_key: str | None,
    payload: dict[str, Any],
) -> SyncOperation:
    return SyncOperation(
        operation_id=f"op-{len(plan.operations) + 1:05d}",
        action=action,
        entity_type=entity_type,
        source_key=source_key,
        target_key=target_key,
        payload=payload,
    )


def _step_values(steps: list[TestStep]) -> list[dict[str, str]]:
    return [_step_value(step) for step in steps]


def _step_value(step: TestStep) -> dict[str, str]:
    payload = _step_payload(step)
    return {
        "action": payload.get("action", ""),
        "data": payload.get("data", ""),
        "result": payload.get("result", ""),
    }


def _step_payload(step: TestStep) -> dict[str, str]:
    payload = {
        "action": step.action or "",
        "result": step.expected_result or "",
    }
    if step.data:
        payload["data"] = step.data
    return payload
