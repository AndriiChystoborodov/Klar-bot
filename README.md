# Klar 💸
### Personal Finance Agent for Telegram

> *"Just tell it what you spent. Get honest analysis. No bank access required."*

Klar is a Telegram bot that helps young professionals and students in expensive cities like Zürich track their spending without connecting a bank account. Log expenses by voice, text, or CSV — get AI-powered monthly analysis and saving tips.

---

## The Problem

Logging expenses manually is too much friction. You open an app, tap through menus, fill in fields. Nobody does it consistently. And even when you do, the app shows you a pie chart with no advice and no answer to the real question: **where did my money actually go and what should I do about it?**

- 60% of Gen Z live paycheck to paycheck *(Deloitte, 2024)*
- Gen Z on average spends nearly 2x what they have in savings *(Bank of America Institute, 2025)*
- Existing apps either require bank access, cost $15/month, or give generic tips that don't apply to your situation

---

## Solution

A Telegram bot that understands natural language in any language, logs your expenses to **your own** Google Sheet automatically, and at the end of the month tells you exactly where your money went and what to do about it.

```
You: "coffee 4.50"
Klar: ✅ Got it! 4.50 CHF · Food & Drink · Today
      April total: 312 CHF
      [ ✅ Yes, log it ]  [ ✏️ Add details ]
```

---

## Features

| Feature | Description |
|---------|-------------|
| 🎤 Voice input | Say what you spent — Whisper transcribes it |
| 💬 Text input | Any language (EN, DE, RU, UA) |
| 📄 CSV upload | Export from your bank — bot categorizes every row |
| 📊 /report | Monthly analysis with patterns + 3 saving tips |
| 💬 Q&A | "How much on food this week?" — bot fetches and answers |
| 🔒 Your data | Stored in your own Google Sheet, not our server |

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Interface | Telegram Bot API + python-telegram-bot | Zero friction, voice built-in, cross-platform |
| AI · Parse | Claude Haiku (Anthropic) | Fast, cheap extraction — ~$0.001/msg |
| AI · Reason | Claude Sonnet (Anthropic) | Deep reasoning for reports and advice |
| Transcription | Whisper API (OpenAI) | $0.0003/msg, multilingual |
| Storage | Google Sheets + gspread | Free, user owns their data |
| Meta storage | SQLite (built-in Python) | User→sheet mapping, bans |
| Deployment | Render (worker) | Free tier, never sleeps |

**No LangChain.** Native Anthropic SDK — routing is deterministic, your code decides what to call.

---

## Architecture

```
User sends message (voice / text / CSV)
         ↓
Security check (rate limit · ban check · SQLite)
         ↓
Detect message type (if/else — NOT LLM)
    voice → Whisper API → text
    CSV   → pandas → rows
    text  → ready
         ↓
Claude Haiku — classify + parse (one call)
returns: {intent: "expense|question|unclear", expenses: [...]}
         ↓
if expense  → validate → confirm → gspread write
if question → sub-classify → fetch slice → Sonnet answer
if /report  → fetch month → Sonnet analysis
if unclear  → friendly fallback, no API called
         ↓
Reply to user via Telegram
```

**Key principle:** Your code orchestrates everything. LLM returns JSON only. It never calls APIs directly.

---

## Setup

### Prerequisites

- Python 3.10+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Anthropic API key
- OpenAI API key (for Whisper)
- Google Service Account with Sheets API enabled

### 1. Clone the repo

```bash
git clone https://github.com/AndriiChystoborodov/Klar-bot.git
cd Klar-bot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=your_token_here
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
ADMIN_TELEGRAM_ID=your_telegram_id
```

### 4. Set up Google Sheets

1. Create a Google Cloud project
2. Enable Google Sheets API
3. Create a Service Account and download `service_account.json`
4. Place `service_account.json` in the project root

### 5. Run locally

```bash
python main.py
```

---

## How to connect your Google Sheet

1. Copy the template sheet: [click here](https://docs.google.com/spreadsheets/d/YOUR_TEMPLATE_ID/copy)
2. Share it with the service account email (find it in `service_account.json` under `client_email`)
3. Give **Editor** access
4. Send the sheet link to the bot after `/start`

---

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Connect your Google Sheet |
| `/help` | Show all commands |
| `/report` | Monthly spending analysis |
| `/budget` | Check remaining budget |
| `/setbudget 2000` | Set monthly budget |
| `/stats` | Quick spending stats |

---

## Security

- All API keys stored in `.env` — never in code
- Rate limiting: auto-bans users who exceed 30 messages/hour or send faster than 3 seconds apart
- Every ban triggers an admin notification
- Financial data never touches the server — stored only in user's own Google Sheet
- Server stores only: `telegram_id → sheet_id` mapping

---

## Definition of Done

- [x] Text + voice parsing works in EN/DE/RU/UA
- [x] Google Sheets logging within 5 seconds
- [x] /report generates monthly analysis + 3 saving tips
- [x] CSV upload categorizes all rows
- [x] Bot handles unexpected input gracefully (never crashes)
- [x] Security: rate limiting + auto-ban
- [x] All API keys in .env
- [x] Deployed on Render (not just local)
- [x] README with setup instructions
- [x] Happy path works 10/10 times

---

## Roadmap

| Priority | Feature |
|----------|---------|
| Should Have | Photo/receipt scanner (Claude Vision) |
| Should Have | Multi-language UI |
| Could Have | Weekly /stats digest |
| Could Have | Budget alerts |
| Won't Have (v2) | Apple Watch native app |
| Won't Have (v2) | Bank integration |
| Won't Have (v2) | Multi-user support |

---

