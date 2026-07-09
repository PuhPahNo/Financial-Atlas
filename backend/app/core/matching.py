"""Deterministic human-name matching shared by assistant and account workflows."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from typing import TypeVar

T = TypeVar("T")


def _name(row: object) -> str:
    if isinstance(row, Mapping):
        return str(row.get("name", ""))
    return str(getattr(row, "name", ""))


def _tokens(value: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", value.lower()) if len(part) > 1}


def best_name_match(rows: Iterable[T], text: str) -> T | None:
    """Prefer an exact normalized name, then the strongest token overlap."""
    candidates = list(rows)
    needle = " ".join(str(text or "").strip().lower().split())
    if not needle:
        return None
    for row in candidates:
        if " ".join(_name(row).lower().split()) == needle:
            return row
    wanted = _tokens(needle)
    best: T | None = None
    best_score = 0
    for row in candidates:
        score = len(wanted & _tokens(_name(row)))
        if score > best_score:
            best, best_score = row, score
    return best if best_score else None
