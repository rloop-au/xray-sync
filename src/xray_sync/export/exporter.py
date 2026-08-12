from __future__ import annotations

from pathlib import Path
from typing import Any

from xray_sync.model.snapshot import ProjectSnapshot
from xray_sync.storage.filesystem import write_json
from xray_sync.storage.manifest import ExportManifest


class SnapshotExporter:
    def export(self, snapshot: ProjectSnapshot, *, environment: str, output: Path) -> Path:
        export_dir = output / f"{snapshot.project_key}-xray-export"
        export_dir.mkdir(parents=True, exist_ok=True)
        manifest = ExportManifest.from_snapshot(snapshot, environment=environment)
        write_json(export_dir / "manifest.json", manifest.model_dump(by_alias=True))
        write_json(export_dir / "snapshot.json", snapshot.model_dump(mode="json"))
        write_json(export_dir / "tests.json", _dump_mapping(snapshot.tests))
        write_json(export_dir / "preconditions.json", _dump_mapping(snapshot.preconditions))
        write_json(export_dir / "test_sets.json", _dump_mapping(snapshot.test_sets))
        write_json(export_dir / "test_plans.json", _dump_mapping(snapshot.test_plans))
        write_json(export_dir / "test_executions.json", _dump_mapping(snapshot.executions))
        write_json(export_dir / "test_runs.json", _dump_mapping(snapshot.test_runs))
        write_json(
            export_dir / "repository.json",
            snapshot.repository.model_dump(mode="json") if snapshot.repository else {},
        )
        write_json(export_dir / "mappings.json", _dump_mapping(snapshot.mappings))
        (export_dir / "evidence").mkdir(exist_ok=True)
        return export_dir


def _dump_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item.model_dump(mode="json") for key, item in sorted(value.items())}
