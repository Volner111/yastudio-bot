"""
main.py — Точка входа в бота
Инициализация aiogram, регистрация роутеров, запуск polling
"""

import asyncio
import logging
import logging.handlers
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database.db import init_db, close_db
from handlers import start, tariffs, payment, admin
from handlers.tribute_webhook import create_webhook_app
from scheduler.tasks import setup_scheduler
from utils.photo_cache import warmup_cache

# ==========================================
# LOGGING SETUP
# ==========================================

def setup_logging():
    """Настройка логирования с ротацией файлов"""
    os.makedirs("logs", exist_ok=True)

    log_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Ротирующий файловый обработчик (10 МБ, хранить 5 файлов)
    file_handler = logging.handlers.RotatingFileHandler(
        filename="logs/bot.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)

    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.INFO)

    # Корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Заглушить шумные библиотеки
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)


logger = logging.getLogger(__name__)


# ==========================================
# MAIN
# ==========================================

async def on_startup(bot: Bot, scheduler):
    """Действия при запуске бота"""
    await init_db()
    scheduler.start()

    # Прогрев кэша баннеров — загружаем файлы один раз при старте.
    # Все последующие отправки будут мгновенными (по file_id).
    if config.ADMIN_IDS:
        await warmup_cache(bot, config.ADMIN_IDS[0], config.WELCOME_BANNER, config.TARIFFS_BANNER, config.PAYMENT_BANNER)

    # Проверить что бот может работать с каналом
    try:
        chat = await bot.get_chat(config.CHANNEL_ID)
        logger.info(f"Канал найден: {chat.title} (id={config.CHANNEL_ID})")
    except Exception as e:
        logger.warning(f"Не удалось получить информацию о канале: {e}")

    me = await bot.get_me()
    logger.info(f"Бот запущен: @{me.username} (id={me.id})")

    # Убираем кнопку меню (плашку "Старт") через API
    from aiogram.types import BotCommand, MenuButtonDefault
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    except Exception:
        pass

    # Устанавливаем список команд — /start намеренно НЕ включаем,
    # чтобы плашка "Старт" не висела в чате после нажатия
    await bot.set_my_commands([
        BotCommand(command="info", description="Политика и соглашение"),
        BotCommand(command="admin", description="Панель администратора"),
    ])


async def on_shutdown(bot: Bot, scheduler):
    """Действия при остановке бота"""
    logger.info("Завершение работы бота...")
    scheduler.shutdown(wait=False)
    await close_db()
    await bot.session.close()
    logger.info("Бот остановлен")


async def main():
    setup_logging()
    logger.info("Запуск бота...")

    # Валидация конфига
    try:
        config.validate()
    except ValueError as e:
        logger.critical(f"Ошибка конфигурации: {e}")
        sys.exit(1)

    # Инициализация бота и диспетчера
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Настройка планировщика
    scheduler = setup_scheduler(bot)

    # Регистрация роутеров (порядок важен!)
    dp.include_router(admin.router)    # Сначала — чтобы /admin не конфликтовал
    dp.include_router(start.router)
    dp.include_router(tariffs.router)
    dp.include_router(payment.router)

    # Хуки запуска/остановки
    # Важно: передаём async-функции напрямую через замыкание, не через lambda
    async def _startup(): await on_startup(bot, scheduler)
    async def _shutdown(): await on_shutdown(bot, scheduler)
    dp.startup.register(_startup)
    dp.shutdown.register(_shutdown)

    # Создать папку assets если нет
    os.makedirs("assets", exist_ok=True)

    logger.info("Запуск polling и webhook-сервера...")
    try:
        # Запускаем webhook-сервер для Tribute параллельно с polling
        from aiohttp import web
        webhook_app = create_webhook_app(bot)
        runner = web.AppRunner(webhook_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", config.TRIBUTE_WEBHOOK_PORT)
        await site.start()
        logger.info(f"Tribute webhook сервер запущен на порту {config.TRIBUTE_WEBHOOK_PORT}")

        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True
        )
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    finally:
        await runner.cleanup()
        await on_shutdown(bot, scheduler)


if __name__ == "__main__":
    asyncio.run(main())