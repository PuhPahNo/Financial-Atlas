"""Assistant API contracts."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class MessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class AssistantAction(BaseModel):
    action: str
    payload: dict
