"""Small Telegram Bot API client."""

from __future__ import annotations

import html
import logging
import re
from typing import Any

import requests


LOGGER = logging.getLogger("alphawire.telegram_client")


class TelegramError(RuntimeError):
    """Raised when the Telegram Bot API returns an error."""


class TelegramClient:
    """Send messages through Telegram's HTTP Bot API."""

    def __init__(self, bot_token: str, chat_id: str, timeout_seconds: int = 20) -> None:
        if not bot_token:
            raise ValueError("bot_token is required")
        if not chat_id:
            raise ValueError("chat_id is required")

        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds

    def send_message(
        self,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Send text to the configured chat, splitting long Telegram messages."""
        if not text.strip():
            raise ValueError("Cannot send an empty Telegram message")

        results = []
        formatted_text = _markdown_links_to_telegram_html(text)
        for chunk in _split_telegram_text(formatted_text):
            payload = {
                "chat_id": self.chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "link_preview_options": {"is_disabled": True},
            }
            if reply_to_message_id:
                payload["reply_parameters"] = {
                    "message_id": reply_to_message_id,
                    "allow_sending_without_reply": True,
                }
            results.append(self._post("sendMessage", payload))

        LOGGER.info("Sent %d Telegram message chunk(s)", len(results))
        return results

    def get_updates(
        self,
        limit: int = 100,
        timeout_seconds: int = 0,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch recent updates visible to this bot."""
        payload: dict[str, Any] = {
            "limit": limit,
            "timeout": timeout_seconds,
        }
        if allowed_updates:
            payload["allowed_updates"] = allowed_updates

        return self._post("getUpdates", payload)

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{method}"
        try:
            response = requests.post(url, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise TelegramError(f"Telegram request failed: {exc}") from exc
        except ValueError as exc:
            raise TelegramError("Telegram returned a non-JSON response") from exc

        if not body.get("ok"):
            description = body.get("description", "Unknown Telegram API error")
            raise TelegramError(description)

        return body["result"]


def _split_telegram_text(text: str, max_length: int = 4096) -> list[str]:
    """Split text on paragraph boundaries to respect Telegram's message limit."""
    text = text.strip()
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_length:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        while len(paragraph) > max_length:
            chunks.append(paragraph[:max_length])
            paragraph = paragraph[max_length:]
        current = paragraph

    if current:
        chunks.append(current)

    return chunks


def _markdown_links_to_telegram_html(text: str) -> str:
    """Convert Markdown links to Telegram-safe HTML links.

    Telegram does not parse Markdown unless parse_mode is set, and MarkdownV2
    requires aggressive escaping. HTML is simpler here: escape all plain text
    and preserve only links emitted as [label](url).
    """
    link_pattern = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
    parts: list[str] = []
    last_end = 0

    for match in link_pattern.finditer(text):
        parts.append(html.escape(text[last_end : match.start()]))
        label = html.escape(match.group(1))
        url = html.escape(match.group(2), quote=True)
        parts.append(f'<a href="{url}">{label}</a>')
        last_end = match.end()

    parts.append(html.escape(text[last_end:]))
    return "".join(parts)
