from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import gspread

from config import GOOGLE_SERVICE_ACCOUNT_JSON, EXPENSES_TAB, INCOME_TAB

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


def get_monthly_rows(sheet_id: str, tab_name: str) -> List[Dict]:
    current_month = datetime.now().strftime("%Y-%m")
    rows = get_all_rows(sheet_id, tab_name)
    return [r for r in rows if _to_iso(r.get("Purchase Date", "")).startswith(current_month)]


def get_rows_for_period(sheet_id: str, tab_name: str, period: str) -> List[Dict]:
    now = datetime.now()
    rows = get_all_rows(sheet_id, tab_name)

    if period == "today":
        target = now.strftime("%Y-%m-%d")
        return [r for r in rows if _to_iso(r.get("Purchase Date", "")) == target]

    if period == "week":
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        return [r for r in rows if _to_iso(r.get("Purchase Date", "")) >= week_ago]

    current_month = now.strftime("%Y-%m")
    return [r for r in rows if _to_iso(r.get("Purchase Date", "")).startswith(current_month)]


def get_monthly_summary(sheet_id: str, tab_name: str) -> Dict:
    rows = get_monthly_rows(sheet_id, tab_name)
    total = sum(float(r.get("Amount", 0)) for r in rows)
    by_category: Dict[str, float] = {}
    for r in rows:
        cat = r.get("Category", "Other")
        by_category[cat] = round(by_category.get(cat, 0) + float(r.get("Amount", 0)), 2)

    return {
        "total": round(total, 2),
        "by_category": by_category,
        "transaction_count": len(rows),
        "month": datetime.now().strftime("%B %Y"),
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


def filter_duplicates(
    sheet_id: str, tab_name: str, expenses: List[Dict]
) -> Tuple[List[Dict], List[Dict]]:
    """Return (new_expenses, duplicates). Duplicate = same Purchase Date + Amount + Item."""
    existing = get_all_rows(sheet_id, tab_name)
    existing_keys = {
        (str(r.get("Purchase Date", "")), str(r.get("Amount", "")), str(r.get("Item", "")).lower())
        for r in existing
    }

    new, dupes = [], []
    for e in expenses:
        key = (str(e["date"]), str(e["amount"]), str(e.get("description", "")).lower())
        if key in existing_keys:
            dupes.append(e)
        else:
            new.append(e)
            existing_keys.add(key)

    return new, dupes
