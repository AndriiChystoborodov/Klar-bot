from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import CATEGORIES
from services import database as db, sheets


def _confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Log it", callback_data="confirm_expenses"),
        InlineKeyboardButton("✏️ Edit", callback_data="edit_expense"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_expenses"),
    ]])


def _edit_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💸 Amount", callback_data="edit_field:amount"),
            InlineKeyboardButton("📂 Category", callback_data="edit_field:category"),
        ],
        [
            InlineKeyboardButton("📝 Description", callback_data="edit_field:description"),
            InlineKeyboardButton("📅 Date", callback_data="edit_field:date"),
        ],
        [InlineKeyboardButton("✅ Log it", callback_data="confirm_expenses")],
    ])


def _format_expense(e: dict, account_name: str) -> str:
    date_label = "Today" if e.get("date") == datetime.now().strftime("%Y-%m-%d") else e.get("date", "")
    return (
        f"💸 {e.get('amount', 0):.2f} CHF\n"
        f"📂 {e.get('category', 'Other')}\n"
        f"📝 {e.get('description', '')}\n"
        f"📅 {date_label}\n"
        f"🏦 {account_name}"
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = update.effective_user.id

    # ------------------------------------------------------------------
    # Expense confirmation
    # ------------------------------------------------------------------
    if data == "confirm_expenses":
        pending = context.user_data.get("pending_expenses", [])
        account = context.user_data.get("pending_account")

        if not pending or not account:
            await query.edit_message_text("No pending expenses found.")
            return

        sheet_id = db.get_sheet_id(user_id)
        if not sheet_id:
            await query.edit_message_text("Sheet not connected. Send /start to begin.")
            return

        try:
            sheets.write_expenses(sheet_id, account["name"], pending)
        except Exception as e:
            await query.edit_message_text(f"❌ Failed to save to sheet: {e}")
            return

        context.user_data.pop("pending_expenses", None)
        context.user_data.pop("pending_account", None)

        count = len(pending)
        total = sum(e["amount"] for e in pending)
        await query.edit_message_text(
            f"✅ Logged {count} expense{'s' if count > 1 else ''} to *{account['name']}*!\n"
            f"Total: {total:.2f} CHF\n\n"
            f"Use /stats to see your spending or /report for monthly analysis.",
            parse_mode="Markdown",
        )

    # ------------------------------------------------------------------
    # Income confirmation
    # ------------------------------------------------------------------
    elif data == "confirm_income":
        pending = context.user_data.get("pending_income", [])
        account = context.user_data.get("pending_account")
        if not pending or not account:
            await query.edit_message_text("No pending income found.")
            return
        sheet_id = db.get_sheet_id(user_id)
        try:
            sheets.write_income(sheet_id, account["name"], pending)
        except Exception as e:
            await query.edit_message_text(f"❌ Failed to save income: {e}")
            return
        context.user_data.pop("pending_income", None)
        context.user_data.pop("pending_account", None)
        total = sum(i["amount"] for i in pending)
        await query.edit_message_text(
            f"✅ Income logged!\nTotal: {total:.2f}\n\nUse /report to see your balance.",
        )

    # ------------------------------------------------------------------
    # Edit expense — show field menu
    # ------------------------------------------------------------------
    elif data == "edit_expense":
        pending = context.user_data.get("pending_expenses", [])
        account = context.user_data.get("pending_account")
        if not pending or not account:
            await query.edit_message_text("Nothing to edit.")
            return
        e = pending[0]
        await query.edit_message_text(
            f"What do you want to change?\n\n{_format_expense(e, account['name'])}",
            reply_markup=_edit_menu_keyboard(),
        )

    # ------------------------------------------------------------------
    # Edit specific field
    # ------------------------------------------------------------------
    elif data.startswith("edit_field:"):
        field = data.split(":", 1)[1]

        if field == "category":
            buttons = [
                [InlineKeyboardButton(cat, callback_data=f"set_category:{cat}")]
                for cat in CATEGORIES
            ]
            await query.edit_message_text(
                "Choose a category:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return

        prompts = {
            "amount": "Send the new amount (e.g. `12.50`):",
            "description": "Send the new description:",
            "date": "Send the new date (e.g. `28.04.2026`):",
        }
        context.user_data["awaiting_field_edit"] = field
        await query.edit_message_text(prompts[field], parse_mode="Markdown")

    # ------------------------------------------------------------------
    # Set category via button
    # ------------------------------------------------------------------
    elif data.startswith("set_category:"):
        category = data.split(":", 1)[1]
        pending = context.user_data.get("pending_expenses", [])
        account = context.user_data.get("pending_account")
        if not pending or not account:
            await query.edit_message_text("Nothing to edit.")
            return
        pending[0]["category"] = category
        context.user_data["pending_expenses"] = pending
        await query.edit_message_text(
            f"Got it! Just to confirm:\n\n{_format_expense(pending[0], account['name'])}",
            reply_markup=_confirmation_keyboard(),
        )

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------
    elif data == "cancel_expenses":
        context.user_data.pop("pending_expenses", None)
        context.user_data.pop("pending_account", None)
        await query.edit_message_text("Cancelled. Nothing was logged.")

    # ------------------------------------------------------------------
    # Sheet row edit (from Q&A)
    # ------------------------------------------------------------------
    elif data == "confirm_sheet_edit":
        edit = context.user_data.pop("pending_sheet_edit", None)
        if not edit:
            await query.edit_message_text("Nothing to edit.")
            return
        try:
            tab_names = edit.get("tab_names") or [edit.get("tab_name")]
            found_any = False
            for tab in tab_names:
                found = sheets.find_and_update_row(
                    edit["sheet_id"],
                    tab,
                    edit["match_date"],
                    edit["match_amount"],
                    edit["match_description"],
                    edit["field"],
                    edit["new_value"],
                )
                if found:
                    found_any = True
            if found_any:
                await query.edit_message_text("✅ Updated in your sheet.")
            else:
                await query.edit_message_text("❌ Couldn't find that transaction in your sheet.")
        except Exception as e:
            await query.edit_message_text(f"❌ Failed to update: {e}")

    elif data == "cancel_sheet_edit":
        context.user_data.pop("pending_sheet_edit", None)
        await query.edit_message_text("Cancelled. Nothing was changed.")

    # ------------------------------------------------------------------
    # Add account
    # ------------------------------------------------------------------
    elif data.startswith("addaccount:"):
        name = data.split(":", 1)[1]
        if name == "custom":
            context.user_data["awaiting_custom_account"] = True
            await query.edit_message_text(
                "Send me the name for your custom account (e.g. 'Revolut', 'Savings'):"
            )
            return
        await _do_add_account(query, user_id, name)

    # ------------------------------------------------------------------
    # Set default account
    # ------------------------------------------------------------------
    elif data.startswith("setdefault:"):
        name = data.split(":", 1)[1]
        if db.set_default_account(user_id, name):
            await query.edit_message_text(
                f"✅ *{name}* is now your default account.", parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(f"Account '{name}' not found.")


async def _do_add_account(query, user_id: int, name: str) -> None:
    if db.get_account_by_name(user_id, name):
        await query.edit_message_text(f"You already have an account named '{name}'.")
        return

    sheet_id = db.get_sheet_id(user_id)
    try:
        sheets.ensure_tab(sheet_id, name)
    except Exception as e:
        await query.edit_message_text(f"❌ Could not create tab in your sheet: {e}")
        return

    db.add_account(user_id, name)
    default = db.get_default_account(user_id)

    await query.edit_message_text(
        f"✅ Account *{name}* added!\n"
        + (
            "It's your default account."
            if default and default["name"] == name
            else f"Default is *{default['name']}*. Use /setdefault to change."
        ),
        parse_mode="Markdown",
    )
