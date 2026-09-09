from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from xray_sync import __version__
from xray_sync.api.jira import JiraClient
from xray_sync.api.xray_auth import XrayAuthClient
from xray_sync.api.xray_graphql import XrayGraphQLClient
from xray_sync.config import load_config
from xray_sync.diff.comparer import SnapshotComparer, SnapshotDiff
from xray_sync.discovery.preflight import project_style_warnings
from xray_sync.discovery.source import SourceDiscovery
from xray_sync.exceptions import XraySyncError
from xray_sync.export.exporter import SnapshotExporter
from xray_sync.logging import configure_logging
from xray_sync.model.snapshot import ProjectSnapshot
from xray_sync.planning.operation import SyncOperation, SyncPlan
from xray_sync.planning.planner import Planner
from xray_sync.planning.serialise import read_plan, write_plan
from xray_sync.storage.checkpoint import Checkpoint
from xray_sync.sync.executor import ApplyProgressCallback, ApplyProgressEvent, PlanExecutor

app = typer.Typer(no_args_is_help=True)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"xray-sync {__version__}")
        raise typer.Exit


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", help="Enable informational logs.")] = False,
    debug: Annotated[
        bool, typer.Option("--debug", help="Enable debug logs and tracebacks.")
    ] = False,
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    _ = version
    configure_logging(verbose=verbose, debug=debug)


@app.command()
def doctor(
    config: Annotated[
        Path | None,
        typer.Option("--config", exists=False, help="Path to xray-sync.yaml."),
    ] = None,
) -> None:
    """Validate local configuration without calling remote APIs."""
    try:
        app_config = load_config(config)
    except XraySyncError as exc:
        console.print(f"[red]Configuration error:[/] {exc}")
        raise typer.Exit(1) from exc

    table = Table(title="xray-sync doctor")
    table.add_column("Check")
    table.add_column("Result")
    table.add_row("Package", f"OK ({__version__})")
    table.add_row("Configuration", "OK")
    table.add_row("Environments", ", ".join(sorted(app_config.environments)))
    table.add_row("Mutation support", "Target-only apply via explicit plan")
    console.print(table)


