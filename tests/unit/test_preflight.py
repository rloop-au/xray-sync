from __future__ import annotations

from xray_sync.discovery.preflight import project_style_warnings
from xray_sync.model.jira import JiraProject
from xray_sync.model.snapshot import ProjectSnapshot
from xray_sync.model.test import XrayTest


def _snapshot(
    key: str, *, style: str | None = None, simplified: bool | None = None, tests: int = 0
) -> ProjectSnapshot:
    return ProjectSnapshot(
        project_key=key,
        project=JiraProject(id="10000", key=key, style=style, simplified=simplified),
        tests={f"{key}-{index}": XrayTest(jira_key=f"{key}-{index}") for index in range(tests)},
    )


def test_company_managed_projects_produce_no_warnings() -> None:
    snapshots = [
        ("prod", _snapshot("LOY", style="classic", simplified=False, tests=3)),
        ("sandbox", _snapshot("LOY", style="classic", simplified=False, tests=3)),
    ]

    assert project_style_warnings(snapshots) == []


def test_simplified_flag_marks_project_as_team_managed() -> None:
    warnings = project_style_warnings([("prod", _snapshot("LOY", simplified=True, tests=3))])

    assert warnings
    assert "prod (LOY)" in warnings[0]


def test_next_gen_style_marks_project_as_team_managed() -> None:
    warnings = project_style_warnings([("prod", _snapshot("LOY", style="next-gen", tests=3))])

    assert warnings
    assert "prod (LOY)" in warnings[0]


def test_simplified_flag_wins_over_style() -> None:
    snapshot = _snapshot("LOY", style="next-gen", simplified=False, tests=3)

    assert project_style_warnings([("prod", snapshot)]) == []


def test_team_managed_environment_without_xray_entities_is_called_out() -> None:
    snapshots = [
        ("prod", _snapshot("LOY", simplified=True, tests=3)),
        ("sandbox", _snapshot("LOY", simplified=True, tests=0)),
    ]

    warnings = project_style_warnings(snapshots)

    assert "prod (LOY), sandbox (LOY)" in warnings[0]
    assert "No Xray entities were discovered in: sandbox (LOY)." in warnings[-1]
    assert "prod" not in warnings[-1]


def test_unknown_style_is_not_treated_as_team_managed() -> None:
    assert project_style_warnings([("prod", _snapshot("LOY"))]) == []


def test_missing_project_metadata_is_tolerated() -> None:
    assert project_style_warnings([("prod", ProjectSnapshot(project_key="LOY"))]) == []
