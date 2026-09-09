from __future__ import annotations

from pathlib import Path

from xray_sync.planning.operation import SyncOperation, SyncPlan
from xray_sync.planning.planner import (
    OP_ADD_TEST_EXECUTIONS_TO_TEST_PLAN,
    OP_ADD_TEST_STEP,
    OP_UPDATE_TEST_RUN_STATUS,
)
from xray_sync.sync.executor import ApplyProgressEvent, PlanExecutor


class FakeGraphQL:
    def __init__(self) -> None:
        self.mutations: list[tuple[str, dict]] = []

    async def query(self, query: str, variables: dict | None = None) -> dict:
        return {"getTest": {"steps": []}}

    async def mutate(self, mutation: str, variables: dict | None = None) -> dict:
        self.mutations.append((mutation, variables or {}))
        return {"ok": True}


async def test_executor_records_checkpoint_after_operation(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan = SyncPlan(
        source_environment="source",
        target_environment="target",
        project_key="ABC",
        operations=[
            SyncOperation(
                operation_id="op-00001",
                action=OP_ADD_TEST_STEP,
                entity_type="TestStep",
                source_key="ABC-1",
                target_key="ABC-1",
                payload={
                    "target_issue_id": "10001",
                    "step_index": 0,
                    "step": {"action": "A", "result": "B"},
                },
            )
        ],
    )
    plan_path.write_text(plan.model_dump_json(), encoding="utf-8")
    fake = FakeGraphQL()

    checkpoint = await PlanExecutor(fake).apply(plan, plan_path=plan_path)

    assert checkpoint.completed == ["op-00001"]
    assert len(fake.mutations) == 1
    assert plan_path.with_suffix(".json.checkpoint.json").exists()


async def test_executor_skips_blank_add_step_operations(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan = SyncPlan(
        source_environment="source",
        target_environment="target",
        project_key="ABC",
        operations=[
            SyncOperation(
                operation_id="op-00001",
                action=OP_ADD_TEST_STEP,
                entity_type="TestStep",
                source_key="ABC-1",
                target_key="ABC-1",
                payload={
                    "target_issue_id": "10001",
                    "step_index": 0,
                    "step": {"action": "", "data": "", "result": ""},
                },
            )
        ],
    )
    fake = FakeGraphQL()

    checkpoint = await PlanExecutor(fake).apply(plan, plan_path=plan_path)

    assert checkpoint.completed == ["op-00001"]
    assert fake.mutations == []


async def test_executor_adds_test_executions_to_test_plan(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan = SyncPlan(
        source_environment="source",
        target_environment="target",
        project_key="ABC",
        operations=[
            SyncOperation(
                operation_id="op-00001",
                action=OP_ADD_TEST_EXECUTIONS_TO_TEST_PLAN,
                entity_type="TestPlan",
                source_key="ABC-10",
                target_key="ABC-10",
                payload={
                    "container_issue_id": "plan-10",
                    "target_test_execution_issue_ids": ["execution-20"],
                    "target_test_execution_keys": ["ABC-20"],
                },
            )
        ],
    )
    fake = FakeGraphQL()

    checkpoint = await PlanExecutor(fake).apply(plan, plan_path=plan_path)

    assert checkpoint.completed == ["op-00001"]
    assert len(fake.mutations) == 1
    mutation, variables = fake.mutations[0]
    assert "addTestExecutionsToTestPlan" in mutation
    assert variables == {
        "issueId": "plan-10",
        "testExecIssueIds": ["execution-20"],
    }


async def test_executor_updates_test_run_status(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan = SyncPlan(
        source_environment="source",
        target_environment="target",
        project_key="ABC",
        operations=[
            SyncOperation(
                operation_id="op-00001",
                action=OP_UPDATE_TEST_RUN_STATUS,
                entity_type="TestRun",
                source_key="ABC-20:ABC-1",
                target_key="ABC-20:ABC-1",
                payload={
                    "target_test_run_id": "run-1",
                    "status": "PASSED",
                    "current_status": "TO DO",
                },
            )
        ],
    )
    fake = FakeGraphQL()

    checkpoint = await PlanExecutor(fake).apply(plan, plan_path=plan_path)

    assert checkpoint.completed == ["op-00001"]
    mutation, variables = fake.mutations[0]
    assert "updateTestRunStatus" in mutation
    assert variables == {"id": "run-1", "status": "PASSED"}


async def test_executor_emits_progress_events(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan = SyncPlan(
        source_environment="source",
        target_environment="target",
        project_key="ABC",
        operations=[
            SyncOperation(
                operation_id="op-00001",
                action=OP_ADD_TEST_STEP,
                entity_type="TestStep",
                source_key="ABC-1",
                target_key="ABC-1",
                payload={
                    "target_issue_id": "10001",
                    "step_index": 0,
                    "step": {"action": "A", "result": "B"},
                },
            )
        ],
    )
    events: list[ApplyProgressEvent] = []

    await PlanExecutor(FakeGraphQL()).apply(plan, plan_path=plan_path, progress=events.append)

    assert [event.kind for event in events] == [
        "start",
        "operation_start",
        "operation_complete",
        "complete",
    ]
    assert events[-1].completed == 1
    assert events[-1].total == 1
