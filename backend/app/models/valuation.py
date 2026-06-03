"""Valuation result persistence models."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String

from ..db import Base, _now


class ValuationResult(Base):
    __tablename__ = "valuation_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, nullable=False, index=True)
    valuation_date = Column(DateTime, default=_now, index=True)
    current_price = Column(Float)
    blended_fair_value = Column(Float)
    margin_of_safety = Column(Float)
    assumptions_json = Column(JSON, default=dict)
    weights_json = Column(JSON, default=dict)
    result_json = Column(JSON, default=dict)

