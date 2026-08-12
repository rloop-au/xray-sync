from __future__ import annotations

from pydantic import BaseModel, Field

from xray_sync.model.execution import TestExecution
from xray_sync.model.mapping import IssueMapping
from xray_sync.model.precondition import Precondition
from xray_sync.model.repository import RepositoryTree
from xray_sync.model.test import XrayTest
from xray_sync.model.test_plan import TestPlan
from xray_sync.model.test_run import TestRun
from xray_sync.model.test_set import TestSet


class ProjectSnapshot(BaseModel):
    project_key: str
    tests: dict[str, XrayTest] = Field(default_factory=dict)
    preconditions: dict[str, Precondition] = Field(default_factory=dict)
    test_sets: dict[str, TestSet] = Field(default_factory=dict)
    test_plans: dict[str, TestPlan] = Field(default_factory=dict)
    executions: dict[str, TestExecution] = Field(default_factory=dict)
    test_runs: dict[str, TestRun] = Field(default_factory=dict)
    repository: RepositoryTree | None = None
    mappings: dict[str, IssueMapping] = Field(default_factory=dict)
