# AlphaWire

AlphaWire is a Telegram-native market briefing system powered by OpenAI. Every morning, Codex writes a concise market brief. Five minutes later, Shrimp Sheriff rides in to verify the receipt, review the report, and call out anything suspicious.

Fear the tiny crustacean. 🤠🦞

<p align="center">
  <img src="assets/shrimp-sheriff.png" alt="Shrimp Sheriff bot" width="320">
</p>

## What It Does

- Posts a daily market briefing to a Telegram group at 11:00 AM Singapore time.
- Uses OpenAI web search in live mode to gather current market news.
- Saves a dated receipt after the news bot posts, so the review bot can verify that today’s brief exists.
- Runs Shrimp Sheriff at 11:05 AM Singapore time to review Codex’s work.
- Keeps local testing cheap with sample-mode defaults. Live OpenAI calls only happen when explicitly enabled.

## Project Structure

```text
AlphaWire/
├── bots/
│   ├── news_bot.py          # Codex: generates and sends the daily briefing
│   └── review_bot.py        # Shrimp Sheriff: verifies and reviews the briefing
├── src/
│   ├── openai_client.py     # OpenAI Responses API + web search helpers
│   └── telegram_client.py   # Telegram Bot API wrapper
├── .github/
│   └── workflows/
│       ├── daily_news.yml   # 11:00 AM SGT scheduled briefing
│       └── daily_review.yml # 11:05 AM SGT scheduled review
├── .env.example             # Template config, safe to commit
├── .gitignore
├── requirements.txt
├── README.md
└── LICENSE
```

Runtime files:

- `.env` stores local secrets and is ignored by git.
- `data/latest_news_post.json` stores the latest news bot receipt and is ignored by git.

## Bots

### Codex News Bot

`bots/news_bot.py` creates the market brief and sends it to Telegram.

In live mode, it asks OpenAI to search current reliable sources and summarize:

- Global and U.S. market news
- Index, rates, FX, commodities, and tech sector moves
- Premarket or latest major movers
- Earnings, macro, central bank, policy, and geopolitical items
- Tech and AI sector themes
- A short watchlist for the trading day

After posting, it writes `data/latest_news_post.json` with the Singapore date, Telegram message ID, and briefing content.

### Shrimp Sheriff Review Bot

`bots/review_bot.py` checks whether today’s Codex briefing receipt exists. If it does, Shrimp Sheriff reviews the briefing and replies in the Telegram group.

In live mode, Shrimp Sheriff also uses OpenAI web search to verify major claims, missing news, unsupported assertions, and obvious factual problems. The tone is intentionally playful. The job is quality control, not corporate compliance theater.

If Codex never posts, Shrimp Sheriff sends a Chinese missing-report warning to the group.

## Local Setup

Create the bots in BotFather, add both bots to the Telegram group, then install dependencies:

```bash
pip install -r requirements.txt
```

Create local config:

```bash
cp .env.example .env
```

Fill in `.env`:

```env
TELEGRAM_BOT_TOKEN=...
REVIEW_TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.4-mini
ALPHAWIRE_USE_LIVE_OPENAI=false
NEWS_BOT_USERNAME=benYnews_bot
```

Run the news bot:

```bash
python bots/news_bot.py
```

Run the review bot:

```bash
python bots/review_bot.py
```

By default, `ALPHAWIRE_USE_LIVE_OPENAI=false`, so the bots use sample content. This lets you test Telegram delivery without spending OpenAI tokens.

To run live:

```bash
ALPHAWIRE_USE_LIVE_OPENAI=true python bots/news_bot.py
ALPHAWIRE_USE_LIVE_OPENAI=true python bots/review_bot.py
```

## Configuration

Required environment variables:

- `TELEGRAM_BOT_TOKEN`: Token for the Codex news bot.
- `REVIEW_TELEGRAM_BOT_TOKEN`: Token for Shrimp Sheriff.
- `TELEGRAM_CHAT_ID`: Target Telegram group chat ID.
- `OPENAI_API_KEY`: OpenAI API key.
- `OPENAI_MODEL`: OpenAI model, currently `gpt-5.4-mini`.
- `ALPHAWIRE_USE_LIVE_OPENAI`: Set to `true` for live OpenAI calls. Keep `false` for sample-mode testing.
- `NEWS_BOT_USERNAME`: Telegram username of the news bot, currently `benYnews_bot`.

## GitHub Actions

AlphaWire runs from GitHub Actions on the default branch.

| Workflow | Schedule | Singapore Time | Purpose |
| --- | ---: | ---: | --- |
| `daily_news.yml` | `*/5 * * * *` UTC | Every 5 minutes, diagnostic mode | Generate and send the market brief |
| `daily_review.yml` | `25 5 * * *` UTC | 1:25 PM | Verify and review the brief |

Both workflows also support manual runs with `workflow_dispatch`.

Add these repository secrets:

```text
TELEGRAM_BOT_TOKEN
REVIEW_TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
OPENAI_API_KEY
OPENAI_MODEL
NEWS_BOT_USERNAME
```

Add this repository variable:

```text
ALPHAWIRE_USE_LIVE_OPENAI=true
```

If the variable is missing or set to `false`, GitHub Actions will run in sample mode.

## Telegram Reality Check

Telegram bots cannot reliably read another bot’s past messages from group history. AlphaWire avoids that trap by using a receipt handoff:

```text
news_bot.py posts the briefing
news_bot.py saves data/latest_news_post.json
GitHub Actions uploads the receipt
review_bot.py downloads the receipt
Shrimp Sheriff verifies and replies
```

This is why Shrimp Sheriff checks the receipt date instead of pretending to scrape group history.

## Failure Behavior

If OpenAI fails during the news run, Codex sends a Chinese failure alert to the Telegram group.

If OpenAI fails during the review run after a valid briefing receipt is found, Shrimp Sheriff replies:

```text
已找到简报，但本警长今天查不了网，你的token被我吃完啦，Yeehaw~
```

If no valid same-day receipt exists, Shrimp Sheriff sends a playful Chinese missing-report warning and the workflow fails.

## Development Checks

Compile-check the Python entrypoints:

```bash
python -m py_compile bots/news_bot.py bots/review_bot.py src/openai_client.py src/telegram_client.py
```

Run sample-mode locally before live mode:

```bash
python bots/news_bot.py
python bots/review_bot.py
```

Then flip `ALPHAWIRE_USE_LIVE_OPENAI=true` when the Telegram route is confirmed.
