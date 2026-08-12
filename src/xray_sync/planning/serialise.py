from __future__ import annotations

import json
from pathlib import Path

from xray_sync.planning.operation import SyncPlan


def write_plan(path: Path, plan: SyncPlan) -> None:
    path.write_text(
        json.dumps(plan.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_plan(path: Path) -> SyncPlan:
    return SyncPlan.model_validate_json(path.read_text(encoding="utf-8"))
