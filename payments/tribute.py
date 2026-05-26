"""
payments/tribute.py — Интеграция с Tribute Shop API
Документация: https://wiki.tribute.tg/ru/for-shops/api-magazina
"""

import hashlib
import hmac
import logging
import ssl
from typing import Optional, Dict, Any

import aiohttp
import certifi

from config import config

logger = logging.getLogger(__name__)

TRIBUTE_API_URL = "https://tribute.tg/api/v1"

# SSL контекст с сертификатами certifi — решает проблему на Windows
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class TributeClient:
    """Клиент для работы с Tribute Shop API"""

    def __init__(self):
        self.api_key = config.TRIBUTE_API_KEY

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """
        Проверить подпись входящего вебхука.
        Tribute подписывает тело запроса через HMAC-SHA256 с API-ключом.
        Подпись передаётся в заголовке trbt-signature.
        """
        expected = hmac.new(
            self.api_key.encode("utf-8"),
            body,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def _request(
        self, method: str, endpoint: str, **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Базовый метод для запросов к Tribute API"""
        url = f"{TRIBUTE_API_URL}/{endpoint}"
        headers = {
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.request(
                    method, url, headers=headers, **kwargs
                ) as resp:
                    data = await resp.json()
                    if resp.status not in (200, 201):
                        logger.error(f"Tribute API HTTP {resp.status}: {data}")
                        return None
                    return data
        except aiohttp.ClientError as e:
            logger.error(f"Tribute сетевая ошибка: {e}")
            return None
        except Exception as e:
            logger.error(f"Tribute неожиданная ошибка: {e}")
            return None

    async def create_order(
        self,
        user_id: int,
        amount_rub: float,
        title: str,
        description: str,
        subscription_type: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Создать разовый заказ в магазине Tribute.

        amount_rub — сумма в рублях (будет переведена в копейки).
        customerId — передаём user_id чтобы в вебхуке знать кому выдать доступ.
        period — "onetime" для разовых платежей.

        Возвращает словарь с полями uuid, paymentUrl, webappPaymentUrl.
        """
        # Tribute принимает сумму в минимальных единицах (копейки для RUB)
        amount_kopecks = int(amount_rub * 100)

        result = await self._request("POST", "shop/orders", json={
            "amount": amount_kopecks,
            "currency": "rub",
            "title": title,
            "description": description,
            "period": "onetime",
            "customerId": str(user_id),
            # Метаданные тарифа передаём в comment — вебхук их не включает,
            # поэтому тариф будем определять по сумме или хранить в БД
            "comment": subscription_type,
        })

        if result:
            logger.info(
                f"Tribute заказ создан: uuid={result.get('uuid')}, "
                f"user={user_id}, amount={amount_rub}₽"
            )
        return result

    async def get_order_status(self, order_uuid: str) -> Optional[str]:
        """
        Получить статус заказа по UUID.
        Возвращает: 'paid' | 'pending' | 'failed' | None
        """
        result = await self._request("GET", f"shop/orders/{order_uuid}/status")
        if result:
            return result.get("status")
        return None


# Синглтон клиента
tribute = TributeClient()
