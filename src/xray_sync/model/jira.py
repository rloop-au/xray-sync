from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JiraProject(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    key: str
    name: str | None = None
    style: str | None = None
    simplified: bool | None = None

    @property
    def is_team_managed(self) -> bool:
        """Whether Jira reports this project as team-managed (formerly next-gen)."""
        if self.simplified is not None:
            return self.simplified
        return (self.style or "").lower() == "next-gen"

    @property
    def style_label(self) -> str:
        if self.simplified is None and not self.style:
            return "unknown"
        return "team-managed" if self.is_team_managed else "company-managed"


class JiraIssueType(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str


class JiraIssue(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    key: str
    fields: dict[str, Any] = Field(default_factory=dict)
