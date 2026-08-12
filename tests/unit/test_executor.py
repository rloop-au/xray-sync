from __future__ import annotations

from pathlib import Path

from xray_sync.planning.operation import SyncOperation, SyncPlan
from xray_sync.planning.planner import OP_ADD_TEST_STEP
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
        source_environment="prod",
        target_environment="sandbox",
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


async def test_executor_emits_progress_events(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan = SyncPlan(
        source_environment="prod",
        target_environment="sandbox",
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
