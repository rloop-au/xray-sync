from __future__ import annotations

import json
from pathlib import Path

from xray_sync.export.exporter import SnapshotExporter
from xray_sync.model.snapshot import ProjectSnapshot
from xray_sync.model.test import XrayTest


def test_exporter_writes_manifest_and_entities(tmp_path: Path) -> None:
    snapshot = ProjectSnapshot(
        project_key="ABC",
        tests={"ABC-1": XrayTest(jira_key="ABC-1", jira_id="10001", test_type="Manual")},
    )

    export_dir = SnapshotExporter().export(snapshot, environment="prod", output=tmp_path)

    manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
    tests = json.loads((export_dir / "tests.json").read_text(encoding="utf-8"))
    assert manifest["project"] == "ABC"
    assert manifest["counts"]["tests"] == 1
    assert tests["ABC-1"]["jira_key"] == "ABC-1"
