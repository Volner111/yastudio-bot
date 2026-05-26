"""
payments/cryptobot.py — Интеграция с CryptoBot (crypto.bot)
Документация API: https://help.crypt.bot/crypto-pay-api
"""

import logging
from typing import Optional, Dict, Any

import aiohttp

from config import config

logger = logging.getLogger(__name__)

CRYPTOBOT_API_URL = "https://pay.crypt.bot/api"
# Для тестнета используйте: "https://testnet-pay.crypt.bot/api"


class CryptoBotClient:
    """Клиент для работы с CryptoBot Pay API"""

    def __init__(self):
        self.token = config.CRYPTOBOT_TOKEN
        self.headers = {"Crypto-Pay-API-Token": self.token}

    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Базовый метод для HTTP-запросов к API"""
        url = f"{CRYPTOBOT_API_URL}/{endpoint}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method, url, headers=self.headers, **kwargs
                ) as resp:
                    data = await resp.json()
                    if not data.get("ok"):
                        logger.error(f"CryptoBot API error: {data}")
                        return None
                    return data.get("result")
        except aiohttp.ClientError as e:
            logger.error(f"CryptoBot сетевая ошибка: {e}")
            return None
        except Exception as e:
            logger.error(f"CryptoBot неожиданная ошибка: {e}")
            return None

    async def create_invoice(
        self,
        amount: float,
        description: str,
        payload: str = "",
        currency: str = "USDT"
    ) -> Optional[Dict[str, Any]]:
        """
        Создать инвойс на оплату.
        Возвращает словарь с полями: invoice_id, pay_url, status и др.
        """
        result = await self._request("POST", "createInvoice", json={
            "asset": currency,
            "amount": str(amount),
            "description": description,
            "payload": payload,
            "expires_in": 1800,  # 30 минут
            "allow_comments": False,
            "allow_anonymous": False,
        })
        if result:
            logger.info(f"CryptoBot инвойс создан: {result.get('invoice_id')}")
        return result

    async def get_invoice(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию об инвойсе по его ID"""
        result = await self._request("GET", "getInvoices", params={
            "invoice_ids": str(invoice_id)
        })
        if result and result.get("items"):
            return result["items"][0]
        return None

    async def check_payment(self, invoice_id: str) -> str:
        """
        Проверить статус платежа.
        Возвращает: 'paid' | 'pending' | 'expired' | 'failed'
        """
        try:
            invoice = await self.get_invoice(int(invoice_id))
            if not invoice:
                return "failed"
            status = invoice.get("status", "pending")
            # CryptoBot статусы: active, paid, expired
            if status == "paid":
                return "paid"
            elif status == "expired":
                return "expired"
            else:
                return "pending"
        except Exception as e:
            logger.error(f"Ошибка проверки платежа CryptoBot {invoice_id}: {e}")
            return "failed"


# Синглтон клиента
cryptobot = CryptoBotClient()
