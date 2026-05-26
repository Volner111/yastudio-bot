"""
config.py — Конфигурация бота
Загружает все переменные окружения из .env файла
"""

import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


def _parse_admin_ids(raw: str) -> List[int]:
    """Парсинг списка ID администраторов из строки"""
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


@dataclass
class Config:
    # Tribute Shop API
    TRIBUTE_API_KEY: str = field(default_factory=lambda: os.getenv("TRIBUTE_API_KEY", ""))
    TRIBUTE_WEBHOOK_PORT: int = field(default_factory=lambda: int(os.getenv("TRIBUTE_WEBHOOK_PORT", "8080")))

    # Цены Tribute в рублях
    TRIBUTE_PRICE_1MONTH: float = field(default_factory=lambda: float(os.getenv("TRIBUTE_PRICE_1MONTH", "1990")))
    TRIBUTE_PRICE_3MONTHS: float = field(default_factory=lambda: float(os.getenv("TRIBUTE_PRICE_3MONTHS", "4990")))
    TRIBUTE_PRICE_FOREVER: float = field(default_factory=lambda: float(os.getenv("TRIBUTE_PRICE_FOREVER", "14990")))

    # Telegram Bot
    BOT_TOKEN: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))

    # Channel
    CHANNEL_ID: int = field(default_factory=lambda: int(os.getenv("CHANNEL_ID", "0")))
    ADMIN_IDS: List[int] = field(
        default_factory=lambda: _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
    )

    # Payment systems
    CRYPTOBOT_TOKEN: str = field(default_factory=lambda: os.getenv("CRYPTOBOT_TOKEN", ""))
    LAVA_API_KEY: str = field(default_factory=lambda: os.getenv("LAVA_API_KEY", ""))
    LAVA_SHOP_ID: str = field(default_factory=lambda: os.getenv("LAVA_SHOP_ID", ""))

    # Prices in USD
    PRICE_1MONTH: float = field(default_factory=lambda: float(os.getenv("PRICE_1MONTH", "19.99")))
    PRICE_3MONTHS: float = field(default_factory=lambda: float(os.getenv("PRICE_3MONTHS", "49.99")))
    PRICE_FOREVER: float = field(default_factory=lambda: float(os.getenv("PRICE_FOREVER", "149.99")))

    # Support
    SUPPORT_LINK: str = field(default_factory=lambda: os.getenv("SUPPORT_LINK", "https://t.me/support"))

    # Assets
    WELCOME_BANNER: str = field(default_factory=lambda: os.getenv("WELCOME_BANNER", "assets/welcome.jpg"))
    TARIFFS_BANNER: str = field(default_factory=lambda: os.getenv("TARIFFS_BANNER", "assets/tariffs.jpg"))
    PAYMENT_BANNER: str = field(default_factory=lambda: os.getenv("PAYMENT_BANNER", "assets/payment.jpg"))

    # Database
    DB_PATH: str = "bot.db"

    # Scheduler
    SUBSCRIPTION_CHECK_INTERVAL_HOURS: int = 12
    REMINDER_CHECK_HOUR: int = 12  # 12:00 UTC

    def validate(self):
        """Проверка обязательных параметров"""
        errors = []
        if not self.BOT_TOKEN:
            errors.append("BOT_TOKEN не задан")
        if not self.CHANNEL_ID:
            errors.append("CHANNEL_ID не задан")
        if not self.ADMIN_IDS:
            errors.append("ADMIN_IDS не задан")
        if errors:
            raise ValueError(f"Ошибки конфигурации: {', '.join(errors)}")


# Глобальный объект конфига
config = Config()