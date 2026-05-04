import io
import re
from datetime import datetime
from typing import List, Optional

import pandas as pd
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import CATEGORIES
from services import claude, database as db, security, sheets, whisper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_sheet_id(text: str) -> Optional[str]:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", text)
    if match:
        return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{40,60}", text.strip()):
        return text.strip()
    return None


def _detect_account(text: str, accounts: List[dict]) -> Optional[dict]:
    """Return the account whose name appears in the text, or None."""
    text_lower = text.lower()
    for acc in accounts:
        if acc["name"].lower() in text_lower:
            return acc
    return None


def validate_expense(expense: dict) -> tuple:
    amount = expense.get("amount")
    if not isinstance(amount, (int, float)) or amount is None:
        return False, "no amount"
    if amount <= 0:
        return False, "amount must be positive"
    if amount > 50000:
        return False, f"amount {amount} seems unusually high"

    raw_date = expense.get("date", "")
    try:
        parsed = datetime.strptime(raw_date, "%Y-%m-%d")
        if parsed > datetime.now():
            expense["date"] = datetime.now().strftime("%Y-%m-%d")
        if parsed.year < 2020:
            expense["date"] = datetime.now().strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        expense["date"] = datetime.now().strftime("%Y-%m-%d")

    if expense.get("category") not in CATEGORIES:
        expense["category"] = "Other"

    return True, "ok"


def _build_confirmation(expenses: List[dict], account_name: str) -> tuple:
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Log it" if len(expenses) == 1 else "✅ Log all",
                callback_data="confirm_expenses",
            ),
            InlineKeyboardButton("✏️ Edit", callback_data="edit_expense"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_expenses"),
        ]
    ])

    if len(expenses) == 1:
        e = expenses[0]
        date_label = "Today" if e["date"] == datetime.now().strftime("%Y-%m-%d") else e["date"]
        text = (
            f"Got it! Just to confirm:\n\n"
            f"💸 {e['amount']:.2f} CHF\n"
            f"📂 {e.get('category', 'Other')}\n"
            f"📅 {date_label}\n"
            f"📝 {e.get('description', '')}\n"
            f"🏦 {account_name}"
        )
    else:
        lines = [
            f"💸 {e['amount']:.2f} CHF · {e.get('category', 'Other')} · {e.get('description', '')}"
            for e in expenses
        ]
        total = sum(e["amount"] for e in expenses)
        text = (
            f"Got it! I found {len(expenses)} expenses:\n\n"
            + "\n".join(lines)
            + f"\n{'─' * 25}\nTotal: {total:.2f} CHF\n🏦 {account_name}"
        )

    return text, keyboard


async def _show_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    expenses: List[dict],
    account: dict,
) -> None:
    context.user_data["pending_expenses"] = expenses
    context.user_data["pending_account"] = account
    text, keyboard = _build_confirmation(expenses, account["name"])
    await update.message.reply_text(text, reply_markup=keyboard)


# ---------------------------------------------------------------------------
# CSV handling
# ---------------------------------------------------------------------------

async def _handle_csv(update: Update, context: ContextTypes.DEFAULT_TYPE, account: dict) -> None:
    doc = update.message.document
    file = await doc.get_file()
    buf = io.BytesIO()
    await file.download_to_memory(buf)
    buf.seek(0)

    try:
        df = pd.read_csv(buf)
    except Exception:
        await update.message.reply_text("❌ Couldn't parse that CSV. Make sure it's a valid file.")
        return

    df.columns = [c.strip().lower() for c in df.columns]

    expenses = []
    for _, row in df.iterrows():
        amount = row.get("amount") or row.get("amount (chf)") or row.get("chf")
        category = str(row.get("category", "Other")).strip()
        description = str(row.get("description", row.get("desc", ""))).strip()
        date = str(row.get("date", datetime.now().strftime("%Y-%m-%d"))).strip()

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            continue

        exp = {
            "amount": amount,
            "category": category if category in CATEGORIES else "Other",
            "description": description,
            "date": date,
            "source": "csv",
        }
        valid, _ = validate_expense(exp)
        if valid:
            expenses.append(exp)

    if not expenses:
        await update.message.reply_text(
            "❌ No valid expenses found in the CSV.\n"
            "Expected columns: Date, Amount, Category, Description"
        )
        return

    # Duplicate check
    sheet_id = db.get_sheet_id(update.effective_user.id)
    try:
        new, dupes = sheets.filter_duplicates(sheet_id, account["name"], expenses)
    except Exception:
        new, dupes = expenses, []

    dupe_note = f"\n⚠️ {len(dupes)} duplicate(s) skipped." if dupes else ""

    if not new:
        await update.message.reply_text(
            f"All {len(dupes)} rows already exist in your sheet — nothing to log."
        )
        return

    await _show_confirmation(update, context, new, account)
    if dupe_note:
        await update.message.reply_text(dupe_note)


