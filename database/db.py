"""
database/db.py — Инициализация БД и все CRUD-операции
Использует aiosqlite для асинхронной работы с SQLite
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import aiosqlite

from config import config
from database.models import CREATE_TABLES_SQL

logger = logging.getLogger(__name__)

# Глобальное соединение с БД
_db: Optional[aiosqlite.Connection] = None


async def get_db() -> aiosqlite.Connection:
    """Получить соединение с БД (создаёт если не существует)"""
    global _db
    if _db is None:
        _db = await aiosqlite.connect(config.DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def init_db():
    """Инициализация БД: создание таблиц и индексов"""
    db = await get_db()
    await db.executescript(CREATE_TABLES_SQL)
    await db.commit()
    logger.info("База данных инициализирована")


async def close_db():
    """Закрытие соединения с БД"""
    global _db
    if _db:
        await _db.close()
        _db = None


# ==========================================
# USERS CRUD
# ==========================================

async def upsert_user(user_id: int, username: Optional[str], full_name: str):
    """Создать или обновить пользователя"""
    db = await get_db()
    await db.execute("""
        INSERT INTO users (user_id, username, full_name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            full_name = excluded.full_name
    """, (user_id, username, full_name))
    await db.commit()


async def get_user(user_id: int) -> Optional[aiosqlite.Row]:
    """Получить пользователя по ID"""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        return await cursor.fetchone()


async def get_user_by_username(username: str) -> Optional[aiosqlite.Row]:
    """Получить пользователя по username (без @)"""
    db = await get_db()
    username = username.lstrip("@")
    async with db.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ) as cursor:
        return await cursor.fetchone()


async def update_last_message_id(user_id: int, message_id: int):
    """Сохранить ID последнего сообщения бота пользователю"""
    db = await get_db()
    await db.execute(
        "UPDATE users SET last_message_id = ? WHERE user_id = ?",
        (message_id, user_id)
    )
    await db.commit()


async def get_last_message_id(user_id: int) -> Optional[int]:
    """Получить ID последнего сообщения бота"""
    user = await get_user(user_id)
    if user:
        return user["last_message_id"]
    return None


async def activate_subscription(
    user_id: int,
    subscription_type: str,
    amount: float,
    manual: bool = False
):
    """
    Активировать подписку пользователю.
    subscription_type: 'month' | '3months' | 'forever'
    """
    now = datetime.utcnow()

    if subscription_type == "month":
        end_date = now + timedelta(days=30)
    elif subscription_type == "3months":
        end_date = now + timedelta(days=90)
    elif subscription_type == "forever":
        end_date = None  # Бессрочно
    else:
        raise ValueError(f"Неизвестный тип подписки: {subscription_type}")

    db = await get_db()
    await db.execute("""
        UPDATE users SET
            subscription_type = ?,
            subscription_end = ?,
            is_active_subscriber = 1,
            total_paid = total_paid + ?,
            notified_5d = 0,
            notified_3d = 0,
            notified_1d = 0
        WHERE user_id = ?
    """, (subscription_type, end_date, amount if not manual else 0, user_id))
    await db.commit()
    logger.info(f"Подписка активирована: user_id={user_id}, type={subscription_type}")


async def deactivate_subscription(user_id: int):
    """Деактивировать подписку пользователя"""
    db = await get_db()
    await db.execute("""
        UPDATE users SET
            is_active_subscriber = 0,
            channel_member = 0
        WHERE user_id = ?
    """, (user_id,))
    await db.commit()


async def set_channel_member(user_id: int, is_member: bool):
    """Обновить статус членства в канале"""
    db = await get_db()
    await db.execute(
        "UPDATE users SET channel_member = ? WHERE user_id = ?",
        (1 if is_member else 0, user_id)
    )
    await db.commit()


async def get_expiring_subscriptions(days: int) -> List[aiosqlite.Row]:
    """
    Получить подписки, истекающие ровно через `days` дней.
    Используется для напоминаний.
    """
    db = await get_db()
    # Ищем пользователей с subscription_end от (сейчас + days - 0.5 дня) до (сейчас + days + 0.5 дня)
    target_start = datetime.utcnow() + timedelta(days=days) - timedelta(hours=12)
    target_end = datetime.utcnow() + timedelta(days=days) + timedelta(hours=12)

    flag_col = f"notified_{days}d"
    async with db.execute(f"""
        SELECT * FROM users
        WHERE is_active_subscriber = 1
          AND subscription_end IS NOT NULL
          AND subscription_end BETWEEN ? AND ?
          AND {flag_col} = 0
    """, (target_start, target_end)) as cursor:
        return await cursor.fetchall()


async def set_notification_flag(user_id: int, days: int):
    """Установить флаг отправки напоминания"""
    flag_col = f"notified_{days}d"
    db = await get_db()
    await db.execute(
        f"UPDATE users SET {flag_col} = 1 WHERE user_id = ?",
        (user_id,)
    )
    await db.commit()


async def get_expired_subscriptions() -> List[aiosqlite.Row]:
    """Получить пользователей с истёкшей подпиской"""
    db = await get_db()
    now = datetime.utcnow()
    async with db.execute("""
        SELECT * FROM users
        WHERE is_active_subscriber = 1
          AND subscription_end IS NOT NULL
          AND subscription_end <= ?
    """, (now,)) as cursor:
        return await cursor.fetchall()


async def get_all_users() -> List[aiosqlite.Row]:
    """Получить всех пользователей"""
    db = await get_db()
    async with db.execute("SELECT * FROM users") as cursor:
        return await cursor.fetchall()


async def get_active_subscribers() -> List[aiosqlite.Row]:
    """Получить активных подписчиков"""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM users WHERE is_active_subscriber = 1"
    ) as cursor:
        return await cursor.fetchall()


async def get_former_subscribers() -> List[aiosqlite.Row]:
    """Бывшие подписчики (платили, подписка кончилась, не продлили)"""
    db = await get_db()
    async with db.execute("""
        SELECT * FROM users
        WHERE is_active_subscriber = 0
          AND total_paid > 0
    """) as cursor:
        return await cursor.fetchall()


async def get_never_paid_users() -> List[aiosqlite.Row]:
    """Пользователи, которые никогда не платили"""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM users WHERE total_paid = 0 AND is_active_subscriber = 0"
    ) as cursor:
        return await cursor.fetchall()


# ==========================================
# PAYMENTS CRUD
# ==========================================

async def create_payment(
    user_id: int,
    amount: float,
    payment_system: str,
    invoice_id: str,
    subscription_type: str,
    pay_url: str = "",
    currency: str = "USD"
) -> int:
    """Создать запись о платеже, вернуть ID записи"""
    db = await get_db()
    async with db.execute("""
        INSERT INTO payments (user_id, amount, currency, payment_system, invoice_id, pay_url, subscription_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, amount, currency, payment_system, invoice_id, pay_url, subscription_type)) as cursor:
        payment_id = cursor.lastrowid
    await db.commit()
    return payment_id


