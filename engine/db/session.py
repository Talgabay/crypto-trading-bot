"""Database engine/session bootstrap (SQLite by default)."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

_engine = None
_Session: sessionmaker | None = None


def init_db(database_url: str = "sqlite:///data/bot.db") -> None:
    global _engine, _Session
    if database_url.startswith("sqlite:///"):
        rel = database_url.replace("sqlite:///", "")
        Path(rel).parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(database_url, future=True)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    Base.metadata.create_all(_engine)


def get_session() -> Session:
    if _Session is None:
        init_db(os.getenv("DATABASE_URL", "sqlite:///data/bot.db"))
    assert _Session is not None
    return _Session()
