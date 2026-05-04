from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ADMIN_TELEGRAM_ID
from services import claude, database as db, security, sheets
from services.database import PRESET_ACCOUNTS


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.upsert_user(user.id, user.username)
    context.user_data["awaiting_sheet"] = True

    await update.message.reply_text(
        "Welcome to Klar! 💸\n\n"
        "I help you track expenses without connecting your bank.\n\n"
        "To get started:\n"
        "1. Create a Google Sheet and share it with the bot service account\n"
        "   (Editor access)\n\n"
        "2. Send me the link or ID of your sheet.\n\n"
        "After that you can add accounts: /addaccount"
    )


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*Klar — Personal Finance Bot*\n\n"
        "*Logging expenses:*\n"
        "• Text: `coffee 4.50` or `lunch 23 ZKB`\n"
        "• Voice message 🎤\n"
        "• CSV file 📄\n\n"
        "*Account commands:*\n"
        "/addaccount — Add an account (Cash, ZKB, UBS, Crypto, custom)\n"
        "/accounts — List your accounts\n"
        "/setdefault — Set your default account\n\n"
        "*Other commands:*\n"
        "/report — Monthly spending analysis\n"
        "/budget — Check budget status\n"
        "/setbudget 2000 — Set monthly budget\n"
        "/stats — Quick spending stats\n"
        "/help — Show this message\n\n"
        "*Questions you can ask:*\n"
        "• How much did I spend today?\n"
        "• What did I spend on food this week?\n"
        "• Am I on track with my budget?\n"
        "• Give me saving tips",
        parse_mode="Markdown",
    )


async def handle_addaccount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    ok, reason = security.check_security(user_id)
    if not ok:
        if reason == "banned":
            await update.message.reply_text("⛔ Your account has been suspended.")
        return

    if not db.get_sheet_id(user_id):
        await update.message.reply_text("Please connect your Google Sheet first. Send /start to begin.")
        return

    # If name provided inline: /addaccount ZKB
    if context.args:
        name = context.args[0].strip()
        await _create_account(update, context, user_id, name)
        return

    # Otherwise show preset buttons
    existing = {a["name"].lower() for a in db.get_accounts(user_id)}
    available = [p for p in PRESET_ACCOUNTS if p.lower() not in existing]

    buttons = [[InlineKeyboardButton(p, callback_data=f"addaccount:{p}")] for p in available]
    buttons.append([InlineKeyboardButton("✏️ Custom name", callback_data="addaccount:custom")])

    await update.message.reply_text(
        "Which account do you want to add?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _create_account(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, name: str
) -> None:
    if not name or len(name) > 30:
        await update.message.reply_text("Account name must be 1–30 characters.")
        return

    if db.get_account_by_name(user_id, name):
        await update.message.reply_text(f"You already have an account named '{name}'.")
        return

    sheet_id = db.get_sheet_id(user_id)
    try:
        sheets.ensure_tab(sheet_id, name)
    except Exception as e:
        await update.message.reply_text(f"❌ Could not create tab in your sheet: {e}")
        return

    db.add_account(user_id, name)
    accounts = db.get_accounts(user_id)
    default = db.get_default_account(user_id)

    await update.message.reply_text(
        f"✅ Account *{name}* added!\n"
        + (f"It's your default account." if default and default["name"] == name
           else f"Default is still *{default['name']}*. Use /setdefault to change."),
        parse_mode="Markdown",
    )


async def handle_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    ok, reason = security.check_security(user_id)
    if not ok:
        if reason == "banned":
            await update.message.reply_text("⛔ Your account has been suspended.")
        return

    accounts = db.get_accounts(user_id)
    if not accounts:
        await update.message.reply_text(
            "You have no accounts yet.\nUse /addaccount to add one."
        )
        return

    lines = []
    for a in accounts:
        marker = " ⭐ default" if a["is_default"] else ""
        lines.append(f"• {a['name']}{marker}")

    await update.message.reply_text(
        "*Your accounts:*\n" + "\n".join(lines) + "\n\nUse /setdefault to change default.",
        parse_mode="Markdown",
    )


