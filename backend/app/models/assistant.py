"""Assistant persistence models."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text

from ..db import Base, _now


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String)
    summary = Column(Text)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("assistant_sessions.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    tool_calls_json = Column(JSON, default=list)
    created_at = Column(DateTime, default=_now)


class AssistantPendingAction(Base):
    __tablename__ = "assistant_pending_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("assistant_sessions.id"), nullable=False)
    action = Column(String, nullable=False)
    payload_json = Column(JSON, default=dict)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=_now)
    resolved_at = Column(DateTime)
