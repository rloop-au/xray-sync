from __future__ import annotations

import pytest

from xray_sync.exceptions import MappingError, PlanError
from xray_sync.model.execution import TestExecution
from xray_sync.model.precondition import Precondition
from xray_sync.model.snapshot import ProjectSnapshot
from xray_sync.model.test import TestStep, XrayTest
from xray_sync.model.test_plan import TestPlan
from xray_sync.model.test_run import TestRun
from xray_sync.planning.planner import (
    OP_ADD_TEST_EXECUTIONS_TO_TEST_PLAN,
    OP_ADD_TEST_STEP,
    OP_ADD_TESTS_TO_PRECONDITION,
    OP_ADD_TESTS_TO_TEST_EXECUTION,
    OP_UPDATE_TEST_RUN_STATUS,
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


def test_planner_ignores_blank_manual_source_steps() -> None:
    source = ProjectSnapshot(
        project_key="ABC",
        tests={
            "ABC-1": XrayTest(
                jira_key="ABC-1",
                xray_id="src-1",
                test_type="Manual",
                steps=[
                    TestStep(action="", data="", expected_result=""),
                    TestStep(action="Do the thing", expected_result="It is done"),
                ],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="tgt-1", test_type="Manual")},
    )

    plan = Planner().build_plan(
        source_environment="prod",
        target_environment="sandbox",
        source=source,
        target=target,
    )

    assert [op.action for op in plan.operations] == [OP_ADD_TEST_STEP]
    assert plan.operations[0].payload["step"] == {
        "action": "Do the thing",
        "result": "It is done",
    }


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
        preconditions={"ABC-10": Precondition(jira_key="ABC-10", xray_id="precondition-10")},
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


def test_planner_skips_missing_external_project_relationship_container() -> None:
    source = ProjectSnapshot(
        project_key="ABC",
        tests={
            "ABC-1": XrayTest(
                jira_key="ABC-1",
                xray_id="src-1",
                test_type="Manual",
                test_plans=["EXT-10"],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="tgt-1", test_type="Manual")},
    )

    plan = Planner().build_plan(
        source_environment="prod",
        target_environment="sandbox",
        source=source,
        target=target,
    )

    assert plan.operations == []


def test_planner_treats_migrated_target_container_key_as_existing_relationship() -> None:
    source = ProjectSnapshot(
        project_key="LOY",
        tests={
            "LOY-3671": XrayTest(
                jira_key="LOY-3671",
                xray_id="src-test-1",
                test_type="Manual",
                test_plans=["LOY-3667"],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="LOY",
        tests={
            "LOY-3671": XrayTest(
                jira_key="LOY-3671",
                xray_id="target-test-1",
                test_type="Manual",
                test_plans=["ZLOYTPLATS-213"],
            )
        },
        test_plans={
            "LOY-3667": TestPlan(
                jira_key="ZLOYTPLATS-213",
                xray_id="target-plan-1",
                tests=["LOY-3671"],
            )
        },
    )

    plan = Planner().build_plan(
        source_environment="prod",
        target_environment="sandbox",
        source=source,
        target=target,
    )

    assert plan.operations == []


def test_planner_fails_for_missing_same_project_relationship_container() -> None:
    source = ProjectSnapshot(
        project_key="ABC",
        tests={
            "ABC-1": XrayTest(
                jira_key="ABC-1",
                xray_id="src-1",
                test_type="Manual",
                test_plans=["ABC-10"],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="tgt-1", test_type="Manual")},
    )

    with pytest.raises(MappingError):
        Planner().build_plan(
            source_environment="prod",
            target_environment="sandbox",
            source=source,
            target=target,
        )


def test_planner_adds_missing_test_execution_membership() -> None:
    source = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="src-test-1")},
        executions={
            "ABC-20": TestExecution(
                jira_key="ABC-20",
                xray_id="src-execution-20",
                tests=["ABC-1"],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="target-test-1")},
        executions={
            "ABC-20": TestExecution(
                jira_key="ABC-20",
                xray_id="target-execution-20",
                tests=[],
            )
        },
    )

    plan = Planner().build_plan(
        source_environment="prod",
        target_environment="sandbox",
        source=source,
        target=target,
    )

    assert [op.action for op in plan.operations] == [OP_ADD_TESTS_TO_TEST_EXECUTION]
    assert plan.operations[0].payload["container_issue_id"] == "target-execution-20"
    assert plan.operations[0].payload["target_test_issue_ids"] == ["target-test-1"]


