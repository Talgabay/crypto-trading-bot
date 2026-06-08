"""Telegram channel: the 'partner in your pocket'. Sends narration and
approval requests with inline Approve/Reject buttons. Safe no-op if no token
is configured."""
from __future__ import annotations

import logging
from typing import Callable, Optional

from .base import NotificationChannel

log = logging.getLogger("notify.telegram")


class TelegramChannel(NotificationChannel):
    name = "telegram"

    def __init__(self, token: str, chat_id: str,
                 on_action: Optional[Callable] = None):
        self.token = token
        self.chat_id = chat_id
        self.on_action = on_action  # async (intent_id, action) -> None
        self._bot = None
        self._app = None

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    async def start(self) -> None:
        if not self.enabled:
            log.info("telegram disabled (no token/chat_id) — UI only")
            return
        from telegram import Bot
        from telegram.ext import Application, CallbackQueryHandler

        self._app = Application.builder().token(self.token).build()
        self._app.add_handler(CallbackQueryHandler(self._on_callback))
        self._bot = self._app.bot
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        log.info("telegram channel started")

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def _on_callback(self, update, context) -> None:
        query = update.callback_query
        await query.answer()
        try:
            action, intent_id = query.data.split(":", 1)
        except ValueError:
            return
        if self.on_action:
            await self.on_action(intent_id, action)
        await query.edit_message_text(f"{query.message.text}\n\n➡️ {action}")

    async def send_text(self, text: str) -> None:
        if self._bot:
            await self._bot.send_message(chat_id=self.chat_id, text=text)

    async def send_alert(self, alert: dict) -> None:
        if not self._bot:
            return
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        iid = alert["intent_id"]
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ אישור", callback_data=f"approve:{iid}"),
            InlineKeyboardButton("❌ דחייה", callback_data=f"reject:{iid}"),
        ]])
        await self._bot.send_message(
            chat_id=self.chat_id, text=alert["narration"], reply_markup=kb)
