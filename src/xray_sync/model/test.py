from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field


class TestStep(BaseModel):
    model_config = ConfigDict(extra="allow")
    __test__: ClassVar[bool] = False

    id: str | None = None
    action: str | None = None
    data: str | None = None
    expected_result: str | None = None


class XrayTest(BaseModel):
    model_config = ConfigDict(extra="allow")
    __test__: ClassVar[bool] = False

    jira_key: str
    jira_id: str | None = None
    xray_id: str | None = None
    test_type: str | None = None
    unstructured: str | None = None
    gherkin: str | None = None
    folder_path: str | None = None
    steps: list[TestStep] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    test_sets: list[str] = Field(default_factory=list)
    test_plans: list[str] = Field(default_factory=list)
    test_executions: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)
