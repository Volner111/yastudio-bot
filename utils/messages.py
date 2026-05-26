"""
utils/messages.py — Утилиты для работы с сообщениями
Удаление предыдущих сообщений бота
"""

import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from database.db import get_last_message_id, update_last_message_id

logger = logging.getLogger(__name__)


async def delete_previous_message(bot: Bot, user_id: int):
    """Удалить предыдущее сообщение бота пользователю"""
    message_id = await get_last_message_id(user_id)
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=user_id, message_id=message_id)
    except TelegramBadRequest:
        # Сообщение уже удалено или слишком старое
        pass
    except TelegramForbiddenError:
        # Пользователь заблокировал бота
        pass
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {message_id} у {user_id}: {e}")


async def save_message_id(user_id: int, message_id: int):
    """Сохранить ID последнего сообщения бота"""
    await update_last_message_id(user_id, message_id)


async def send_and_save(bot: Bot, user_id: int, **kwargs) -> Optional[int]:
    """
    Отправить сообщение и сохранить его ID.
    Сначала удаляет предыдущее сообщение.
    kwargs передаются в bot.send_message / bot.send_photo и т.д.
    """
    await delete_previous_message(bot, user_id)
    try:
        msg = await bot.send_message(chat_id=user_id, **kwargs)
        await save_message_id(user_id, msg.message_id)
        return msg.message_id
    except TelegramForbiddenError:
        logger.warning(f"Пользователь {user_id} заблокировал бота")
        return None
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
        return None
