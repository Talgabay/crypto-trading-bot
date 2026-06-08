"""Narrator: turns engine events into plain-language Hebrew updates and builds
the rich approval payload. This is the 'partner who tells you what's
happening' layer."""
from __future__ import annotations

from ..models import OrderIntent, Position, Side


def _dir(side: Side) -> str:
    return "לונג" if side is Side.LONG else "שורט"


def narrate_setup(intent: OrderIntent) -> str:
    s = intent.signal
    lines = [f"🔔 setup {_dir(s.side)} ב-{s.symbol} ({s.strategy})"]
    lines += [f"• {r}" for r in s.rationale]
    lines.append(
        f"כניסה ~{s.entry_price:.4f} | SL {s.stop_loss:.4f} | "
        f"R:R {s.risk_reward:.1f} | סיכון {intent.equity_at_risk_pct*100:.2f}%"
    )
    if intent.notes:
        lines += [f"⚠️ {n}" for n in intent.notes]
    return "\n".join(lines)


def build_alert(intent: OrderIntent, timeout_sec: int) -> dict:
    """Structured payload sent to UI + Telegram for human approval."""
    s = intent.signal
    return {
        "intent_id": intent.id,
        "symbol": s.symbol,
        "side": s.side.value,
        "strategy": s.strategy,
        "entry_type": s.entry_type.value,
        "entry_price": round(s.entry_price, 6),
        "stop_loss": round(s.stop_loss, 6),
        "take_profits": [[round(p, 6), f] for p, f in s.take_profits],
        "stop_distance": round(s.stop_distance, 6),
        "risk_reward": round(s.risk_reward, 2),
        "size": round(intent.size, 6),
        "notional": round(intent.notional, 2),
        "equity_at_risk_pct": round(intent.equity_at_risk_pct * 100, 3),
        "rationale": s.rationale,
        "notes": intent.notes,
        "regime": s.regime.value,
        "timeout_sec": timeout_sec,
        "narration": narrate_setup(intent),
    }


def narrate_fill(pos: Position) -> str:
    return (f"✅ נכנסנו {_dir(pos.side)} {pos.symbol} @ {pos.entry_price:.4f} "
            f"| גודל {pos.size:.4f} | SL {pos.stop_loss:.4f}")


def narrate_exit(pos: Position, price: float, reason: str) -> str:
    pnl = pos.unrealized_pnl(price) + pos.realized_pnl
    emoji = "🟢" if pnl >= 0 else "🔴"
    return (f"{emoji} סגירת {pos.symbol} ({reason}) @ {price:.4f} | "
            f"P&L {pnl:+.2f} ({pos.r_multiple(price):+.2f}R)")


def narrate_halt(reason: str) -> str:
    return f"🛑 עוצרים להיום: {reason}. צא לאוויר — נתראה מחר."
