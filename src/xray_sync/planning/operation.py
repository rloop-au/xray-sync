from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SyncOperation(BaseModel):
    operation_id: str
    action: str
    entity_type: str
    source_key: str | None = None
    target_key: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class SyncPlan(BaseModel):
    format_version: int = 1
    source_environment: str
    target_environment: str
    project_key: str
    mode: str = "dry-run"
    operations: list[SyncOperation] = Field(default_factory=list)
