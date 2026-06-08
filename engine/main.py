"""Headless runner: runs the engine without the API (Telegram + console).

    python -m engine.main            # synthetic demo
    python -m engine.main --live     # live testnet feed (requires keys)
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from .runtime import Runtime


async def _amain(use_live: bool) -> None:
    rt = Runtime(use_live=use_live)
    await rt.start_telegram()
    logging.info("engine started (autonomy=%s, live=%s)",
                 rt.engine.status.autonomy.value, rt.use_live)
    await rt.run()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        asyncio.run(_amain(args.live))
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
