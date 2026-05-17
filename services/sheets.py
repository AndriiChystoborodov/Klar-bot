from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import gspread

from config import GOOGLE_SERVICE_ACCOUNT_JSON, EXPENSES_TAB, INCOME_TAB, MONTHLY_OVERVIEW_TAB

# Matches the user's existing Expenses sheet structure
HEADERS = ["Timestamp", "Purchase Date", "Item", "Amount", "Category", "Account"]

# Matches the user's existing Income sheet structure
INCOME_HEADERS = ["Timestamp", "Date", "Income Source", "Description/Invoice No.", "Income Amount", "Account"]


def _gc():
    return gspread.service_account(filename=GOOGLE_SERVICE_ACCOUNT_JSON)


def _open_tab(sheet_id: str, tab_name: str):
    gc = _gc()
    spreadsheet = gc.open_by_key(sheet_id)
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=10)
        ws.insert_row(HEADERS, 1)
    return ws


def ensure_tab(sheet_id: str, tab_name: str) -> None:
    _open_tab(sheet_id, tab_name)


def _fmt_date(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return date_str


def _build_rows(expenses: List[Dict], account_name: str) -> List[List]:
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    return [
        [now, _fmt_date(e["date"]), e.get("description", ""), e["amount"], e.get("category", "Other"), account_name]
        for e in expenses
    ]


def write_expenses(sheet_id: str, account_name: str, expenses: List[Dict]) -> None:
    """Write to the account tab AND to the shared Expenses tab."""
    rows = _build_rows(expenses, account_name)

    # Write to account-specific tab
    ws_account = _open_tab(sheet_id, account_name)
    ws_account.append_rows(rows, value_input_option="USER_ENTERED")

    # Write to shared Expenses tab
    ws_expenses = _open_tab(sheet_id, EXPENSES_TAB)
    ws_expenses.append_rows(rows, value_input_option="USER_ENTERED")


def _to_iso(date_str: str) -> str:
    """Convert dd.mm.yyyy or dd/mm/yyyy to yyyy-mm-dd for comparison."""
    s = str(date_str).strip()
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def get_all_rows(sheet_id: str, tab_name: str) -> List[Dict]:
    ws = _open_tab(sheet_id, tab_name)
    return ws.get_all_records()


def _latest_month_with_data(rows: List[Dict]) -> str:
    """Return the most recent yyyy-mm that has data, falling back from current month."""
    months = set()
    for r in rows:
        iso = _to_iso(r.get("Purchase Date", ""))
        if len(iso) >= 7:
            months.add(iso[:7])
    if not months:
        return datetime.now().strftime("%Y-%m")
    current = datetime.now().strftime("%Y-%m")
    # Prefer current month; if not present, use the latest available
    return current if current in months else max(months)


def get_monthly_rows(sheet_id: str, tab_name: str) -> Tuple[List[Dict], str]:
    """Returns (rows, month_label). Falls back to latest month with data if current month is empty."""
    rows = get_all_rows(sheet_id, tab_name)
    month = _latest_month_with_data(rows)
    return [r for r in rows if _to_iso(r.get("Purchase Date", "")).startswith(month)], month


def get_rows_for_period(sheet_id: str, tab_name: str, period: str) -> List[Dict]:
    now = datetime.now()
    rows = get_all_rows(sheet_id, tab_name)

    if period == "today":
        target = now.strftime("%Y-%m-%d")
        return [r for r in rows if _to_iso(r.get("Purchase Date", "")) == target]

    if period == "week":
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        return [r for r in rows if _to_iso(r.get("Purchase Date", "")) >= week_ago]

    # month: fall back to latest month with data
    month = _latest_month_with_data(rows)
    return [r for r in rows if _to_iso(r.get("Purchase Date", "")).startswith(month)]


def get_monthly_summary(sheet_id: str, tab_name: str) -> Dict:
    rows, month = get_monthly_rows(sheet_id, tab_name)
    total = sum(float(r.get("Amount", 0)) for r in rows)
    by_category: Dict[str, float] = {}
    for r in rows:
        cat = r.get("Category", "Other")
        by_category[cat] = round(by_category.get(cat, 0) + float(r.get("Amount", 0)), 2)

    try:
        month_label = datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    except ValueError:
        month_label = month

    return {
        "total": round(total, 2),
        "by_category": by_category,
        "transaction_count": len(rows),
        "month": month_label,
    }


def write_income(sheet_id: str, account_name: str, incomes: List[Dict]) -> None:
    """Write income entries to the Income tab (matches existing sheet structure)."""
    ws = _open_tab_with_headers(sheet_id, INCOME_TAB, INCOME_HEADERS)
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    rows = [
        [now, _fmt_date(inc["date"]), inc["source"], inc.get("description", ""), inc["amount"], account_name]
        for inc in incomes
    ]
    ws.append_rows(rows, value_input_option="USER_ENTERED")


def get_monthly_income(sheet_id: str) -> float:
    """Sum of all income this month from the Income tab."""
    try:
        ws = _open_tab_with_headers(sheet_id, INCOME_TAB, INCOME_HEADERS)
        rows = ws.get_all_records()
    except Exception:
        return 0.0
    current_month = datetime.now().strftime("%Y-%m")
    total = 0.0
    for r in rows:
        date_val = str(r.get("Date", ""))
        # Handle dd.mm.yyyy format from existing data
        if "." in date_val:
            try:
                parts = date_val.split(".")
                date_val = f"{parts[2]}-{parts[1]}-{parts[0]}"
            except Exception:
                pass
        if date_val.startswith(current_month):
            try:
                amt = str(r.get("Income Amount", "0")).replace("$", "").replace(",", "")
                total += float(amt)
            except (ValueError, TypeError):
                pass
    return round(total, 2)


def _open_tab_with_headers(sheet_id: str, tab_name: str, headers: List[str]):
    gc = _gc()
    spreadsheet = gc.open_by_key(sheet_id)
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=10)
        ws.insert_row(headers, 1)
    return ws


