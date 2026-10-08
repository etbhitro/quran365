"""Хранение прогресса пользователей в SQLite (без внешних зависимостей)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from .config import PROGRESS_DB


@contextmanager
def _conn():
    PROGRESS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(PROGRESS_DB)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                current_day INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attempts (
                user_id   INTEGER NOT NULL,
                day       INTEGER NOT NULL,
                accuracy  REAL    NOT NULL,
                created_at TEXT   NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, day)
            )
            """
        )


def get_current_day(user_id: int) -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT current_day FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (user_id, current_day) VALUES (?, 1)", (user_id,)
            )
            return 1
        return row[0]


def set_current_day(user_id: int, day: int) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, current_day) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET current_day = excluded.current_day
            """,
            (user_id, day),
        )


def record_attempt(user_id: int, day: int, accuracy: float) -> None:
    """Сохраняем лучший результат за день."""
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO attempts (user_id, day, accuracy) VALUES (?, ?, ?)
            ON CONFLICT(user_id, day) DO UPDATE SET
                accuracy = MAX(attempts.accuracy, excluded.accuracy),
                created_at = datetime('now')
            """,
            (user_id, day, accuracy),
        )


def completed_days(user_id: int, threshold: float = 0.8) -> int:
    """Сколько дней пройдено с точностью не ниже порога."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM attempts WHERE user_id = ? AND accuracy >= ?",
            (user_id, threshold),
        ).fetchone()
        return row[0] if row else 0
