from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from xray_sync.model.snapshot import ProjectSnapshot


class ExportManifest(BaseModel):
    format_version: int = Field(default=1, serialization_alias="formatVersion")
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    project: str
    environment: str
    counts: dict[str, int]

    @classmethod
    def from_snapshot(cls, snapshot: ProjectSnapshot, *, environment: str) -> ExportManifest:
        return cls(
            project=snapshot.project_key,
            environment=environment,
            counts={
                "tests": len(snapshot.tests),
                "preconditions": len(snapshot.preconditions),
                "testSets": len(snapshot.test_sets),
                "testPlans": len(snapshot.test_plans),
                "executions": len(snapshot.executions),
                "testRuns": len(snapshot.test_runs),
            },
        )
