from __future__ import annotations

import datetime as dt
import json
from typing import List, Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(String(36), primary_key=True)
    period_id = Column(Integer, nullable=False)
    numbers = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    matches = Column(Integer, nullable=True)
    payout = Column(Integer, nullable=True)
    claimed = Column(Boolean, nullable=False, default=False)
    buyer = Column(String(64), nullable=True)
    tx_hash = Column(String(66), nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False)

    def set_numbers(self, numbers: List[int]) -> None:
        self.numbers = json.dumps(numbers)

    def get_numbers(self) -> List[int]:
        return json.loads(self.numbers)

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.id,
            "period_id": self.period_id,
            "numbers": self.get_numbers(),
            "status": self.status,
            "matches": self.matches,
            "payout": self.payout,
            "claimed": self.claimed,
            "buyer": self.buyer,
            "tx_hash": self.tx_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Draw(Base):
    __tablename__ = "draws"

    period_id = Column(Integer, primary_key=True)
    winning_numbers = Column(Text, nullable=False)
    submitted_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    def set_numbers(self, numbers: List[int]) -> None:
        self.winning_numbers = json.dumps(numbers)

    def get_numbers(self) -> List[int]:
        return json.loads(self.winning_numbers)

    def to_dict(self) -> dict:
        return {
            "period_id": self.period_id,
            "winning_numbers": self.get_numbers(),
            "submitted_at": self.submitted_at.isoformat(),
        }


class SystemState(Base):
    __tablename__ = "system_state"

    id = Column(Integer, primary_key=True, default=1)
    current_period = Column(Integer, nullable=False, default=1)