# ---------------------------------------------------------------------------
# Q&A handling
# ---------------------------------------------------------------------------

async def _handle_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    user_id: int,
    account: dict,
) -> None:
    sheet_id = db.get_sheet_id(user_id)

    await update.message.reply_text("🔍 Checking your data...")

    try:
        rows = sheets.get_all_rows(sheet_id, account["name"])
    except Exception as e:
        await update.message.reply_text(f"❌ Could not read your sheet: {e}")
        return

    try:
        result = claude.answer_with_data(text, rows)
    except Exception as e:
        await update.message.reply_text(f"❌ Couldn't answer that: {e}")
        return

    action = result.get("action")

    if action == "answer":
        await update.message.reply_text(result.get("text", "No answer."))

    elif action == "edit":
        context.user_data["pending_sheet_edit"] = {
            "row_index": result.get("row_index"),
            "field": result.get("field"),
            "new_value": result.get("new_value"),
            "sheet_id": sheet_id,
            "tab_name": account["name"],
        }
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Confirm", callback_data="confirm_sheet_edit"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_sheet_edit"),
        ]])
        await update.message.reply_text(
            result.get("confirmation_text", "Apply this change?"),
            reply_markup=keyboard,
        )

    else:
        await update.message.reply_text("❌ Unexpected response. Please try again.")


# ---------------------------------------------------------------------------
# Main message handler
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id

    ok, reason = security.check_security(user_id)
    if not ok:
        if reason == "banned":
            await update.message.reply_text("⛔ Your account has been suspended.")
        return

    # Custom account name input (after tapping "Custom name" button)
    if context.user_data.get("awaiting_custom_account"):
        name = (update.message.text or "").strip()
        if not name or len(name) > 30:
            await update.message.reply_text("Account name must be 1–30 characters. Try again:")
            return
        context.user_data.pop("awaiting_custom_account", None)

        sheet_id = db.get_sheet_id(user_id)
        if db.get_account_by_name(user_id, name):
            await update.message.reply_text(f"You already have an account named '{name}'.")
            return
        try:
            sheets.ensure_tab(sheet_id, name)
        except Exception as e:
            await update.message.reply_text(f"❌ Could not create tab in your sheet: {e}")
            return
        db.add_account(user_id, name)
        default = db.get_default_account(user_id)
        await update.message.reply_text(
            f"✅ Account *{name}* added!\n"
            + (
                "It's your default account."
                if default and default["name"] == name
                else f"Default is *{default['name']}*. Use /setdefault to change."
            ),
            parse_mode="Markdown",
        )
        return

    # Field edit: user sent a new value for a specific field
    if context.user_data.get("awaiting_field_edit"):
        field = context.user_data.pop("awaiting_field_edit")
        pending = context.user_data.get("pending_expenses", [])
        account = context.user_data.get("pending_account")
        text_in = (update.message.text or "").strip()

        if pending and account and text_in:
            e = pending[0]
            if field == "amount":
                try:
                    e["amount"] = float(text_in.replace(",", "."))
                except ValueError:
                    await update.message.reply_text("Invalid amount. Send a number like `12.50`.", parse_mode="Markdown")
                    context.user_data["awaiting_field_edit"] = field
                    return
            elif field == "description":
                e["description"] = text_in
            elif field == "date":
                try:
                    e["date"] = datetime.strptime(text_in, "%d.%m.%Y").strftime("%Y-%m-%d")
                except ValueError:
                    await update.message.reply_text("Invalid date. Use format `28.04.2026`.", parse_mode="Markdown")
                    context.user_data["awaiting_field_edit"] = field
                    return

            pending[0] = e
            context.user_data["pending_expenses"] = pending

            from handlers.callbacks import _confirmation_keyboard, _format_expense
            await update.message.reply_text(
                f"Got it! Just to confirm:\n\n{_format_expense(e, account['name'])}",
                reply_markup=_confirmation_keyboard(),
            )
        return

    # Onboarding: waiting for Google Sheet link/ID
    if context.user_data.get("awaiting_sheet"):
        text = (update.message.text or "").strip()
        sheet_id = _extract_sheet_id(text)
        if sheet_id:
            db.upsert_user(user_id, user.username)
            db.set_sheet_id(user_id, sheet_id)
            context.user_data.pop("awaiting_sheet", None)

            await update.message.reply_text(
                "✅ Sheet connected!\n\n"
                "Now add your first account:\n"
                "/addaccount — choose from Cash, ZKB, UBS, Crypto or enter a custom name"
            )
        else:
            await update.message.reply_text(
                "I need your Google Sheet link or ID.\n"
                "It looks like: https://docs.google.com/spreadsheets/d/YOUR_ID/edit"
            )
        return

    if not db.get_sheet_id(user_id):
        await update.message.reply_text(
            "Please set up your Google Sheet first.\nSend /start to begin."
        )
        return

    # Resolve account — detect from text or use default
    accounts = db.get_accounts(user_id)
    if not accounts:
        await update.message.reply_text(
            "Please add an account first.\nUse /addaccount."
        )
        return

    message = update.message
    raw_text = message.text or ""

    detected_account = _detect_account(raw_text, accounts)
    account = detected_account or db.get_default_account(user_id)

    # Voice
    if message.voice:
        await message.reply_text("🎤 Transcribing...")
        try:
            text = await whisper.transcribe(message.voice)
        except Exception as e:
            await message.reply_text(f"❌ Could not transcribe audio: {e}")
            return
        await _process_text(update, context, text, user_id, account, source="voice")
        return

    # CSV
    if message.document:
        mime = message.document.mime_type or ""
        if "csv" in mime or (message.document.file_name or "").endswith(".csv"):
            await _handle_csv(update, context, account)
        else:
            await message.reply_text("Please send a CSV file to import expenses.")
        return

    # Plain text
    if message.text:
        await _process_text(update, context, message.text, user_id, account, source="text")
        return

    await message.reply_text("I can handle voice messages, text, or CSV files.")


