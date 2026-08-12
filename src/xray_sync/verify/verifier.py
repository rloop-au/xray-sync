from __future__ import annotations

from xray_sync.diff.comparer import SnapshotComparer, SnapshotDiff
from xray_sync.model.snapshot import ProjectSnapshot


class SnapshotVerifier:
    def verify(self, source: ProjectSnapshot, target: ProjectSnapshot) -> SnapshotDiff:
        return SnapshotComparer().compare(source, target)
