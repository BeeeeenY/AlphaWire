"""Daily AlphaWire briefing verification bot."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.openai_client import BriefingReviewClient
from src.telegram_client import TelegramClient, TelegramError


LOGGER = logging.getLogger("alphawire.review_bot")
DEFAULT_STATE_FILE = PROJECT_ROOT / "data" / "latest_news_post.json"
REVIEW_OPENAI_FAILURE_ALERT = "已找到简报，但本警长今天查不了网，你的token被我吃完啦，Yeehaw~"


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "y", "on"}


def load_settings() -> dict[str, str]:
    load_dotenv(PROJECT_ROOT / ".env")

    settings = {
        "REVIEW_TELEGRAM_BOT_TOKEN": os.getenv(
            "REVIEW_TELEGRAM_BOT_TOKEN",
            os.getenv("TELEGRAM_BOT_TOKEN", ""),
        ).strip(),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "").strip(),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL", "").strip() or "gpt-5.4-mini",
        "ALPHAWIRE_USE_LIVE_OPENAI": str(env_flag("ALPHAWIRE_USE_LIVE_OPENAI")),
        "NEWS_BOT_USERNAME": os.getenv("NEWS_BOT_USERNAME", "").strip().lstrip("@"),
        "ALPHAWIRE_STATE_FILE": os.getenv(
            "ALPHAWIRE_STATE_FILE",
            str(DEFAULT_STATE_FILE),
        ).strip(),
    }

    missing = [
        key
        for key in ("REVIEW_TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
        if not settings[key]
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    return settings


def today_sgt() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d")


def load_news_receipt(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None

    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read news receipt at {path}: {exc}") from exc

    if receipt.get("date_sgt") != today_sgt():
        LOGGER.warning("Ignoring stale news receipt dated %s", receipt.get("date_sgt"))
        return None

    if not receipt.get("briefing") and not receipt.get("telegram_message"):
        LOGGER.warning("Ignoring news receipt without briefing content")
        return None

    return receipt


def find_visible_news_post(
    telegram: TelegramClient,
    news_bot_username: str,
    lookback_minutes: int = 180,
) -> dict[str, Any] | None:
    """Best-effort scan of updates visible to this bot.

    Telegram bots cannot see messages from other bots, so this is mainly useful
    when testing with human-posted copies or if Telegram changes update behavior.
    """
    if not news_bot_username:
        return None

    updates = telegram.get_updates(limit=100, timeout_seconds=0, allowed_updates=["message"])
    cutoff = datetime.now(ZoneInfo("Asia/Singapore")) - timedelta(minutes=lookback_minutes)
    expected_header = f"AlphaWire Daily Market Briefing - {today_sgt()} SGT"

    for update in reversed(updates):
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        sent_at = datetime.fromtimestamp(message.get("date", 0), tz=ZoneInfo("Asia/Singapore"))
        text = message.get("text", "")

        if str(chat.get("id")) != telegram.chat_id:
            continue
        if sent_at < cutoff:
            continue
        if sender.get("username") != news_bot_username:
            continue
        if expected_header not in text:
            continue

        return {
            "message_id": message.get("message_id"),
            "telegram_message": text,
            "briefing": text.replace(expected_header, "", 1).strip(),
        }

    return None


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    try:
        settings = load_settings()
        telegram = TelegramClient(
            bot_token=settings["REVIEW_TELEGRAM_BOT_TOKEN"],
            chat_id=settings["TELEGRAM_CHAT_ID"],
        )
        reviewer = BriefingReviewClient(
            api_key=settings["OPENAI_API_KEY"],
            model=settings["OPENAI_MODEL"],
            use_live_openai=settings["ALPHAWIRE_USE_LIVE_OPENAI"] == "True",
        )

        receipt = load_news_receipt(Path(settings["ALPHAWIRE_STATE_FILE"]))
        if not receipt:
            receipt = find_visible_news_post(
                telegram=telegram,
                news_bot_username=settings["NEWS_BOT_USERNAME"],
            )

        if not receipt:
            alert = (
                f"未通过验证。虾警长巡逻到 {today_sgt()}，"
                "没有发现 Codex 今天的 AlphaWire 简报回执。Codex，速速交稿，🤠Yeehaw~"
            )
            telegram.send_message(alert)
            LOGGER.error(alert)
            return 1

        briefing = receipt.get("briefing") or receipt["telegram_message"]
        try:
            review = reviewer.review_briefing(briefing)
        except RuntimeError as exc:
            telegram.send_message(
                REVIEW_OPENAI_FAILURE_ALERT,
                reply_to_message_id=receipt.get("message_id"),
            )
            raise RuntimeError(f"{exc}; sent Telegram failure alert") from exc

        telegram.send_message(review, reply_to_message_id=receipt.get("message_id"))
    except (RuntimeError, TelegramError, ValueError) as exc:
        LOGGER.error("Review bot failed: %s", exc)
        if "401 Client Error: Unauthorized" in str(exc):
            LOGGER.error(
                "Telegram rejected REVIEW_TELEGRAM_BOT_TOKEN. Regenerate or re-copy "
                "the review bot token from BotFather, then update .env and GitHub Secrets."
            )
        return 1
    except Exception:
        LOGGER.exception("Unexpected review bot failure")
        return 1

    LOGGER.info("Daily briefing review sent successfully")
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
