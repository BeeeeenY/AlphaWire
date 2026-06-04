"""OpenAI integration for market-news briefing generation."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from openai import OpenAI


LOGGER = logging.getLogger("alphawire.openai_client")


MARKET_BRIEF_PROMPT = (
    "Prepare a concise morning market brief. Use current, reliable sources and "
    "include: major global and U.S. market news; key index, rates, tech sector, "
    "FX, and commodities moves where relevant; premarket or latest major market "
    "movers with likely drivers; important earnings, macro data, central bank, "
    "policy, and geopolitical items; notable sector themes, especially tech "
    "sector & AI related news; and a short watchlist for the trading day. "
    "Include source links and timestamp the brief."
)


SAMPLE_HEADLINES = [
    "Asian equities were mixed as investors weighed central-bank policy signals.",
    "US index futures were steady ahead of major macro data and earnings updates.",
    "Oil prices moved as traders assessed supply risks and demand expectations.",
    "The US dollar held firm while Treasury yields remained a key cross-asset driver.",
]


class MarketNewsClient:
    """Generate concise market briefings with OpenAI web search."""

    def __init__(self, api_key: str, model: str, use_live_openai: bool = False) -> None:
        self.api_key = api_key
        self.model = model
        self.use_live_openai = use_live_openai
        self.client = (
            OpenAI(api_key=api_key, timeout=300, max_retries=0)
            if api_key and use_live_openai
            else None
        )

    def generate_daily_briefing(self) -> str:
        """Return a concise daily market briefing.

        By default this returns a sample briefing so Telegram delivery can be
        tested without spending OpenAI tokens. Set ALPHAWIRE_USE_LIVE_OPENAI=true
        to call OpenAI web search.
        """
        if not self.client:
            LOGGER.info("Using sample market headlines; live OpenAI is disabled")
            return self._generate_sample_briefing()

        today = datetime.now(ZoneInfo("Asia/Singapore")).strftime("%B %d, %Y")
        prompt = (
            f"{MARKET_BRIEF_PROMPT}\n\n"
            f"Date context: {today}. Timing context: 11:00 AM Singapore time. "
            "Return text and icon for each section suitable for Telegram, under 650 words. Clearly distinguish facts from market interpretation. Do not start with a general title, start with the news directly. Be concise and informative. Telegram message format is not markdown, do not use * for formating. "
        
        )

        try:
            response = self.client.responses.create(
                model=self.model,
                reasoning={"effort": "low"},
                tools=[{"type": "web_search"}],
                input=prompt,
                max_output_tokens=3500,
                max_tool_calls=8,
            )
        except Exception as exc:
            raise RuntimeError(f"OpenAI briefing generation failed: {exc}") from exc

        briefing = extract_response_text(response)
        if not briefing:
            raise RuntimeError("OpenAI returned an empty briefing")

        return briefing

    def _generate_sample_briefing(self) -> str:
        bullets = "\n".join(f"- {headline}" for headline in SAMPLE_HEADLINES)
        return (
            "Executive summary\n"
            "- Sample briefing mode is active because OPENAI_API_KEY is not set.\n"
            "- Replace this with live OpenAI web-search output in production.\n\n"
            "What moved markets\n"
            f"{bullets}\n\n"
            "Asia/Singapore watch\n"
            "- Monitor regional index performance, USD/SGD, oil, and China-linked headlines.\n\n"
            "Key risks today\n"
            "- Macro data surprises, central-bank commentary, and earnings guidance."
        )


class BriefingReviewClient:
    """Review a posted market briefing and produce a short Telegram reply."""

    def __init__(self, api_key: str, model: str, use_live_openai: bool = False) -> None:
        self.api_key = api_key
        self.model = model
        self.use_live_openai = use_live_openai
        self.client = (
            OpenAI(api_key=api_key, timeout=60, max_retries=0)
            if api_key and use_live_openai
            else None
        )

    def review_briefing(self, briefing: str) -> str:
        if not self.client:
            LOGGER.info("Using sample review comment; live OpenAI is disabled")
            return "Verified! Yeehaw~🤠"

        prompt = (
            "You are a Shrimp Sheriff, reviewing other AI agents works. Review this AlphaWire daily market briefing for any major errors, missing key news, "
            "unsupported market assertions, whether major claims supported by sources, "
            "any wrong info etc. Reply in chinese with one short "
            "Telegram-ready sentence starting exactly with 'Verified.' if acceptable. example:Varified.🤠已检测到今日 AlphaWire 简报,整体内容准确，有一处小纰漏xxxxx。codex回去干活！(鞭子抽)"
            "Do not over criticize the quality of report, but check if information are correct. You can add-on new information also. Be playful in tone, remember you are a funny shrimp sheriff, fell free to add on emoji, except 🦐. Yeehaw~.\n\n"
            f"Briefing:\n{briefing}"
        )

        try:
            response = self.client.responses.create(
                model=self.model,
                reasoning={"effort": "low"},
                tools=[{"type": "web_search"}],
                input=prompt,
                max_output_tokens=1200,
                max_tool_calls=6,
            )
        except Exception as exc:
            raise RuntimeError(f"OpenAI briefing review failed: {exc}") from exc

        review = extract_response_text(response)
        if not review:
            raise RuntimeError("OpenAI returned an empty review")

        return review


def extract_response_text(response: object) -> str:
    """Extract text from OpenAI Responses API objects across SDK versions."""
    output_text = getattr(response, "output_text", "")
    if output_text:
        return output_text.strip()

    if hasattr(response, "model_dump"):
        response_data = response.model_dump()
        dumped_text = _extract_text_from_mapping(response_data)
        if dumped_text:
            return dumped_text

    output = getattr(response, "output", None) or []
    parts: list[str] = []
    for item in output:
        content = getattr(item, "content", None) or []
        for block in content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)

    return "\n".join(parts).strip()


def _extract_text_from_mapping(data: object) -> str:
    if not isinstance(data, dict):
        return ""

    parts: list[str] = []
    for item in data.get("output", []) or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for block in item.get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "output_text":
                text = block.get("text")
                if text:
                    parts.append(text)

    return "\n".join(parts).strip()
