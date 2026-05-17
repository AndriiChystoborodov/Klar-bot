import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional

DB_PATH = "klar.db"

_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id      INTEGER PRIMARY KEY,
    username         TEXT,
    sheet_id         TEXT,
    monthly_budget   REAL DEFAULT NULL,
    category_budgets TEXT DEFAULT '{}',
    is_banned        INTEGER DEFAULT 0,
    banned_at        TEXT DEFAULT NULL,
    created_at       TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_ACCOUNTS = """
CREATE TABLE IF NOT EXISTS accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    name        TEXT NOT NULL,
    is_default  INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);
"""

PRESET_ACCOUNTS = ["Cash", "ZKB", "UBS", "Crypto"]


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.execute(_CREATE_USERS)
        con.execute(_CREATE_ACCOUNTS)
        # Migrate: add category_budgets column if it doesn't exist yet
        try:
            con.execute("ALTER TABLE users ADD COLUMN category_budgets TEXT DEFAULT '{}'")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def upsert_user(telegram_id: int, username: Optional[str]) -> None:
    with _conn() as con:
        con.execute(
            """
            INSERT INTO users (telegram_id, username)
            VALUES (?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET username = excluded.username
            """,
            (telegram_id, username),
        )


def get_sheet_id(telegram_id: int) -> Optional[str]:
    with _conn() as con:
        row = con.execute(
            "SELECT sheet_id FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    return row["sheet_id"] if row else None


def set_sheet_id(telegram_id: int, sheet_id: str) -> None:
    with _conn() as con:
        con.execute(
            """
            INSERT INTO users (telegram_id, sheet_id)
            VALUES (?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET sheet_id = excluded.sheet_id
            """,
            (telegram_id, sheet_id),
        )


def get_budget(telegram_id: int) -> Optional[float]:
    with _conn() as con:
        row = con.execute(
            "SELECT monthly_budget FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    return row["monthly_budget"] if row else None


def set_budget(telegram_id: int, amount: float) -> None:
    with _conn() as con:
        con.execute(
            """
            INSERT INTO users (telegram_id, monthly_budget)
            VALUES (?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET monthly_budget = excluded.monthly_budget
            """,
            (telegram_id, amount),
        )


def get_category_budgets(telegram_id: int) -> Dict[str, float]:
    with _conn() as con:
        row = con.execute(
            "SELECT category_budgets FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["category_budgets"] or "{}")
    except (ValueError, TypeError):
        return {}


def set_category_budget(telegram_id: int, category: str, amount: float) -> None:
    budgets = get_category_budgets(telegram_id)
    budgets[category] = amount
    with _conn() as con:
        con.execute(
            """
            INSERT INTO users (telegram_id, category_budgets)
            VALUES (?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET category_budgets = excluded.category_budgets
            """,
            (telegram_id, json.dumps(budgets)),
        )


def is_banned(telegram_id: int) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT is_banned FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    return bool(row["is_banned"]) if row else False


def ban_user(telegram_id: int) -> None:
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO users (telegram_id, is_banned, banned_at)
            VALUES (?, 1, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET is_banned = 1, banned_at = excluded.banned_at
            """,
            (telegram_id, now),
        )


def unban_user(telegram_id: int) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE users SET is_banned = 0, banned_at = NULL WHERE telegram_id = ?",
            (telegram_id,),
        )


def get_all_banned() -> List[Dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT telegram_id, username, banned_at FROM users WHERE is_banned = 1"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def get_accounts(telegram_id: int) -> List[Dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, name, is_default FROM accounts WHERE telegram_id = ? ORDER BY id",
            (telegram_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_account_by_name(telegram_id: int, name: str) -> Optional[Dict]:
    with _conn() as con:
        row = con.execute(
            "SELECT id, name, is_default FROM accounts WHERE telegram_id = ? AND LOWER(name) = LOWER(?)",
            (telegram_id, name),
        ).fetchone()
    return dict(row) if row else None


def get_default_account(telegram_id: int) -> Optional[Dict]:
    with _conn() as con:
        row = con.execute(
            "SELECT id, name, is_default FROM accounts WHERE telegram_id = ? AND is_default = 1",
            (telegram_id,),
        ).fetchone()
        if not row:
            # Fall back to first account
            row = con.execute(
                "SELECT id, name, is_default FROM accounts WHERE telegram_id = ? ORDER BY id LIMIT 1",
                (telegram_id,),
            ).fetchone()
    return dict(row) if row else None


def add_account(telegram_id: int, name: str) -> int:
    accounts = get_accounts(telegram_id)
    is_first = len(accounts) == 0
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO accounts (telegram_id, name, is_default) VALUES (?, ?, ?)",
            (telegram_id, name, 1 if is_first else 0),
        )
    return cur.lastrowid


def set_default_account(telegram_id: int, name: str) -> bool:
    account = get_account_by_name(telegram_id, name)
    if not account:
        return False
    with _conn() as con:
        con.execute("UPDATE accounts SET is_default = 0 WHERE telegram_id = ?", (telegram_id,))
        con.execute("UPDATE accounts SET is_default = 1 WHERE id = ?", (account["id"],))
    return True


def delete_account(telegram_id: int, name: str) -> bool:
    account = get_account_by_name(telegram_id, name)
    if not account:
        return False
    with _conn() as con:
        con.execute("DELETE FROM accounts WHERE id = ?", (account["id"],))
    # If deleted was default, promote the first remaining account
    if account["is_default"]:
        remaining = get_accounts(telegram_id)
        if remaining:
            with _conn() as con:
                con.execute("UPDATE accounts SET is_default = 1 WHERE id = ?", (remaining[0]["id"],))
    return True
