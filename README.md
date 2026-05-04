# Klar 💸
### Personal Finance Agent for Telegram

> *"Just tell it what you spent. Get honest analysis. No bank access required."*

Klar is a Telegram bot that helps peoples track their spending without connecting a bank account. Log expenses by voice, text, or CSV — get AI-powered monthly analysis and saving tips.

---

## The Problem

Logging expenses manually is too much friction. You open an app, tap through menus, fill in fields. Nobody does it consistently. And even when you do, the app shows you a pie chart with no advice and no answer to the real question: **where did my money actually go and what should I do about it?**

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
| 💬 Text input | language (EN, DE, RU, UA) |
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

---

## Setup

## For Users
Just open Telegram and start chatting:
👉 t.me/Klar_budget_bot

## For Devs
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

1. Copy the template sheet: [click here](https://docs.google.com/spreadsheets/d/1gJL07L_oowC7PIFhm6xm3KasJIUOisUDzzE5RR_XFiQ/edit?gid=1962169306#gid=1962169306)
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
 Must Have ( MVP )
- [ ] User sends text in any language (EN/DE/RU/UA) → expense parsed correctly and appears in Google Sheets
- [x] User sends voice message → transcribed by Whisper → parsed → logged
- [ ] User uploads CSV bank export → all rows categorized and batch-written to Sheets ( Before logging, it checks for duplicates )
- [x] /report generates monthly analysis with spending patterns and concrete saving tips in CHF
- [ ] Bot handles unexpected input gracefully (never crashes)
- [ ] Security: rate limiting + auto-ban
- [x] README with setup instructions
- [x] Default account selection
- [ ] Multi-account setup
---

## Roadmap

| Priority | Feature |
|----------|---------|
| Must Have | text and voice parsing |
| Must Have | Google Sheets logging |
| Must Have | Default account selection|
| Must Have | Multi-account setup (Cash, ZKB, UBS, Crypto + custom)
| Must Have | /report command |
| Must Have | CSV upload |
| Should Have | Photo/receipt scanner |
| Should Have | Multi-language UI |
| Should Have | Transfer between accounts (/transfer) |
| Should Have | Weekly /stats digest |
| Should Have | /set the budget |
| Could Have | monthly budget limits with alerts |
| Could Have | AI suggestions how to set a budget wtih yr Income |
| Won't Have (v2) | Apple Watch native app |
| Won't Have (v2) | Bank integration |
| Won't Have (v2) | Multi-user support |


