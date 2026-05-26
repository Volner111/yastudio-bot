"""
utils/channel.py — Утилиты для работы с Telegram-каналом
Генерация инвайт-ссылок, кик участников
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from config import config

logger = logging.getLogger(__name__)


async def generate_invite_link(bot: Bot) -> Optional[str]:
    """
    Сгенерировать одноразовую инвайт-ссылку в канал.
    - expire_date: через 24 часа
    - member_limit: 1 (одноразовая)
    """
    try:
        expire = datetime.utcnow() + timedelta(hours=24)
        link = await bot.create_chat_invite_link(
            chat_id=config.CHANNEL_ID,
            expire_date=expire,
            member_limit=1,
            name="Subscription"
        )
        logger.info(f"Создана инвайт-ссылка: {link.invite_link}")
        return link.invite_link
    except TelegramBadRequest as e:
        logger.error(f"Ошибка создания инвайт-ссылки: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при создании ссылки: {e}")
        return None


async def kick_user_from_channel(bot: Bot, user_id: int) -> bool:
    """
    Кикнуть пользователя из канала без бана.
    Используем ban + немедленный unban.
    """
    try:
        await bot.ban_chat_member(
            chat_id=config.CHANNEL_ID,
            user_id=user_id
        )
        # Сразу снимаем бан — пользователь выкинут, но не в ЧС
        await bot.unban_chat_member(
            chat_id=config.CHANNEL_ID,
            user_id=user_id,
            only_if_banned=True
        )
        logger.info(f"Пользователь {user_id} кикнут из канала")
        return True
    except TelegramBadRequest as e:
        # Пользователь может уже не быть в канале
        logger.warning(f"Не удалось кикнуть {user_id}: {e}")
        return False
    except TelegramForbiddenError as e:
        logger.error(f"Нет прав для кика {user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при кике {user_id}: {e}")
        return False


async def check_user_in_channel(bot: Bot, user_id: int) -> bool:
    """Проверить, является ли пользователь участником канала"""
    try:
        member = await bot.get_chat_member(
            chat_id=config.CHANNEL_ID,
            user_id=user_id
        )
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False