async def handle_setdefault(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    ok, reason = security.check_security(user_id)
    if not ok:
        if reason == "banned":
            await update.message.reply_text("⛔ Your account has been suspended.")
        return

    accounts = db.get_accounts(user_id)
    if not accounts:
        await update.message.reply_text("You have no accounts yet. Use /addaccount first.")
        return

    # If name provided inline: /setdefault ZKB
    if context.args:
        name = context.args[0].strip()
        if db.set_default_account(user_id, name):
            await update.message.reply_text(f"✅ *{name}* is now your default account.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"No account named '{name}'. Use /accounts to see your accounts.")
        return

    buttons = [
        [InlineKeyboardButton(
            a["name"] + (" ⭐" if a["is_default"] else ""),
            callback_data=f"setdefault:{a['name']}"
        )]
        for a in accounts
    ]
    await update.message.reply_text(
        "Which account should be the default?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def handle_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    ok, reason = security.check_security(user_id)
    if not ok:
        if reason == "banned":
            await update.message.reply_text("⛔ Your account has been suspended.")
        return

    sheet_id = db.get_sheet_id(user_id)
    if not sheet_id:
        await update.message.reply_text("Please connect your Google Sheet first. Send /start to begin.")
        return

    account = db.get_default_account(user_id)
    if not account:
        await update.message.reply_text("Please add an account first. Use /addaccount.")
        return

    await update.message.reply_text(f"⏳ Generating report for *{account['name']}*...", parse_mode="Markdown")

    try:
        rows = sheets.get_monthly_rows(sheet_id, account["name"])
    except Exception as e:
        await update.message.reply_text(f"❌ Could not read your sheet: {e}")
        return

    if not rows:
        await update.message.reply_text(f"No expenses found this month in *{account['name']}*.", parse_mode="Markdown")
        return

    summary = sheets.get_monthly_summary(sheet_id, account["name"])
    summary["budget"] = db.get_budget(user_id)

    monthly_income = sheets.get_monthly_income(sheet_id)
    balance = monthly_income - summary["total"]
    balance_emoji = "✅" if balance >= 0 else "❌"

    analysis = claude.generate_monthly_report(summary)

    by_cat_lines = "\n".join(
        f"  {cat}: {amt:.2f} CHF"
        for cat, amt in sorted(summary["by_category"].items(), key=lambda x: -x[1])
    )

    await update.message.reply_text(
        f"📊 *{summary['month']} — {account['name']}*\n\n"
        f"💰 Income: *{monthly_income:.2f} CHF*\n"
        f"💸 Expenses: *{summary['total']:.2f} CHF*\n"
        f"{balance_emoji} Balance: *{balance:.2f} CHF*\n"
        f"Transactions: {summary['transaction_count']}\n\n"
        f"*By category:*\n{by_cat_lines}\n\n"
        + analysis,
        parse_mode="Markdown",
    )


async def handle_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    ok, reason = security.check_security(user_id)
    if not ok:
        if reason == "banned":
            await update.message.reply_text("⛔ Your account has been suspended.")
        return

    sheet_id = db.get_sheet_id(user_id)
    budget = db.get_budget(user_id)

    if not budget:
        await update.message.reply_text("You haven't set a budget yet.\nTry: /setbudget 2000")
        return

    account = db.get_default_account(user_id)
    if not account or not sheet_id:
        await update.message.reply_text("Please connect your sheet and add an account first.")
        return

    try:
        rows = sheets.get_monthly_rows(sheet_id, account["name"])
    except Exception as e:
        await update.message.reply_text(f"❌ Could not read your sheet: {e}")
        return

    spent = sum(float(r.get("Amount", 0)) for r in rows)
    remaining = budget - spent
    pct = (spent / budget) * 100
    emoji = "✅" if remaining >= 0 else "❌"

    await update.message.reply_text(
        f"📊 *{account['name']}* budget\n\n"
        f"Budget: {budget:.0f} CHF\n"
        f"💸 Spent: {spent:.0f} CHF ({pct:.0f}%)\n"
        f"{emoji} {'Remaining' if remaining >= 0 else 'Over budget by'}: {abs(remaining):.0f} CHF",
        parse_mode="Markdown",
    )


async def handle_setbudget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    ok, reason = security.check_security(user_id)
    if not ok:
        if reason == "banned":
            await update.message.reply_text("⛔ Your account has been suspended.")
        return

    try:
        amount = float(context.args[0])
        if amount <= 0:
            raise ValueError
        db.upsert_user(user_id, update.effective_user.username)
        db.set_budget(user_id, amount)
        await update.message.reply_text(f"✅ Monthly budget set: {amount:.0f} CHF")
    except (IndexError, ValueError, TypeError):
        await update.message.reply_text("Usage: /setbudget 2000")


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    ok, reason = security.check_security(user_id)
    if not ok:
        if reason == "banned":
            await update.message.reply_text("⛔ Your account has been suspended.")
        return

    sheet_id = db.get_sheet_id(user_id)
    account = db.get_default_account(user_id)

    if not sheet_id or not account:
        await update.message.reply_text("Please connect your sheet and add an account first.")
        return

    try:
        today_rows = sheets.get_rows_for_period(sheet_id, account["name"], "today")
        week_rows = sheets.get_rows_for_period(sheet_id, account["name"], "week")
        month_rows = sheets.get_monthly_rows(sheet_id, account["name"])
    except Exception as e:
        await update.message.reply_text(f"❌ Could not read your sheet: {e}")
        return

    today_total = sum(float(r.get("Amount", 0)) for r in today_rows)
    week_total = sum(float(r.get("Amount", 0)) for r in week_rows)
    month_total = sum(float(r.get("Amount", 0)) for r in month_rows)

    await update.message.reply_text(
        f"📈 *{account['name']} — spending stats*\n\n"
        f"Today: *{today_total:.2f} CHF* ({len(today_rows)} transactions)\n"
        f"This week: *{week_total:.2f} CHF* ({len(week_rows)} transactions)\n"
        f"This month: *{month_total:.2f} CHF* ({len(month_rows)} transactions)",
        parse_mode="Markdown",
    )


async def handle_banned(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        return

    banned = db.get_all_banned()
    if not banned:
        await update.message.reply_text("No banned users.")
        return

    text = "⛔ Banned users:\n\n"
    for u in banned:
        text += f"• {u['telegram_id']} (@{u.get('username', 'unknown')}) — {u['banned_at']}\n"
    text += "\nUse /unban [id] to restore"
    await update.message.reply_text(text)


async def handle_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        return

    try:
        target_id = int(context.args[0])
        db.unban_user(target_id)
        await update.message.reply_text(f"✅ User {target_id} unbanned.")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /unban 123456789")