async def _process_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    user_id: int,
    account: dict,
    source: str = "text",
) -> None:
    try:
        result = claude.classify_and_parse(text)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Claude error: {e}")
        await update.message.reply_text(f"❌ Couldn't process that: {e}")
        return

    intent = result.get("intent")

    if intent == "income":
        incomes = result.get("incomes", [])
        valid = [i for i in incomes if isinstance(i.get("amount"), (int, float)) and i["amount"] > 0]
        if not valid:
            await update.message.reply_text("I couldn't understand that as income. Try: 'received 2000 salary'")
            return
        for i in valid:
            if not i.get("date"):
                i["date"] = datetime.now().strftime("%Y-%m-%d")
            if not i.get("source"):
                i["source"] = "Other"
        context.user_data["pending_income"] = valid
        context.user_data["pending_account"] = account

        lines = [f"💰 {i['amount']:.2f} · {i['source']} · {i.get('description', '')}" for i in valid]
        total = sum(i["amount"] for i in valid)
        text = (
            f"Income — confirm?\n\n" + "\n".join(lines) +
            f"\n{'─'*25}\nTotal: {total:.2f}\n🏦 {account['name']}"
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Log income", callback_data="confirm_income"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_expenses"),
        ]])
        await update.message.reply_text(text, reply_markup=keyboard)
        return

    if intent == "expense":
        expenses = result.get("expenses", [])
        valid = []
        for e in expenses:
            e["source"] = source
            ok, _ = validate_expense(e)
            if ok:
                valid.append(e)

        if not valid:
            await update.message.reply_text(
                "I couldn't understand that as an expense.\n"
                "Try: 'coffee 4.50' or send a voice message 🎤"
            )
            return

        await _show_confirmation(update, context, valid, account)

    elif intent == "question":
        await _handle_question(update, context, text, user_id, account)

    else:
        await update.message.reply_text(
            "I didn't understand that.\n\n"
            "Try:\n"
            "• 'coffee 4.50' to log an expense\n"
            "• 'coffee 4.50 ZKB' to log to a specific account\n"
            "• 'how much did I spend today?' to check spending\n"
            "• /report for monthly analysis\n"
            "• /help for all commands"
        )
