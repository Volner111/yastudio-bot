"""
utils/photo_cache.py — Кэш file_id для баннеров

Логика:
- При первом вызове загружаем файл с диска через FSInputFile (медленно, ~1-2с)
- Telegram возвращает file_id — сохраняем его в памяти
- При всех последующих вызовах отправляем по file_id (мгновенно, <100мс)
"""

import logging
import os
from typing import Optional

from aiogram import Bot
from aiogram.types import FSInputFile

logger = logging.getLogger(__name__)

# Словарь: путь к файлу → file_id полученный от Telegram
_cache: dict[str, str] = {}


async def get_file_id(bot: Bot, file_path: str, admin_id: int) -> Optional[str]:
    """
    Получить file_id для фото. При первом вызове загружает файл и кэширует.
    admin_id — ID администратора, которому отправим фото для получения file_id
    (сообщение сразу удаляется, пользователь ничего не видит).
    """
    if file_path in _cache:
        return _cache[file_path]

    if not os.path.exists(file_path):
        logger.warning(f"Файл не найден: {file_path}")
        return None

    try:
        logger.info(f"Кэширую file_id для {file_path}...")
        # Отправляем фото администратору чтобы получить file_id
        msg = await bot.send_photo(
            chat_id=admin_id,
            photo=FSInputFile(file_path)
        )
        file_id = msg.photo[-1].file_id
        # Сразу удаляем — пользователь ничего не увидит
        await msg.delete()

        _cache[file_path] = file_id
        logger.info(f"file_id закэширован для {file_path}: {file_id[:20]}...")
        return file_id

    except Exception as e:
        logger.error(f"Не удалось закэшировать {file_path}: {e}")
        return None


async def warmup_cache(bot: Bot, admin_id: int, *file_paths: str):
    """
    Прогреть кэш при старте бота — загрузить все баннеры заранее.
    Вызывается один раз в on_startup().
    """
    for path in file_paths:
        if os.path.exists(path):
            await get_file_id(bot, path, admin_id)
    logger.info("Кэш баннеров прогрет")
