"""
payments/lava.py — Интеграция с Lava.ru (новое API v2)
Документация: https://dev.lava.ru/
"""

import hashlib
import hmac
import logging
from typing import Optional, Dict, Any

import aiohttp

from config import config

logger = logging.getLogger(__name__)

LAVA_API_URL = "https://api.lava.ru/business"


class LavaClient:
    """Клиент для работы с Lava.ru API v2"""

    def __init__(self):
        self.api_key = config.LAVA_API_KEY
        self.shop_id = config.LAVA_SHOP_ID

    def _sign(self, body: str) -> str:
        """
        Подпись запроса для Lava API v2.
        HMAC-SHA256 от тела запроса с использованием API-ключа.
        """
        return hmac.new(
            self.api_key.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    async def _request(self, endpoint: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Базовый метод POST-запроса к Lava API v2"""
        import json
        url = f"{LAVA_API_URL}/{endpoint}"
        body = json.dumps(data)
        signature = self._sign(body)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Signature": signature,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=body, headers=headers) as resp:
                    result = await resp.json()
                    if resp.status != 200:
                        logger.error(f"Lava API HTTP {resp.status}: {result}")
                        return None
                    # Lava v2 возвращает {"data": {...}, "status": 200}
                    if result.get("status") not in (200, "success", 1):
                        logger.error(f"Lava API error: {result}")
                        return None
                    return result.get("data") or result
        except aiohttp.ClientError as e:
            logger.error(f"Lava сетевая ошибка: {e}")
            return None
        except Exception as e:
            logger.error(f"Lava неожиданная ошибка: {e}")
            return None

    async def create_invoice(
        self,
        amount_rub: float,
        order_id: str,
        description: str,
        expire: int = 1800
    ) -> Optional[Dict[str, Any]]:
        """
        Создать счёт на оплату в рублях.
        Возвращает словарь с полями: id, url и др.
        """
        result = await self._request("invoice/create", {
            "shopId": self.shop_id,
            "sum": amount_rub,
            "orderId": order_id,
            "description": description,
            "expire": expire,
        })
        if result:
            logger.info(f"Lava инвойс создан: {result.get('id')}")
        return result

    async def get_invoice(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Получить информацию об инвойсе по ID"""
        result = await self._request("invoice/info", {
            "shopId": self.shop_id,
            "invoiceId": invoice_id,
        })
        return result

    async def check_payment(self, invoice_id: str) -> str:
        """
        Проверить статус платежа.
        Возвращает: 'paid' | 'pending' | 'expired' | 'failed'
        """
        try:
            invoice = await self.get_invoice(invoice_id)
            if not invoice:
                return "failed"
            status = invoice.get("status", "pending")
            # Lava v2 статусы: pending, success, fail, expire
            if status == "success":
                return "paid"
            elif status in ("fail", "expire", "expired"):
                return "expired"
            else:
                return "pending"
        except Exception as e:
            logger.error(f"Ошибка проверки платежа Lava {invoice_id}: {e}")
            return "failed"


# Синглтон клиента
lava = LavaClient()