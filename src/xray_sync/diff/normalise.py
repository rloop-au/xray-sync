from __future__ import annotations

from typing import Any

from xray_sync.model.repository import RepositoryTree
from xray_sync.model.test import XrayTest
from xray_sync.model.test_run import TestRun


def normalise_test(test: XrayTest) -> dict[str, Any]:
    data = test.model_dump(mode="json", exclude={"jira_id", "xray_id", "raw"})
    data["preconditions"] = sorted(data.get("preconditions") or [])
    data["test_sets"] = sorted(data.get("test_sets") or [])
    data["test_plans"] = sorted(data.get("test_plans") or [])
    data["test_executions"] = sorted(data.get("test_executions") or [])
    data["steps"] = [
        {
            "action": step.get("action") or "",
            "data": step.get("data") or "",
            "expected_result": step.get("expected_result") or "",
        }
        for step in data.get("steps", [])
    ]
    return data


def normalise_repository(repository: RepositoryTree | None) -> dict[str, Any]:
    if repository is None:
        return {"folders": []}
    data = repository.model_dump(mode="json")
    data["folders"] = sorted(data.get("folders", []), key=lambda item: item.get("path", ""))
    return data


def normalise_test_run(test_run: TestRun) -> dict[str, Any]:
    return test_run.model_dump(mode="json", exclude={"id", "raw"})
