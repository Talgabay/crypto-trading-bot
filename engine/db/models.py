"""SQLAlchemy models. Audit-first: every signal, approval, override, fill and
equity snapshot is persisted (council: logging/journal is foundational, not
polish — it's also the data that closes the psychological feedback loop)."""
from __future__ import annotations

import time

from sqlalchemy import JSON, Boolean, Column, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class JournalEntry(Base):
    __tablename__ = "journal"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(Float, default=time.time, index=True)
    symbol = Column(String(32))
    side = Column(String(8))
    strategy = Column(String(32))
    decision = Column(String(16))          # approved/rejected/modified/override/auto
    was_override = Column(Boolean, default=False)
    entry_price = Column(Float)
    stop_loss = Column(Float)
    risk_reward = Column(Float)
    size = Column(Float)
    rationale = Column(JSON)
    outcome_pnl = Column(Float, nullable=True)  # filled when the trade closes
    outcome_r = Column(Float, nullable=True)
    emotion_tag = Column(String(32), nullable=True)
    intent_id = Column(String(32), index=True)


class NarrationLog(Base):
    __tablename__ = "narration_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(Float, default=time.time, index=True)
    level = Column(String(16), default="info")
    text = Column(Text)


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(Float, default=time.time, index=True)
    equity = Column(Float)
    realized_pnl = Column(Float, default=0.0)


class DisciplineEvent(Base):
    __tablename__ = "discipline_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(Float, default=time.time, index=True)
    kind = Column(String(32))   # cooldown | override_blocked | halt | tilt
    detail = Column(Text)


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(64), primary_key=True)
    value = Column(JSON)
