from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from xray_sync.diff.normalise import normalise_repository, normalise_test, normalise_test_run
from xray_sync.model.snapshot import ProjectSnapshot


class Difference(BaseModel):
    entity_type: str
    key: str
    field: str
    source: object | None = None
    target: object | None = None


class SnapshotDiff(BaseModel):
    differences: list[Difference] = Field(default_factory=list)

    @property
    def has_differences(self) -> bool:
        return bool(self.differences)


class SnapshotComparer:
    def compare(self, source: ProjectSnapshot, target: ProjectSnapshot) -> SnapshotDiff:
        diff = SnapshotDiff()
        self._compare_mapping(diff, "Test", source.tests, target.tests, normalise_test)
        self._compare_mapping(
            diff, "TestRun", source.test_runs, target.test_runs, normalise_test_run
        )
        source_repo = normalise_repository(source.repository)
        target_repo = normalise_repository(target.repository)
        if source_repo != target_repo:
            diff.differences.append(
                Difference(
                    entity_type="Repository",
                    key=source.project_key,
                    field="tree",
                    source=source_repo,
                    target=target_repo,
                )
            )
        return diff

    def _compare_mapping(
        self,
        diff: SnapshotDiff,
        entity_type: str,
        source: dict[str, Any],
        target: dict[str, Any],
        normalise: Callable[[Any], dict[str, Any]],
    ) -> None:
        for key in sorted(set(source) | set(target)):
            if key not in target:
                diff.differences.append(
                    Difference(entity_type=entity_type, key=key, field="missing_target")
                )
            elif key not in source:
                diff.differences.append(
                    Difference(entity_type=entity_type, key=key, field="extra_target")
                )
            else:
                source_value = normalise(source[key])
                target_value = normalise(target[key])
                if source_value != target_value:
                    diff.differences.append(
                        Difference(
                            entity_type=entity_type,
                            key=key,
                            field="content",
                            source=source_value,
                            target=target_value,
                        )
                    )
