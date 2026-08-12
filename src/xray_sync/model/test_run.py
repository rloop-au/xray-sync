from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TestRun(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    test_key: str | None = None
    execution_key: str | None = None
    status: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)
