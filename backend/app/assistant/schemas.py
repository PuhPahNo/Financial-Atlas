"""Assistant API contracts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    surface: Literal["copilot", "global"] = "copilot"


class PageContext(BaseModel):
    path: str = Field(default="", max_length=240)
    ticker: str | None = Field(default=None, max_length=12)


class MessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    page_context: PageContext | None = None
