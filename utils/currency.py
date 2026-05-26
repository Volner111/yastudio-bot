"""
utils/currency.py — Получение актуального курса валют
Использует бесплатный API exchangerate-api.com (без ключа, 1500 запросов/месяц)
Резервный источник — api.frankfurter.app (полностью бесплатный, без лимитов)
Курс кэшируется на 1 час чтобы не спамить API.
"""

import logging
import time
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# Кэш: {"rate": float, "updated_at": timestamp}
_cache: dict = {}
CACHE_TTL = 3600  # 1 час


async def get_usd_to_rub() -> float:
    """
    Получить актуальный курс USD → RUB.
    При ошибке возвращает резервный курс 90.0.
    """
    # Проверить кэш
    now = time.time()
    if _cache.get("rate") and now - _cache.get("updated_at", 0) < CACHE_TTL:
        logger.debug(f"Курс из кэша: {_cache['rate']}")
        return _cache["rate"]

    rate = await _fetch_from_frankfurter()

    if not rate:
        rate = await _fetch_from_exchangerate()

    if not rate:
        # Резервный курс если оба API недоступны
        fallback = _cache.get("rate", 90.0)
        logger.warning(f"Все API курсов недоступны, используем резерв: {fallback}")
        return fallback

    # Сохранить в кэш
    _cache["rate"] = rate
    _cache["updated_at"] = now
    logger.info(f"Курс USD/RUB обновлён: {rate}")
    return rate


async def _fetch_from_frankfurter() -> Optional[float]:
    """Получить курс с api.frankfurter.app (бесплатно, без лимитов)"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.frankfurter.app/latest",
                params={"from": "USD", "to": "RUB"},
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data["rates"]["RUB"])
    except Exception as e:
        logger.warning(f"frankfurter.app недоступен: {e}")
    return None


async def _fetch_from_exchangerate() -> Optional[float]:
    """Резервный источник — exchangerate-api.com"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://open.er-api.com/v6/latest/USD",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data["rates"]["RUB"])
    except Exception as e:
        logger.warning(f"open.er-api.com недоступен: {e}")
    return None


async def usd_to_rub(usd: float) -> float:
    """Конвертировать USD в RUB по актуальному курсу"""
    rate = await get_usd_to_rub()
    rub = round(usd * rate, 2)
    logger.debug(f"{usd} USD → {rub} RUB (курс {rate})")
    return rub
