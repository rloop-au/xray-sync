from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from xray_sync.api.xray_graphql import XrayGraphQLClient
from xray_sync.exceptions import ApiError, PlanError, RateLimitError
from xray_sync.planning.operation import SyncOperation, SyncPlan
from xray_sync.planning.planner import (
    OP_ADD_TEST_STEP,
    OP_ADD_TESTS_TO_FOLDER,
    OP_ADD_TESTS_TO_PRECONDITION,
    OP_ADD_TESTS_TO_TEST_EXECUTION,
    OP_ADD_TESTS_TO_TEST_PLAN,
    OP_ADD_TESTS_TO_TEST_SET,
    OP_UPDATE_TEST_STEP,
)
from xray_sync.storage.checkpoint import Checkpoint
from xray_sync.storage.filesystem import write_json


@dataclass(frozen=True)
class ApplyProgressEvent:
    kind: str
    completed: int
    total: int
    operation: SyncOperation | None = None
    message: str | None = None
    sleep_seconds: float | None = None


ApplyProgressCallback = Callable[[ApplyProgressEvent], None]


class PlanExecutor:
    def __init__(self, xray: XrayGraphQLClient) -> None:
        self.xray = xray

    async def apply(
        self,
        plan: SyncPlan,
        *,
        plan_path: Path,
        checkpoint_path: Path | None = None,
        progress: ApplyProgressCallback | None = None,
    ) -> Checkpoint:
        checkpoint_file = checkpoint_path or plan_path.with_suffix(
            plan_path.suffix + ".checkpoint.json"
        )
        checkpoint = _read_checkpoint(checkpoint_file, plan_path)
        completed = set(checkpoint.completed)
        total = len(plan.operations)
        _emit(progress, "start", len(completed), total)
        for operation in plan.operations:
            if operation.operation_id in completed:
                continue
            _emit(progress, "operation_start", len(completed), total, operation=operation)
            await self._apply_with_rate_limit_retry(
                operation, checkpoint, checkpoint_file, len(completed), total, progress
            )
            checkpoint.completed.append(operation.operation_id)
            checkpoint.failed = None
            write_json(checkpoint_file, checkpoint.model_dump())
            completed.add(operation.operation_id)
            _emit(progress, "operation_complete", len(completed), total, operation=operation)
        _emit(progress, "complete", len(completed), total)
        return checkpoint

    async def _apply_with_rate_limit_retry(
        self,
        operation: SyncOperation,
        checkpoint: Checkpoint,
        checkpoint_file: Path,
        completed: int,
        total: int,
        progress: ApplyProgressCallback | None,
    ) -> None:
        attempts = 0
        while True:
            try:
                await self._apply_operation(operation)
                return
            except RateLimitError as exc:
                attempts += 1
                checkpoint.failed = operation.operation_id
                write_json(checkpoint_file, checkpoint.model_dump())
                if attempts > 20:
                    raise
                sleep_seconds = _rate_limit_sleep_seconds(exc, attempts)
                _emit(
                    progress,
                    "rate_limit",
                    completed,
                    total,
                    operation=operation,
                    message=f"Rate limited; retrying in {sleep_seconds:.0f}s",
                    sleep_seconds=sleep_seconds,
                )
                await asyncio.sleep(sleep_seconds)

    async def _apply_operation(self, operation: SyncOperation) -> None:
        if operation.action == OP_ADD_TEST_STEP:
            await self._add_test_step(operation)
        elif operation.action == OP_UPDATE_TEST_STEP:
            await self._update_test_step(operation)
        elif operation.action == OP_ADD_TESTS_TO_PRECONDITION:
            await self._add_tests_to_precondition(operation)
        elif operation.action == OP_ADD_TESTS_TO_TEST_SET:
            await self._add_tests_to_test_set(operation)
        elif operation.action == OP_ADD_TESTS_TO_TEST_PLAN:
            await self._add_tests_to_test_plan(operation)
        elif operation.action == OP_ADD_TESTS_TO_TEST_EXECUTION:
            await self._add_tests_to_test_execution(operation)
        elif operation.action == OP_ADD_TESTS_TO_FOLDER:
            await self._add_tests_to_folder(operation)
        else:
            raise PlanError(
                "Plan contains an operation that this version cannot apply",
                detail={"operation_id": operation.operation_id, "action": operation.action},
            )

    async def _add_test_step(self, operation: SyncOperation) -> None:
        issue_id = _required_payload(operation, "target_issue_id")
        step = _required_payload(operation, "step")
        step_index = int(operation.payload.get("step_index", 0))
        if await self._test_step_already_present(
            cast(str, issue_id), step_index, cast(dict[str, object], step)
        ):
            return
        await self.xray.mutate(
            """
            mutation AddTestStep($issueId: String!, $step: CreateStepInput!) {
              addTestStep(issueId: $issueId, step: $step) {
                id
                action
                data
                result
              }
            }
            """,
            {"issueId": issue_id, "step": step},
        )

    async def _update_test_step(self, operation: SyncOperation) -> None:
        step_id = _required_payload(operation, "target_step_id")
        step = _required_payload(operation, "step")
        await self.xray.mutate(
            """
            mutation UpdateTestStep($stepId: String!, $step: UpdateStepInput!) {
              updateTestStep(stepId: $stepId, step: $step) {
                warnings
              }
            }
            """,
            {"stepId": step_id, "step": step},
        )

    async def _add_tests_to_precondition(self, operation: SyncOperation) -> None:
        await self._relationship_mutation(
            operation,
            """
            mutation AddTestsToPrecondition($issueId: String!, $testIssueIds: [String]!) {
              addTestsToPrecondition(issueId: $issueId, testIssueIds: $testIssueIds) {
                addedTests
                warning
              }
            }
            """,
            "addTestsToPrecondition",
        )

    async def _add_tests_to_test_set(self, operation: SyncOperation) -> None:
        await self._relationship_mutation(
            operation,
            """
            mutation AddTestsToTestSet($issueId: String!, $testIssueIds: [String]!) {
              addTestsToTestSet(issueId: $issueId, testIssueIds: $testIssueIds) {
                addedTests
                warning
              }
            }
            """,
            "addTestsToTestSet",
        )

    async def _add_tests_to_test_plan(self, operation: SyncOperation) -> None:
        await self._relationship_mutation(
            operation,
            """
            mutation AddTestsToTestPlan($issueId: String!, $testIssueIds: [String]!) {
              addTestsToTestPlan(issueId: $issueId, testIssueIds: $testIssueIds) {
                addedTests
                warning
              }
            }
            """,
            "addTestsToTestPlan",
        )

    async def _add_tests_to_test_execution(self, operation: SyncOperation) -> None:
        await self._relationship_mutation(
            operation,
            """
            mutation AddTestsToTestExecution($issueId: String!, $testIssueIds: [String]!) {
              addTestsToTestExecution(issueId: $issueId, testIssueIds: $testIssueIds) {
                addedTests
                warning
              }
            }
            """,
            "addTestsToTestExecution",
        )

    async def _add_tests_to_folder(self, operation: SyncOperation) -> None:
        variables = {
            "projectId": operation.payload.get("project_id"),
            "path": _required_payload(operation, "path"),
            "testIssueIds": _required_payload(operation, "target_test_issue_ids"),
        }
        try:
            await self.xray.mutate(
                """
                mutation AddTestsToFolder(
                  $projectId: String,
                  $path: String!,
                  $testIssueIds: [String]!
                ) {
                  addTestsToFolder(
                    projectId: $projectId,
                    path: $path,
                    testIssueIds: $testIssueIds
                  ) {
                    folder { path testsCount }
                    warnings
                  }
                }
                """,
                variables,
            )
        except ApiError as exc:
            if "folder with path" not in str(exc.detail):
                raise
            await self.xray.mutate(
                """
                mutation CreateFolder(
                  $projectId: String,
                  $path: String!,
                  $testIssueIds: [String]
                ) {
                  createFolder(
                    projectId: $projectId,
                    path: $path,
                    testIssueIds: $testIssueIds
                  ) {
                    folder { path testsCount }
                    warnings
                  }
                }
                """,
                variables,
            )

    async def _relationship_mutation(
        self, operation: SyncOperation, mutation: str, _result_field: str
    ) -> None:
        await self.xray.mutate(
            mutation,
            {
                "issueId": _required_payload(operation, "container_issue_id"),
                "testIssueIds": _required_payload(operation, "target_test_issue_ids"),
            },
        )

    async def _test_step_already_present(
        self, issue_id: str, step_index: int, desired_step: dict[str, object]
    ) -> bool:
        data = await self.xray.query(
            """
            query GetTestSteps($issueId: String!) {
              getTest(issueId: $issueId) {
                steps { action data result }
              }
            }
            """,
            {"issueId": issue_id},
        )
        steps = ((data.get("getTest") or {}).get("steps") or [])
        if step_index >= len(steps):
            return False
        current = steps[step_index]
        return {
            "action": current.get("action") or "",
            "data": current.get("data") or "",
            "result": current.get("result") or "",
        } == {
            "action": desired_step.get("action") or "",
            "data": desired_step.get("data") or "",
            "result": desired_step.get("result") or "",
        }


def _required_payload(operation: SyncOperation, key: str) -> Any:
    try:
        return operation.payload[key]
    except KeyError as exc:
        raise PlanError(
            "Plan operation payload is missing a required value",
            detail={"operation_id": operation.operation_id, "key": key},
        ) from exc


def _rate_limit_sleep_seconds(exc: RateLimitError, attempts: int) -> float:
    retry_after = exc.detail.get("retry_after")
    if isinstance(retry_after, str) and retry_after.isdigit():
        return float(retry_after)
    return min(120.0, 30.0 * attempts)


def _read_checkpoint(path: Path, plan_path: Path) -> Checkpoint:
    if path.exists():
        return Checkpoint.model_validate_json(path.read_text(encoding="utf-8"))
    return Checkpoint(plan=str(plan_path), completed=[])


def _emit(
    progress: ApplyProgressCallback | None,
    kind: str,
    completed: int,
    total: int,
    *,
    operation: SyncOperation | None = None,
    message: str | None = None,
    sleep_seconds: float | None = None,
) -> None:
    if progress is None:
        return
    progress(
        ApplyProgressEvent(
            kind=kind,
            completed=completed,
            total=total,
            operation=operation,
            message=message,
            sleep_seconds=sleep_seconds,
        )
    )
