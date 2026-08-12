from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Evidence(BaseModel):
    model_config = ConfigDict(extra="allow")

    filename: str
    sha256: str | None = None
    content_type: str | None = None
    size: int | None = None
