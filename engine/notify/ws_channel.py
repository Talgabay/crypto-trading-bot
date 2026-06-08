"""In-process pub/sub used by the FastAPI WebSocket hub to stream events to
the UI. Decoupled from FastAPI so the engine has no web dependency."""
from __future__ import annotations

import asyncio
from typing import Any

from .base import NotificationChannel


class WsHub(NotificationChannel):
    name = "ui"

    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def _broadcast(self, event: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def send_text(self, text: str) -> None:
        await self._broadcast({"type": "narration", "text": text})

    async def send_alert(self, alert: dict) -> None:
        await self._broadcast({"type": "approval_request", "alert": alert})

    async def push(self, event_type: str, payload: dict) -> None:
        await self._broadcast({"type": event_type, **payload})
