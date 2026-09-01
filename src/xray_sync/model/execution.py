from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field


class TestExecution(BaseModel):
    model_config = ConfigDict(extra="allow")
    __test__: ClassVar[bool] = False

    jira_key: str
    jira_id: str | None = None
    xray_id: str | None = None
    tests: list[str] = Field(default_factory=list)
    plans: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)
