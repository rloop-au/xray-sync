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
        ("source", _snapshot("ABC", style="classic", simplified=False, tests=3)),
        ("target", _snapshot("ABC", style="classic", simplified=False, tests=3)),
    ]

    assert project_style_warnings(snapshots) == []


def test_simplified_flag_marks_project_as_team_managed() -> None:
    warnings = project_style_warnings([("source", _snapshot("ABC", simplified=True, tests=3))])

    assert warnings
    assert "source (ABC)" in warnings[0]


def test_next_gen_style_marks_project_as_team_managed() -> None:
    warnings = project_style_warnings([("source", _snapshot("ABC", style="next-gen", tests=3))])

    assert warnings
    assert "source (ABC)" in warnings[0]


def test_simplified_flag_wins_over_style() -> None:
    snapshot = _snapshot("ABC", style="next-gen", simplified=False, tests=3)

    assert project_style_warnings([("source", snapshot)]) == []


def test_team_managed_environment_without_xray_entities_is_called_out() -> None:
    snapshots = [
        ("source", _snapshot("ABC", simplified=True, tests=3)),
        ("target", _snapshot("ABC", simplified=True, tests=0)),
    ]

    warnings = project_style_warnings(snapshots)

    assert "source (ABC), target (ABC)" in warnings[0]
    assert "No Xray entities were discovered in: target (ABC)." in warnings[-1]
    assert "source" not in warnings[-1]


def test_unknown_style_is_not_treated_as_team_managed() -> None:
    assert project_style_warnings([("source", _snapshot("ABC"))]) == []


def test_missing_project_metadata_is_tolerated() -> None:
    assert project_style_warnings([("source", ProjectSnapshot(project_key="ABC"))]) == []
