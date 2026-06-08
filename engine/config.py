"""Configuration loader: merges secret .env (pydantic-settings) with
non-secret config/settings.yaml. No secrets are ever read from YAML."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Secrets(BaseSettings):
    """Secret / environment configuration (from .env)."""
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    exchange: str = "binance"
    sandbox: bool = True
    trading_mode: str = "paper"  # hard safety: only 'paper' executes real orders

    binance_testnet_api_key: str = ""
    binance_testnet_secret: str = ""
    binance_sandbox_rest_url: str = "https://testnet.binance.vision"
    binance_sandbox_ws_url: str = "wss://testnet.binance.vision/ws"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    database_url: str = "sqlite:///data/bot.db"
    log_level: str = "INFO"


def _load_yaml() -> dict[str, Any]:
    path = ROOT / "config" / "settings.yaml"
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


class Settings:
    """Unified settings facade."""

    def __init__(self) -> None:
        self.secrets = Secrets()
        self.params = _load_yaml()

    # convenience accessors -------------------------------------------------
    @property
    def universe(self) -> dict[str, Any]:
        return self.params.get("universe", {})

    @property
    def strategy(self) -> dict[str, Any]:
        return self.params.get("strategy", {})

    @property
    def exits(self) -> dict[str, Any]:
        return self.params.get("exits", {})

    @property
    def risk(self) -> dict[str, Any]:
        return self.params.get("risk", {})

    @property
    def coach(self) -> dict[str, Any]:
        return self.params.get("coach", {})

    @property
    def notify(self) -> dict[str, Any]:
        return self.params.get("notify", {})

    @property
    def is_paper(self) -> bool:
        return self.secrets.trading_mode.lower() == "paper"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
