from __future__ import annotations

import pytest

from xray_sync.exceptions import MappingError, PlanError
from xray_sync.model.precondition import Precondition
from xray_sync.model.snapshot import ProjectSnapshot
from xray_sync.model.test import TestStep, XrayTest
from xray_sync.planning.planner import (
    OP_ADD_TEST_STEP,
    OP_ADD_TESTS_TO_PRECONDITION,
    OP_UPDATE_TEST_STEP,
    Planner,
)


def test_planner_adds_and_updates_manual_steps() -> None:
    source = ProjectSnapshot(
        project_key="ABC",
        tests={
            "ABC-1": XrayTest(
                jira_key="ABC-1",
                xray_id="src-1",
                test_type="Manual",
                steps=[
                    TestStep(action="A", expected_result="B"),
                    TestStep(action="C", data="D", expected_result="E"),
                ],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="ABC",
        tests={
            "ABC-1": XrayTest(
                jira_key="ABC-1",
                xray_id="tgt-1",
                test_type="Manual",
                steps=[TestStep(id="step-1", action="old", expected_result="old")],
            )
        },
    )

    plan = Planner().build_plan(
        source_environment="prod",
        target_environment="sandbox",
        source=source,
        target=target,
    )

    assert [op.action for op in plan.operations] == [OP_UPDATE_TEST_STEP, OP_ADD_TEST_STEP]
    assert plan.operations[0].payload["target_step_id"] == "step-1"
    assert plan.operations[1].payload["target_issue_id"] == "tgt-1"


def test_planner_adds_missing_precondition_relationship() -> None:
    source = ProjectSnapshot(
        project_key="ABC",
        tests={
            "ABC-1": XrayTest(
                jira_key="ABC-1",
                xray_id="src-1",
                test_type="Manual",
                preconditions=["ABC-10"],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="tgt-1", test_type="Manual")},
        preconditions={
            "ABC-10": Precondition(jira_key="ABC-10", xray_id="precondition-10")
        },
    )

    plan = Planner().build_plan(
        source_environment="prod",
        target_environment="sandbox",
        source=source,
        target=target,
    )

    assert [op.action for op in plan.operations] == [OP_ADD_TESTS_TO_PRECONDITION]
    assert plan.operations[0].payload["container_issue_id"] == "precondition-10"
    assert plan.operations[0].payload["target_test_issue_ids"] == ["tgt-1"]


def test_planner_fails_if_target_test_missing() -> None:
    source = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="src-1")},
    )
    target = ProjectSnapshot(project_key="ABC")

    with pytest.raises(MappingError):
        Planner().build_plan(
            source_environment="prod",
            target_environment="sandbox",
            source=source,
            target=target,
        )


def test_planner_refuses_extra_target_steps_because_deletion_is_unsupported() -> None:
    source = ProjectSnapshot(
        project_key="ABC",
        tests={
            "ABC-1": XrayTest(
                jira_key="ABC-1",
                xray_id="src-1",
                test_type="Manual",
                steps=[TestStep(action="A")],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="ABC",
        tests={
            "ABC-1": XrayTest(
                jira_key="ABC-1",
                xray_id="tgt-1",
                test_type="Manual",
                steps=[TestStep(id="1", action="A"), TestStep(id="2", action="B")],
            )
        },
    )

    with pytest.raises(PlanError):
        Planner().build_plan(
            source_environment="prod",
            target_environment="sandbox",
            source=source,
            target=target,
        )
