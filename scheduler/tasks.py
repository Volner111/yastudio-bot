"""
scheduler/tasks.py — Фоновые задачи APScheduler
- Проверка истёкших подписок (каждые 12 часов)
- Напоминания об истечении (ежедневно в 12:00 UTC)
"""

import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import config
from database.db import (
    get_expired_subscriptions, deactivate_subscription,
    get_expiring_subscriptions, set_notification_flag
)
from texts import REMINDER_TEXT, SUBSCRIPTION_EXPIRED_TEXT
from utils.channel import kick_user_from_channel

logger = logging.getLogger(__name__)


async def check_expired_subscriptions(bot: Bot):
    """
    Проверить истёкшие подписки и кикнуть пользователей из канала.
    Запускается каждые 12 часов.
    """
    logger.info("Запуск проверки истёкших подписок...")
    expired_users = await get_expired_subscriptions()

    if not expired_users:
        logger.info("Истёкших подписок нет")
        return

    kicked = 0
    for user in expired_users:
        user_id = user["user_id"]
        try:
            # Кикнуть из канала (ban + unban)
            await kick_user_from_channel(bot, user_id)
            # Деактивировать в БД
            await deactivate_subscription(user_id)
            # Уведомить пользователя
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=SUBSCRIPTION_EXPIRED_TEXT,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="show_tariffs")]
                    ])
                )
            except Exception as notify_err:
                logger.warning(f"Не удалось уведомить {user_id} об истечении: {notify_err}")

            kicked += 1
            logger.info(f"Подписка деактивирована: user_id={user_id}")
        except Exception as e:
            logger.error(f"Ошибка при деактивации подписки {user_id}: {e}")

    logger.info(f"Проверка завершена. Деактивировано подписок: {kicked}")


async def send_subscription_reminders(bot: Bot):
    """
    Отправить напоминания об истечении подписки.
    За 5, 3 и 1 день. Запускается ежедневно в 12:00 UTC.
    """
    logger.info("Запуск отправки напоминаний...")
    total_sent = 0

    for days in (5, 3, 1):
        users = await get_expiring_subscriptions(days)
        for user in users:
            user_id = user["user_id"]
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=REMINDER_TEXT(days),
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="show_tariffs")]
                    ])
                )
                # Установить флаг — не слать повторно
                await set_notification_flag(user_id, days)
                total_sent += 1
                logger.info(f"Напоминание за {days}д отправлено: user_id={user_id}")
            except Exception as e:
                logger.warning(f"Не удалось отправить напоминание {user_id}: {e}")

    logger.info(f"Напоминания отправлены: {total_sent}")


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """
    Настроить и запустить планировщик задач.
    Возвращает объект scheduler для управления из main.py.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Проверка истёкших подписок каждые 12 часов
    scheduler.add_job(
        check_expired_subscriptions,
        trigger="interval",
        hours=config.SUBSCRIPTION_CHECK_INTERVAL_HOURS,
        kwargs={"bot": bot},
        id="check_expired",
        replace_existing=True,
        misfire_grace_time=300  # Допустимое опоздание — 5 минут
    )

    # Напоминания ежедневно в 12:00 UTC
    scheduler.add_job(
        send_subscription_reminders,
        trigger="cron",
        hour=config.REMINDER_CHECK_HOUR,
        minute=0,
        kwargs={"bot": bot},
        id="send_reminders",
        replace_existing=True,
        misfire_grace_time=3600  # Допустимое опоздание — 1 час
    )

    logger.info("Планировщик задач настроен")
    return scheduler
