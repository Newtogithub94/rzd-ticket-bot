import aiosqlite
import logging
from typing import List, Dict, Any, Optional
from config import DB_PATH

logger = logging.getLogger(__name__)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                dnd_enabled INTEGER NOT NULL DEFAULT 0,
                dnd_start INTEGER NOT NULL DEFAULT 23,
                dnd_end INTEGER NOT NULL DEFAULT 7,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                origin_code TEXT NOT NULL,
                origin_name TEXT NOT NULL,
                destination_code TEXT NOT NULL,
                destination_name TEXT NOT NULL,
                date TEXT NOT NULL,
                date_end TEXT,
                car_type TEXT NOT NULL DEFAULT 'ANY',
                lower_seats_only INTEGER NOT NULL DEFAULT 0,
                upper_seats_only INTEGER NOT NULL DEFAULT 0,
                no_side_seats INTEGER NOT NULL DEFAULT 0,
                min_seats_count INTEGER NOT NULL DEFAULT 1,
                train_number TEXT DEFAULT '',
                train_departure TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                last_checked_at TEXT,
                last_seen_min_price REAL,
                error_count INTEGER NOT NULL DEFAULT 0,
                error_notified_active INTEGER NOT NULL DEFAULT 0,
                last_error_notified_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Migrations for existing DB tables
        cursor = await db.execute("PRAGMA table_info(subscriptions)")
        columns = [row[1] for row in await cursor.fetchall()]
        
        migrations = [
            ("no_side_seats", "INTEGER NOT NULL DEFAULT 0"),
            ("upper_seats_only", "INTEGER NOT NULL DEFAULT 0"),
            ("date_end", "TEXT"),
            ("min_seats_count", "INTEGER NOT NULL DEFAULT 1"),
            ("train_departure", "TEXT DEFAULT ''"),
            ("last_seen_min_price", "REAL"),
            ("error_count", "INTEGER NOT NULL DEFAULT 0"),
            ("error_notified_active", "INTEGER NOT NULL DEFAULT 0"),
            ("last_error_notified_at", "TEXT")
        ]
        
        for col_name, col_type in migrations:
            if col_name not in columns:
                await db.execute(f"ALTER TABLE subscriptions ADD COLUMN {col_name} {col_type}")

        # Check users table migrations
        cursor_u = await db.execute("PRAGMA table_info(users)")
        u_columns = [row[1] for row in await cursor_u.fetchall()]
        if "dnd_enabled" not in u_columns:
            await db.execute("ALTER TABLE users ADD COLUMN dnd_enabled INTEGER NOT NULL DEFAULT 0")
            await db.execute("ALTER TABLE users ADD COLUMN dnd_start INTEGER NOT NULL DEFAULT 23")
            await db.execute("ALTER TABLE users ADD COLUMN dnd_end INTEGER NOT NULL DEFAULT 7")

        await db.commit()
        logger.info("Database initialized successfully.")

async def register_user(user_id: int, username: Optional[str] = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        await db.commit()

async def get_user_settings(user_id: int) -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return {"user_id": user_id, "dnd_enabled": 0, "dnd_start": 23, "dnd_end": 7}

async def update_user_dnd(user_id: int, enabled: int, start: int = 23, end: int = 7):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET dnd_enabled = ?, dnd_start = ?, dnd_end = ? WHERE user_id = ?",
            (enabled, start, end, user_id)
        )
        await db.commit()

async def add_subscription(
    user_id: int,
    origin_code: str,
    origin_name: str,
    destination_code: str,
    destination_name: str,
    date_str: str,
    date_end_str: Optional[str] = None,
    car_type: str = "ANY",
    lower_seats_only: int = 0,
    upper_seats_only: int = 0,
    no_side_seats: int = 0,
    min_seats_count: int = 1,
    train_number: str = "",
    train_departure: str = ""
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO subscriptions (
                user_id, origin_code, origin_name, destination_code, destination_name,
                date, date_end, car_type, lower_seats_only, upper_seats_only, no_side_seats,
                min_seats_count, train_number, train_departure, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                user_id, origin_code, origin_name, destination_code, destination_name,
                date_str, date_end_str or date_str, car_type, lower_seats_only,
                upper_seats_only, no_side_seats, min_seats_count,
                train_number.strip().upper(), train_departure.strip()
            )
        )
        await db.commit()
        return cursor.lastrowid

async def get_user_subscriptions(user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_all_active_subscriptions() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscriptions WHERE status = 'active'"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def delete_subscription(sub_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM subscriptions WHERE id = ? AND user_id = ?",
            (sub_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0

async def toggle_subscription_status(sub_id: int, user_id: int) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT status FROM subscriptions WHERE id = ? AND user_id = ?",
            (sub_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            new_status = "paused" if row["status"] == "active" else "active"
        
        await db.execute(
            "UPDATE subscriptions SET status = ? WHERE id = ?",
            (new_status, sub_id)
        )
        await db.commit()
        return new_status

async def update_last_checked(sub_id: int, timestamp_str: str, min_price: Optional[float] = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE subscriptions 
            SET last_checked_at = ?, error_count = 0, last_seen_min_price = COALESCE(?, last_seen_min_price) 
            WHERE id = ?
            """,
            (timestamp_str, min_price, sub_id)
        )
        await db.commit()

async def clear_error_notified_flag(sub_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT error_notified_active FROM subscriptions WHERE id = ?", (sub_id,)) as cursor:
            row = await cursor.fetchone()
            was_active = bool(row[0]) if row else False

        await db.execute(
            "UPDATE subscriptions SET error_notified_active = 0, error_count = 0 WHERE id = ?",
            (sub_id,)
        )
        await db.commit()
        return was_active

async def increment_error_count(sub_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions SET error_count = error_count + 1 WHERE id = ?",
            (sub_id,)
        )
        await db.commit()
        async with db.execute("SELECT error_count FROM subscriptions WHERE id = ?", (sub_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 1

async def mark_error_notified(sub_id: int, timestamp_str: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions SET error_notified_active = 1, last_error_notified_at = ? WHERE id = ?",
            (timestamp_str, sub_id)
        )
        await db.commit()
