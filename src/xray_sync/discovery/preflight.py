from __future__ import annotations

from collections.abc import Sequence

from xray_sync.model.snapshot import ProjectSnapshot

TEAM_MANAGED_NOTE = (
    "Team-managed projects scope their work item types to the project itself, so the Xray "
    "types (Test, Precondition, Test Set, Test Plan, Test Execution) must be configured in "
    "each team-managed project separately - they are not inherited from a shared scheme."
)

EMPTY_PROJECT_NOTE = (
    "Configure the Xray work item types for that project in Jira before running plan or "
    "apply, otherwise planning fails with every Test reported as missing."
)


def xray_entity_count(snapshot: ProjectSnapshot) -> int:
    return (
        len(snapshot.tests)
        + len(snapshot.preconditions)
        + len(snapshot.test_sets)
        + len(snapshot.test_plans)
        + len(snapshot.executions)
    )


def project_style_warnings(
    snapshots: Sequence[tuple[str, ProjectSnapshot]],
) -> list[str]:
    """Warn when any environment's project is team-managed.

    Discovery itself is project-style agnostic, but team-managed projects are the common
    cause of an environment reporting no Xray entities at all, which later surfaces as a
    wall of missing Jira keys during plan. Reporting it here names the actual cause.
    """
    team_managed = [
        (environment, snapshot)
        for environment, snapshot in snapshots
        if snapshot.project is not None and snapshot.project.is_team_managed
    ]
    if not team_managed:
        return []

    labelled = ", ".join(
        f"{environment} ({snapshot.project_key})" for environment, snapshot in team_managed
    )
    warnings = [f"Team-managed project detected in: {labelled}.", TEAM_MANAGED_NOTE]

    empty = [
        f"{environment} ({snapshot.project_key})"
        for environment, snapshot in team_managed
        if xray_entity_count(snapshot) == 0
    ]
    if empty:
        warnings.append(
            f"No Xray entities were discovered in: {', '.join(empty)}. {EMPTY_PROJECT_NOTE}"
        )
    return warnings
