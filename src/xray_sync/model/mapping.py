from __future__ import annotations

from pydantic import BaseModel


class IssueMapping(BaseModel):
    source_key: str
    source_jira_id: str
    source_xray_id: str | None = None
    target_key: str
    target_jira_id: str
    target_xray_id: str | None = None
