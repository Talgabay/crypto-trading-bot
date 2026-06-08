"""Thin persistence helpers used by the engine + API."""
from __future__ import annotations

import time

from .models import (DisciplineEvent, EquitySnapshot, JournalEntry,
                     NarrationLog)
from .session import get_session


def log_narration(text: str, level: str = "info") -> None:
    with get_session() as s:
        s.add(NarrationLog(text=text, level=level))
        s.commit()


def record_journal(**kwargs) -> int:
    with get_session() as s:
        entry = JournalEntry(**kwargs)
        s.add(entry)
        s.commit()
        return entry.id


def update_journal_outcome(intent_id: str, pnl: float, r: float) -> None:
    with get_session() as s:
        rows = s.query(JournalEntry).filter_by(intent_id=intent_id).all()
        for row in rows:
            row.outcome_pnl = pnl
            row.outcome_r = r
        s.commit()


def snapshot_equity(equity: float, realized: float = 0.0) -> None:
    with get_session() as s:
        s.add(EquitySnapshot(equity=equity, realized_pnl=realized))
        s.commit()


def record_discipline(kind: str, detail: str) -> None:
    with get_session() as s:
        s.add(DisciplineEvent(kind=kind, detail=detail))
        s.commit()


def journal_summary() -> dict:
    """Followed-plan vs override performance — the psychological feedback loop."""
    with get_session() as s:
        rows = s.query(JournalEntry).filter(
            JournalEntry.outcome_pnl.isnot(None)).all()
    followed = [r for r in rows if not r.was_override]
    override = [r for r in rows if r.was_override]

    def agg(items):
        pnl = sum(r.outcome_pnl or 0 for r in items)
        wins = sum(1 for r in items if (r.outcome_pnl or 0) >= 0)
        return {"count": len(items), "wins": wins, "pnl": round(pnl, 2)}

    return {"followed": agg(followed), "override": agg(override),
            "generated_at": time.time()}