@app.command()
def inspect(
    environment: Annotated[str, typer.Option("--environment", "-e")],
    project: Annotated[str, typer.Option("--project", "-p")],
    config: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Inspect a project and print discovered Xray entity counts."""
    snapshot = asyncio.run(_discover(environment=environment, project=project, config_path=config))
    table = Table(title=f"{environment}:{project}")
    table.add_column("Entity")
    table.add_column("Count", justify="right")
    table.add_row("Project style", snapshot.project.style_label if snapshot.project else "unknown")
    table.add_row("Tests", str(len(snapshot.tests)))
    table.add_row("Preconditions", str(len(snapshot.preconditions)))
    table.add_row("Test Sets", str(len(snapshot.test_sets)))
    table.add_row("Test Plans", str(len(snapshot.test_plans)))
    table.add_row("Test Executions", str(len(snapshot.executions)))
    table.add_row("Test Runs", str(len(snapshot.test_runs)))
    console.print(table)
    _print_preflight_warnings([(environment, snapshot)])


@app.command()
def export(
    environment: Annotated[str, typer.Option("--environment", "-e")],
    project: Annotated[str, typer.Option("--project", "-p")],
    output: Annotated[Path, typer.Option("--output", "-o")],
    config: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Export a deterministic read-only project snapshot."""
    snapshot = asyncio.run(_discover(environment=environment, project=project, config_path=config))
    export_dir = SnapshotExporter().export(snapshot, environment=environment, output=output)
    console.print(f"[green]Export written:[/] {export_dir}")


@app.command()
def diff(
    source: Annotated[str, typer.Option("--source")],
    target: Annotated[str, typer.Option("--target")],
    project: Annotated[str, typer.Option("--project", "-p")],
    config: Annotated[Path | None, typer.Option("--config")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
) -> None:
    """Compare source and target snapshots without mutating either environment."""
    source_snapshot, target_snapshot = asyncio.run(
        _discover_pair(source=source, target=target, project=project, config_path=config)
    )
    _print_preflight_warnings([(source, source_snapshot), (target, target_snapshot)])
    snapshot_diff = SnapshotComparer().compare(source_snapshot, target_snapshot)
    if json_output:
        console.print_json(data=snapshot_diff.model_dump(mode="json"))
    else:
        _print_diff(snapshot_diff)
    if snapshot_diff.has_differences:
        raise typer.Exit(1)


@app.command()
def plan(
    source: Annotated[str, typer.Option("--source")],
    target: Annotated[str, typer.Option("--target")],
    project: Annotated[str, typer.Option("--project", "-p")],
    output: Annotated[Path, typer.Option("--output", "-o")],
    config: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Dry-run source-to-target sync and write explicit proposed operations."""
    try:
        source_snapshot, target_snapshot = asyncio.run(
            _discover_pair(source=source, target=target, project=project, config_path=config)
        )
        _print_preflight_warnings([(source, source_snapshot), (target, target_snapshot)])
        sync_plan = Planner().build_plan(
            source_environment=source,
            target_environment=target,
            source=source_snapshot,
            target=target_snapshot,
        )
    except XraySyncError as exc:
        _print_sync_error(exc)
        raise typer.Exit(1) from exc
    write_plan(output, sync_plan)
    console.print(
        f"[green]Dry-run plan written:[/] {output} ({len(sync_plan.operations)} operations)"
    )


@app.command()
def apply(
    plan_file: Annotated[Path, typer.Argument(exists=True)],
    config: Annotated[Path | None, typer.Option("--config")] = None,
    checkpoint: Annotated[Path | None, typer.Option("--checkpoint")] = None,
) -> None:
    """Apply a previously generated plan to the target environment only."""
    sync_plan = read_plan(plan_file)
    with _apply_progress() as progress:
        task_id = progress.add_task("Preparing apply...", total=len(sync_plan.operations))
        completed = asyncio.run(
            _apply_plan(
                sync_plan,
                plan_path=plan_file,
                config_path=config,
                checkpoint_path=checkpoint,
                progress_callback=_rich_apply_progress(progress, task_id),
            )
        )
    console.print(
        f"[green]Apply complete:[/] {len(completed.completed)} operations recorded in checkpoint"
    )


@app.command()
def verify(
    source: Annotated[str, typer.Option("--source")],
    target: Annotated[str, typer.Option("--target")],
    project: Annotated[str, typer.Option("--project", "-p")],
    config: Annotated[Path | None, typer.Option("--config")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
) -> None:
    """Verify source and target are structurally equivalent for supported fields."""
    source_snapshot, target_snapshot = asyncio.run(
        _discover_pair(source=source, target=target, project=project, config_path=config)
    )
    _print_preflight_warnings([(source, source_snapshot), (target, target_snapshot)])
    snapshot_diff = SnapshotComparer().compare(source_snapshot, target_snapshot)
    if json_output:
        console.print_json(data=snapshot_diff.model_dump(mode="json"))
    else:
        _print_diff(snapshot_diff)
    if snapshot_diff.has_differences:
        raise typer.Exit(1)


def _print_preflight_warnings(
    snapshots: Sequence[tuple[str, ProjectSnapshot]],
) -> None:
    for warning in project_style_warnings(snapshots):
        console.print(f"[yellow]Warning:[/] {warning}")


def _print_sync_error(exc: XraySyncError) -> None:
    console.print(f"[red]{type(exc).__name__}:[/] {exc}")
    if exc.detail:
        console.print_json(data=exc.detail)


async def _discover(environment: str, project: str, config_path: Path | None) -> ProjectSnapshot:
    app_config = load_config(config_path)
    env = app_config.environment(environment)
    async with JiraClient(env.jira) as jira:
        async with XrayAuthClient(env.xray) as auth:
            async with XrayGraphQLClient(env.xray, auth) as xray:
                return await SourceDiscovery(jira, xray).discover_project(project)


async def _discover_pair(
    *, source: str, target: str, project: str, config_path: Path | None
) -> tuple[ProjectSnapshot, ProjectSnapshot]:
    source_snapshot = await _discover(source, project, config_path)
    app_config = load_config(config_path)
    target_env = app_config.environment(target)
    async with JiraClient(target_env.jira) as jira:
        async with XrayAuthClient(target_env.xray) as auth:
            async with XrayGraphQLClient(target_env.xray, auth) as xray:
                discovery = SourceDiscovery(jira, xray)
                target_snapshot = await discovery.discover_project(project)
                await discovery.enrich_referenced_containers(target_snapshot, source_snapshot)
    return source_snapshot, target_snapshot


async def _apply_plan(
    sync_plan: SyncPlan,
    *,
    plan_path: Path,
    config_path: Path | None,
    checkpoint_path: Path | None,
    progress_callback: ApplyProgressCallback,
) -> Checkpoint:
    app_config = load_config(config_path)
    env = app_config.environment(sync_plan.target_environment)
    async with XrayAuthClient(env.xray) as auth:
        async with XrayGraphQLClient(env.xray, auth) as xray:
            return await PlanExecutor(xray).apply(
                sync_plan,
                plan_path=plan_path,
                checkpoint_path=checkpoint_path,
                progress=progress_callback,
            )


def _apply_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def _rich_apply_progress(progress: Progress, task_id: TaskID) -> ApplyProgressCallback:
    def update(event: ApplyProgressEvent) -> None:
        if event.kind == "start":
            progress.update(
                task_id,
                completed=event.completed,
                total=event.total,
                description="Applying plan...",
            )
            return
        if event.kind == "operation_start" and event.operation:
            progress.update(
                task_id,
                description=_operation_description(event.operation),
            )
            return
        if event.kind == "operation_complete":
            progress.update(
                task_id,
                completed=event.completed,
                description="Applying plan...",
            )
            return
        if event.kind == "rate_limit":
            progress.update(
                task_id,
                completed=event.completed,
                description=event.message or "Rate limited; waiting...",
            )
            return
        if event.kind == "complete":
            progress.update(
                task_id,
                completed=event.completed,
                description="Apply complete",
            )

    return update


def _operation_description(operation: SyncOperation) -> str:
    key = operation.target_key or operation.source_key or ""
    return f"{operation.operation_id} {operation.action} {key}".strip()


def _print_diff(snapshot_diff: SnapshotDiff) -> None:
    if not snapshot_diff.has_differences:
        console.print("[green]No supported structural differences found.[/]")
        return
    table = Table(title="xray-sync diff")
    table.add_column("Entity")
    table.add_column("Key")
    table.add_column("Field")
    table.add_column("Source")
    table.add_column("Target")
    for item in snapshot_diff.differences:
        table.add_row(
            item.entity_type,
            item.key,
            item.field,
            _brief(item.source),
            _brief(item.target),
        )
    console.print(table)


def _brief(value: object | None) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) > 80:
        return text[:77] + "..."
    return text


if __name__ == "__main__":
    app()
