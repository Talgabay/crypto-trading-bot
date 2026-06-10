"""FastAPI host: runs the engine as a managed asyncio task and exposes REST +
WebSocket for the dashboard. Engine lives in app.state; the WS streams every
narration/alert/tick event to the UI."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine.db import repo
from engine.models import AutonomyMode, EngineState
from engine.runtime import Runtime

log = logging.getLogger("api")


class ApprovalAction(BaseModel):
    action: str                      # approve | reject | modify
    modifications: Optional[dict] = None
    was_override: bool = False


class ControlAction(BaseModel):
    action: str                      # pause | resume | halt | autonomy
    autonomy: Optional[str] = None


def create_app() -> FastAPI:
    app = FastAPI(title="Crypto Trading Co-Pilot", version="0.1.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _startup() -> None:
        rt = Runtime()  # live vs synthetic comes from USE_LIVE in .env
        await rt.start_telegram()
        app.state.rt = rt
        app.state.task = asyncio.create_task(_supervise(rt))
        log.info("engine task started")

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        task = getattr(app.state, "task", None)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _supervise(rt: Runtime) -> None:
        """Restart the engine loop if it crashes (isolated failure domain)."""
        while True:
            try:
                await rt.run()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("engine loop crashed; restarting in 3s")
                await asyncio.sleep(3)

    # --- health & status ---------------------------------------------------
    @app.get("/health")
    async def health():
        rt: Runtime = app.state.rt
        return {"status": "ok", "engine_state": rt.engine.status.state.value}

    @app.get("/api/status")
    async def status():
        rt: Runtime = app.state.rt
        e = rt.engine
        return {
            "state": e.status.state.value,
            "autonomy": e.status.autonomy.value,
            "equity": round(rt.broker.get_equity(), 2),
            "daily_pnl": round(e.day.realized_pnl, 2),
            "trades_today": e.day.trades,
            "discipline_score": e.discipline.discipline_score(),
            "in_cooldown": e.tilt.state.in_cooldown(),
            "live": rt.use_live,
            "prices": e.status.last_price,
        }

    @app.get("/api/positions")
    async def positions():
        rt: Runtime = app.state.rt
        out = []
        for p in rt.broker.get_positions():
            mark = rt.engine.status.last_price.get(p.symbol, p.entry_price)
            out.append({
                "symbol": p.symbol, "side": p.side.value, "size": p.size,
                "entry": p.entry_price, "stop": p.stop_loss, "mark": mark,
                "upnl": round(p.unrealized_pnl(mark), 2),
                "r": round(p.r_multiple(mark), 2),
                "tp1_done": p.tp1_done,
            })
        return out

    @app.get("/api/approvals")
    async def approvals():
        rt: Runtime = app.state.rt
        return rt.approvals.pending_payloads()

    @app.post("/api/approvals/{intent_id}")
    async def resolve(intent_id: str, body: ApprovalAction):
        rt: Runtime = app.state.rt
        ok = rt.approvals.resolve(intent_id, body.action, body.modifications,
                                  body.was_override)
        return {"ok": ok}

    @app.get("/api/journal")
    async def journal():
        return {"summary": repo.journal_summary()}

    @app.post("/api/control")
    async def control(body: ControlAction):
        rt: Runtime = app.state.rt
        e = rt.engine
        if body.action == "pause":
            e.set_state(EngineState.PAUSED)
        elif body.action == "resume":
            e.set_state(EngineState.RUNNING)
        elif body.action in ("halt", "kill"):
            e.set_state(EngineState.HALTED)
        elif body.action == "autonomy" and body.autonomy:
            e.set_autonomy(AutonomyMode(body.autonomy))
        return {"state": e.status.state.value, "autonomy": e.status.autonomy.value}

    # --- websocket ---------------------------------------------------------
    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        rt: Runtime = app.state.rt
        await websocket.accept()
        q = rt.ws_hub.subscribe()
        try:
            while True:
                event = await q.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            rt.ws_hub.unsubscribe(q)

    return app


app = create_app()
