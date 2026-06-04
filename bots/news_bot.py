"""Daily AlphaWire market briefing publisher."""

from __future__ import annotations

import logging
import os
import sys
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.openai_client import MarketNewsClient
from src.telegram_client import TelegramClient, TelegramError


LOGGER = logging.getLogger("alphawire.news_bot")
STATE_FILE = PROJECT_ROOT / "data" / "latest_news_post.json"


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "y", "on"}


def load_settings() -> dict[str, str]:
    """Load required runtime settings from environment variables."""
    load_dotenv(PROJECT_ROOT / ".env")

    required = {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "").strip(),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL", "").strip() or "gpt-5.4-mini",
        "ALPHAWIRE_USE_LIVE_OPENAI": str(env_flag("ALPHAWIRE_USE_LIVE_OPENAI")),
    }

    missing = [
        key
        for key, value in required.items()
        if not value and key in {"TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"}
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    return required


def format_message(briefing: str) -> str:
    """Add a stable bot header around the model-generated briefing."""
    today = datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d")
    return f"🌍 AlphaWire Daily Market Briefing - {today} SGT\n\n{briefing.strip()}"


def save_post_receipt(
    briefing: str,
    message: str,
    telegram_results: list[dict[str, object]],
) -> None:
    """Persist the sent briefing so the review workflow can verify it later."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d")
    message_ids = [
        result.get("message_id")
        for result in telegram_results
        if isinstance(result.get("message_id"), int)
    ]
    receipt = {
        "date_sgt": today,
        "sent_at_sgt": datetime.now(ZoneInfo("Asia/Singapore")).isoformat(),
        "chat_id": os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        "message_id": message_ids[0] if message_ids else None,
        "message_ids": message_ids,
        "briefing": briefing,
        "telegram_message": message,
    }
    STATE_FILE.write_text(json.dumps(receipt, indent=2), encoding="utf-8")


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    try:
        settings = load_settings()
        market_news = MarketNewsClient(
            api_key=settings["OPENAI_API_KEY"],
            model=settings["OPENAI_MODEL"],
            use_live_openai=settings["ALPHAWIRE_USE_LIVE_OPENAI"] == "True",
        )
        telegram = TelegramClient(
            bot_token=settings["TELEGRAM_BOT_TOKEN"],
            chat_id=settings["TELEGRAM_CHAT_ID"],
        )

        briefing = market_news.generate_daily_briefing()
        message = format_message(briefing)
        telegram_results = telegram.send_message(message)
        save_post_receipt(briefing, message, telegram_results)
    except (RuntimeError, TelegramError) as exc:
        LOGGER.error("News bot failed: %s", exc)
        return 1
    except Exception:
        LOGGER.exception("Unexpected news bot failure")
        return 1

    LOGGER.info("Daily market briefing sent successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
