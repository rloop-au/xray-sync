from __future__ import annotations

from pydantic import BaseModel, Field


class Checkpoint(BaseModel):
    plan: str
    completed: list[str] = Field(default_factory=list)
    failed: str | None = None
