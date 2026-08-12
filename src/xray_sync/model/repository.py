from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RepositoryFolder(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str
    tests: list[str] = Field(default_factory=list)
    children: list[RepositoryFolder] = Field(default_factory=list)


class RepositoryTree(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_key: str
    folders: list[RepositoryFolder] = Field(default_factory=list)