def test_planner_adds_missing_test_execution_to_test_plan_membership() -> None:
    source = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="src-test-1")},
        test_plans={
            "ABC-10": TestPlan(
                jira_key="ABC-10",
                xray_id="source-plan-10",
                executions=["ABC-20"],
            )
        },
        executions={
            "ABC-20": TestExecution(
                jira_key="ABC-20",
                xray_id="source-execution-20",
                tests=["ABC-1"],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="target-test-1")},
        test_plans={
            "ABC-10": TestPlan(
                jira_key="ABC-10",
                xray_id="target-plan-10",
                executions=[],
            )
        },
        executions={
            "ABC-20": TestExecution(
                jira_key="ABC-20",
                xray_id="target-execution-20",
                tests=["ABC-1"],
            )
        },
    )

    plan = Planner().build_plan(
        source_environment="prod",
        target_environment="sandbox",
        source=source,
        target=target,
    )

    assert [op.action for op in plan.operations] == [OP_ADD_TEST_EXECUTIONS_TO_TEST_PLAN]
    assert plan.operations[0].payload["container_issue_id"] == "target-plan-10"
    assert plan.operations[0].payload["target_test_execution_issue_ids"] == [
        "target-execution-20"
    ]


def test_planner_fails_for_missing_test_plan_execution() -> None:
    source = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="src-test-1")},
        test_plans={
            "ABC-10": TestPlan(
                jira_key="ABC-10",
                xray_id="source-plan-10",
                executions=["ABC-20"],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="target-test-1")},
        test_plans={
            "ABC-10": TestPlan(
                jira_key="ABC-10",
                xray_id="target-plan-10",
                executions=[],
            )
        },
    )

    with pytest.raises(MappingError):
        Planner().build_plan(
            source_environment="prod",
            target_environment="sandbox",
            source=source,
            target=target,
        )


def test_planner_updates_existing_test_run_status() -> None:
    source = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="src-test-1")},
        test_runs={
            "ABC-20:ABC-1": TestRun(
                id="source-run-1",
                test_key="ABC-1",
                execution_key="ABC-20",
                status="PASSED",
            )
        },
    )
    target = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="target-test-1")},
        test_runs={
            "ABC-20:ABC-1": TestRun(
                id="target-run-1",
                test_key="ABC-1",
                execution_key="ABC-20",
                status="TO DO",
            )
        },
    )

    plan = Planner().build_plan(
        source_environment="prod",
        target_environment="sandbox",
        source=source,
        target=target,
    )

    assert [op.action for op in plan.operations] == [OP_UPDATE_TEST_RUN_STATUS]
    assert plan.operations[0].payload["target_test_run_id"] == "target-run-1"
    assert plan.operations[0].payload["status"] == "PASSED"
    assert plan.operations[0].payload["current_status"] == "TO DO"


def test_planner_fails_for_missing_external_project_execution_test() -> None:
    source = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="src-test-1")},
        executions={
            "ABC-20": TestExecution(
                jira_key="ABC-20",
                xray_id="src-execution-20",
                tests=["EXT-1"],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="target-test-1")},
        executions={
            "ABC-20": TestExecution(
                jira_key="ABC-20",
                xray_id="target-execution-20",
                tests=[],
            )
        },
    )

    with pytest.raises(MappingError):
        Planner().build_plan(
            source_environment="prod",
            target_environment="sandbox",
            source=source,
            target=target,
        )


def test_planner_fails_for_missing_same_project_execution_test() -> None:
    source = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="src-test-1")},
        executions={
            "ABC-20": TestExecution(
                jira_key="ABC-20",
                xray_id="src-execution-20",
                tests=["ABC-2"],
            )
        },
    )
    target = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", xray_id="target-test-1")},
        executions={
            "ABC-20": TestExecution(
                jira_key="ABC-20",
                xray_id="target-execution-20",
                tests=[],
            )
        },
    )

    with pytest.raises(MappingError):
        Planner().build_plan(
            source_environment="prod",
            target_environment="sandbox",
            source=source,
            target=target,
        )


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
