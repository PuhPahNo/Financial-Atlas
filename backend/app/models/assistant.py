"""Assistant persistence models."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text

from ..db import Base, _now


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String)
    surface = Column(String, nullable=False, default="copilot")
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
    artifact_json = Column(JSON, default=dict)
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


class OpenAIBudget(Base):
    """Singleton durable totals for the application-level hard spend cap."""

    __tablename__ = "openai_budget"

    id = Column(Integer, primary_key=True)
    spent_microusd = Column(Integer, nullable=False, default=0)
    reserved_microusd = Column(Integer, nullable=False, default=0)
    qa_spent_microusd = Column(Integer, nullable=False, default=0)
    qa_reserved_microusd = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class OpenAIUsage(Base):
    """Append-only-ish request ledger; reservations become settled or released."""

    __tablename__ = "openai_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reservation_key = Column(String(36), nullable=False, unique=True)
    response_id = Column(String, unique=True)
    session_id = Column(Integer, ForeignKey("assistant_sessions.id"))
    purpose = Column(String, nullable=False, default="production")
    model = Column(String, nullable=False)
    status = Column(String, nullable=False, default="reserved")
    reserved_microusd = Column(Integer, nullable=False)
    cost_microusd = Column(Integer, nullable=False, default=0)
    input_tokens = Column(Integer, nullable=False, default=0)
    cached_input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=_now)
    settled_at = Column(DateTime)
