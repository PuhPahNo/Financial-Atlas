"""Research assistant API routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..assistant import service
from ..assistant.schemas import MessageCreate, SessionCreate

router = APIRouter(prefix="/api/v1")


def envelope(data: Any) -> dict:
    return {"data": data, "meta": {"ticker": None, "served_by": "openai", "stale": False}}


@router.post("/assistant/sessions")
def create_session(payload: SessionCreate):
    return envelope(service.create_session(payload))


@router.get("/assistant/sessions/{session_id}")
def get_session(session_id: int):
    return envelope(service.get_session(session_id))


@router.post("/assistant/sessions/{session_id}/messages")
def add_message(session_id: int, payload: MessageCreate):
    return envelope(service.add_message(session_id, payload))


@router.post("/assistant/actions/{action_id}/confirm")
def confirm_action(action_id: int):
    return envelope(service.confirm_action(action_id))


@router.post("/assistant/actions/{action_id}/reject")
def reject_action(action_id: int):
    return envelope(service.reject_action(action_id))
