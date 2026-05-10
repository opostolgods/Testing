"""SQLite database for user accounts and VPN keys."""
import os
import sqlite3
import time
from typing import Optional

from config import DB_PATH


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_db() -> sqlite3.Connection:
    _ensure_dir()
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def init_db():
    db = get_db()
    cur = db.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        photo_url TEXT,
        is_premium INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0,
        created_at REAL,
        last_login REAL
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        uuid TEXT NOT NULL UNIQUE,
        sub_id TEXT,
        email TEXT NOT NULL,
        is_premium INTEGER DEFAULT 0,
        vless_links TEXT,
        expiry_ms INTEGER,
        created_at REAL,
        active INTEGER DEFAULT 1,
        FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        plan TEXT NOT NULL,
        started_at REAL,
        expires_at REAL,
        active INTEGER DEFAULT 1,
        FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
    )""")

    db.commit()
    db.close()


def upsert_user(telegram_id: int, username: str = "",
                first_name: str = "", last_name: str = "",
                photo_url: str = "", is_admin: bool = False) -> dict:
    db = get_db()
    now = time.time()
    existing = db.execute(
        "SELECT * FROM users WHERE telegram_id=?", [telegram_id]
    ).fetchone()

    if existing:
        db.execute(
            "UPDATE users SET username=?, first_name=?, last_name=?, "
            "photo_url=?, last_login=? WHERE telegram_id=?",
            [username, first_name, last_name, photo_url, now, telegram_id],
        )
    else:
        db.execute(
            "INSERT INTO users (telegram_id, username, first_name, last_name, "
            "photo_url, is_premium, is_admin, created_at, last_login) "
            "VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)",
            [telegram_id, username, first_name, last_name, photo_url,
             1 if is_admin else 0, now, now],
        )

    db.commit()
    user = db.execute(
        "SELECT * FROM users WHERE telegram_id=?", [telegram_id]
    ).fetchone()
    db.close()
    return dict(user)


def get_user(telegram_id: int) -> Optional[dict]:
    db = get_db()
    row = db.execute(
        "SELECT * FROM users WHERE telegram_id=?", [telegram_id]
    ).fetchone()
    db.close()
    return dict(row) if row else None


def set_premium(telegram_id: int, is_premium: bool = True):
    db = get_db()
    db.execute(
        "UPDATE users SET is_premium=? WHERE telegram_id=?",
        [1 if is_premium else 0, telegram_id],
    )
    db.commit()
    db.close()


def save_key(telegram_id: int, key_data: dict):
    db = get_db()
    import json
    db.execute(
        "INSERT INTO keys (telegram_id, uuid, sub_id, email, is_premium, "
        "vless_links, expiry_ms, created_at, active) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
        [
            telegram_id,
            key_data["uuid"],
            key_data.get("sub_id", ""),
            key_data["email"],
            1 if key_data.get("is_premium") else 0,
            json.dumps(key_data.get("links", [])),
            key_data.get("expiry_ms", 0),
            time.time(),
        ],
    )
    db.commit()
    db.close()


def get_user_keys(telegram_id: int) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM keys WHERE telegram_id=? AND active=1 ORDER BY created_at DESC",
        [telegram_id],
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def deactivate_key(key_uuid: str):
    db = get_db()
    db.execute("UPDATE keys SET active=0 WHERE uuid=?", [key_uuid])
    db.commit()
    db.close()


def get_all_users() -> list[dict]:
    db = get_db()
    rows = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_all_keys() -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT k.*, u.username, u.first_name FROM keys k "
        "LEFT JOIN users u ON k.telegram_id = u.telegram_id "
        "ORDER BY k.created_at DESC"
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    db = get_db()
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    premium_users = db.execute(
        "SELECT COUNT(*) FROM users WHERE is_premium=1"
    ).fetchone()[0]
    active_keys = db.execute(
        "SELECT COUNT(*) FROM keys WHERE active=1"
    ).fetchone()[0]
    db.close()
    return {
        "total_users": total_users,
        "premium_users": premium_users,
        "free_users": total_users - premium_users,
        "active_keys": active_keys,
    }
