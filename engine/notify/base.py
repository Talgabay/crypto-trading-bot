"""Notification abstraction. The same events (narration, alerts, halts) fan
out to every configured channel (Telegram + UI)."""
from __future__ import annotations

import abc
import logging

log = logging.getLogger("notify")


class NotificationChannel(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def send_text(self, text: str) -> None:
        ...

    @abc.abstractmethod
    async def send_alert(self, alert: dict) -> None:
        """Push an approval request (with action affordances where supported)."""


class NotificationHub:
    def __init__(self):
        self.channels: list[NotificationChannel] = []

    def register(self, channel: NotificationChannel) -> None:
        self.channels.append(channel)
        log.info("registered notification channel: %s", channel.name)

    async def text(self, text: str) -> None:
        for ch in self.channels:
            try:
                await ch.send_text(text)
            except Exception as exc:  # never let a channel crash the engine
                log.warning("channel %s text failed: %s", ch.name, exc)

    async def alert(self, alert: dict) -> None:
        for ch in self.channels:
            try:
                await ch.send_alert(alert)
            except Exception as exc:
                log.warning("channel %s alert failed: %s", ch.name, exc)
