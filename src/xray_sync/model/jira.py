from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JiraProject(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    key: str
    name: str | None = None


class JiraIssueType(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str


class JiraIssue(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    key: str
    fields: dict[str, Any] = Field(default_factory=dict)