async def get_payment_by_invoice(invoice_id: str) -> Optional[aiosqlite.Row]:
    """Найти платёж по ID инвойса"""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM payments WHERE invoice_id = ?", (invoice_id,)
    ) as cursor:
        return await cursor.fetchone()


async def update_payment_status(invoice_id: str, status: str):
    """Обновить статус платежа"""
    db = await get_db()
    paid_at = datetime.utcnow() if status == "paid" else None
    await db.execute("""
        UPDATE payments SET status = ?, paid_at = ?
        WHERE invoice_id = ?
    """, (status, paid_at, invoice_id))
    await db.commit()


async def get_pending_payment(user_id: int) -> Optional[aiosqlite.Row]:
    """Получить последний незавершённый платёж пользователя"""
    db = await get_db()
    async with db.execute("""
        SELECT * FROM payments
        WHERE user_id = ? AND status = 'pending'
        ORDER BY created_at DESC
        LIMIT 1
    """, (user_id,)) as cursor:
        return await cursor.fetchone()


# ==========================================
# STATISTICS
# ==========================================

async def get_stats(period: str) -> Dict[str, Any]:
    """
    Получить статистику за период.
    period: 'today' | 'week' | 'month' | 'all'
    """
    db = await get_db()

    if period == "today":
        since = datetime.utcnow() - timedelta(hours=24)
    elif period == "week":
        since = datetime.utcnow() - timedelta(days=7)
    elif period == "month":
        since = datetime.utcnow() - timedelta(days=30)
    else:
        since = None

    if period == "all":
        async with db.execute("SELECT COUNT(*) as cnt FROM users") as c:
            total_users = (await c.fetchone())["cnt"]
        async with db.execute("SELECT COUNT(*) as cnt FROM users WHERE is_active_subscriber = 1") as c:
            active_subs = (await c.fetchone())["cnt"]
        async with db.execute("SELECT COALESCE(SUM(total_paid), 0) as total FROM users") as c:
            total_earned = (await c.fetchone())["total"]
        return {
            "total_users": total_users,
            "active_subs": active_subs,
            "total_earned": total_earned,
        }
    else:
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE registered_at >= ?", (since,)
        ) as c:
            new_users = (await c.fetchone())["cnt"]
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM payments WHERE status = 'paid' AND paid_at >= ?", (since,)
        ) as c:
            new_payments = (await c.fetchone())["cnt"]
        async with db.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM payments WHERE status = 'paid' AND paid_at >= ?",
            (since,)
        ) as c:
            total_amount = (await c.fetchone())["total"]
        return {
            "new_users": new_users,
            "new_payments": new_payments,
            "total_amount": total_amount,
        }