def update_row(sheet_id: str, tab_name: str, row_index: int, field: str, new_value) -> None:
    """Update a single cell. row_index is 0-based (excluding header row)."""
    ws = _open_tab(sheet_id, tab_name)
    col = HEADERS.index(field) + 1  # 1-based column
    sheet_row = row_index + 2       # +1 for header, +1 for 1-based
    ws.update_cell(sheet_row, col, new_value)


def find_and_update_row(
    sheet_id: str, tab_name: str,
    match_date: str, match_amount: float, match_description: str,
    field: str, new_value,
) -> bool:
    """Find a row by date+amount+description and update a single field.
    Returns True if a matching row was found and updated."""
    ws = _open_tab(sheet_id, tab_name)
    all_values = ws.get_all_values()
    if not all_values:
        return False

    headers = [h.strip() for h in all_values[0]]
    try:
        col_idx = headers.index(field) + 1  # 1-based
        date_col = headers.index("Purchase Date")
        amount_col = headers.index("Amount")
        desc_col = headers.index("Item")
    except ValueError:
        return False

    target_date = _to_iso(match_date)
    target_amount = round(float(match_amount), 2)

    for i, row in enumerate(all_values[1:], start=2):  # start=2: 1-based, skip header
        row_date = _to_iso(str(row[date_col]).strip()) if date_col < len(row) else ""
        try:
            row_amount = round(float(row[amount_col]), 2) if amount_col < len(row) else -1
        except (ValueError, TypeError):
            row_amount = -1

        if row_date == target_date and row_amount == target_amount:
            ws.update_cell(i, col_idx, new_value)
            return True

    return False


def _build_existing_keys(sheet_id: str, tab_name: str) -> set:
    """Read a tab and return a set of (iso_date, rounded_amount) keys."""
    try:
        rows = get_all_rows(sheet_id, tab_name)
    except Exception:
        return set()
    return {
        (_to_iso(str(r.get("Purchase Date", ""))), round(float(r.get("Amount", 0) or 0), 2))
        for r in rows
        if r.get("Purchase Date") and r.get("Amount")
    }


def filter_duplicates(
    sheet_id: str, tab_name: str, expenses: List[Dict]
) -> Tuple[List[Dict], List[Dict]]:
    """Return (new_expenses, duplicates).
    Checks BOTH the account tab and the shared Expenses tab so deleting
    from either one is enough to mark the transaction as new."""
    keys = _build_existing_keys(sheet_id, tab_name)
    if tab_name != EXPENSES_TAB:
        keys |= _build_existing_keys(sheet_id, EXPENSES_TAB)

    new, dupes = [], []
    for e in expenses:
        key = (_to_iso(str(e.get("date", ""))), round(float(e.get("amount", 0) or 0), 2))
        if key in keys:
            dupes.append(e)
        else:
            new.append(e)
            keys.add(key)

    return new, dupes


def update_budget_in_sheet(sheet_id: str, category: str, amount: float) -> None:
    """Write a category budget into the Monthly Budget row of the Monthly Overview tab.

    Finds the row where column A == "Monthly Budget", then looks up the column
    whose header matches the category name (case-insensitive).
    """
    gc = _gc()
    spreadsheet = gc.open_by_key(sheet_id)
    try:
        ws = spreadsheet.worksheet(MONTHLY_OVERVIEW_TAB)
    except gspread.WorksheetNotFound:
        raise ValueError(f"Tab '{MONTHLY_OVERVIEW_TAB}' not found in your sheet.")

    all_values = ws.get_all_values()
    if not all_values:
        raise ValueError("Monthly Overview tab is empty.")

    headers = [h.strip() for h in all_values[0]]

    # Find the "Monthly Budget" row (search column A)
    budget_row_idx = None
    for i, row in enumerate(all_values):
        if row and str(row[0]).strip().lower() == "monthly budget":
            budget_row_idx = i
            break
    if budget_row_idx is None:
        raise ValueError("Could not find a 'Monthly Budget' row in Monthly Overview.")

    # Find the column matching the category
    col_idx = None
    for i, header in enumerate(headers):
        if header.strip().lower() == category.strip().lower():
            col_idx = i + 1  # 1-based
            break
    if col_idx is None:
        raise ValueError(f"Column '{category}' not found in Monthly Overview headers.")

    sheet_row = budget_row_idx + 1  # 1-based
    ws.update_cell(sheet_row, col_idx, amount)
