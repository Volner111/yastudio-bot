"""
handlers/tribute_webhook.py — Приём вебхуков от Tribute Shop API
Запускает отдельный HTTP-сервер на порту 8080 через aiohttp.
"""

import json
import logging
from typing import Optional

from aiohttp import web
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from database.db import (
    get_user_by_username, activate_subscription,
    create_payment, update_payment_status, set_channel_member,
    get_payment_by_invoice
)
from payments.tribute import tribute
from texts import PAYMENT_SUCCESS_TEXT
from utils.channel import generate_invite_link
from utils.messages import save_message_id

logger = logging.getLogger(__name__)


def success_keyboard(invite_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Войти в канал", url=invite_link)]
    ])


def period_to_subscription_type(period: str, amount_rub: float) -> str:
    """
    Определить тип подписки по сумме заказа.
    Так как в comment передаём subscription_type — читаем оттуда через БД.
    """
    # Сравниваем с ценами из конфига (с допуском ±5 рублей)
    prices = {
        "month":   config.TRIBUTE_PRICE_1MONTH,
        "3months": config.TRIBUTE_PRICE_3MONTHS,
        "forever": config.TRIBUTE_PRICE_FOREVER,
    }
    for sub_type, price in prices.items():
        if abs(amount_rub - price) < 5:
            return sub_type
    return "month"  # fallback


async def handle_tribute_webhook(request: web.Request) -> web.Response:
    """
    Обработчик входящих вебхуков от Tribute.
    Проверяет подпись, обрабатывает событие shop_order (оплата).
    """
    # Читаем тело запроса
    body = await request.read()
    signature = request.headers.get("trbt-signature", "")

    # Проверяем подпись HMAC-SHA256
    if not tribute.verify_webhook_signature(body, signature):
        logger.warning("Tribute webhook: неверная подпись")
        return web.json_response({"status": "error"}, status=401)

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return web.json_response({"status": "error"}, status=400)

    event_name = data.get("name")
    payload = data.get("payload", {})

    logger.info(f"Tribute webhook получен: {event_name} | payload={payload}")

    # Обрабатываем только успешную оплату
    if event_name == "shop_order" and payload.get("status") == "paid":
        await handle_payment(request.app["bot"], payload)

    elif event_name == "shop_order_charge_success":
        # Рекуррентное списание — на будущее
        logger.info(f"Tribute рекуррентное списание: {payload.get('uuid')}")

    elif event_name == "shop_order_cancelled":
        await handle_cancellation(payload)

    # Всегда отвечаем 200 — иначе Tribute будет повторять попытки
    return web.json_response({"status": "ok"})


async def handle_payment(bot: Bot, payload: dict):
    """Обработать успешную оплату — активировать подписку и уведомить пользователя"""
    order_uuid = payload.get("uuid")
    amount_kopecks = payload.get("amount", 0)
    currency = payload.get("currency", "rub")
    customer_id = payload.get("customerId", "")  # это наш user_id

    if not customer_id:
        logger.error(f"Tribute webhook: нет customerId в заказе {order_uuid}")
        return

    try:
        user_id = int(customer_id)
    except ValueError:
        logger.error(f"Tribute webhook: неверный customerId={customer_id}")
        return

    # Сумма в рублях
    amount_rub = amount_kopecks / 100

    # Определить тип подписки по сумме
    subscription_type = period_to_subscription_type("onetime", amount_rub)

    # Сохранить платёж в БД
    await create_payment(
        user_id=user_id,
        amount=amount_rub,
        payment_system="tribute",
        invoice_id=order_uuid,
        subscription_type=subscription_type,
        pay_url="",
        currency=currency.upper()
    )

    # Обновить статус
    await update_payment_status(order_uuid, "paid")

    # Активировать подписку
    await activate_subscription(
        user_id=user_id,
        subscription_type=subscription_type,
        amount=amount_rub
    )
    await set_channel_member(user_id, True)

    # Сгенерировать инвайт-ссылку и уведомить пользователя
    invite_link = await generate_invite_link(bot)
    try:
        if invite_link:
            msg = await bot.send_message(
                chat_id=user_id,
                text=PAYMENT_SUCCESS_TEXT,
                parse_mode="HTML",
                reply_markup=success_keyboard(invite_link)
            )
        else:
            msg = await bot.send_message(
                chat_id=user_id,
                text="✅ Оплата прошла! Свяжись с поддержкой для получения ссылки.",
            )
        await save_message_id(user_id, msg.message_id)
        logger.info(f"Tribute: подписка активирована user={user_id}, type={subscription_type}")
    except Exception as e:
        logger.error(f"Tribute: не удалось уведомить пользователя {user_id}: {e}")


async def handle_cancellation(payload: dict):
    """Обработать отмену заказа (для логов)"""
    order_uuid = payload.get("uuid")
    reason = payload.get("cancelReason", "unknown")
    logger.info(f"Tribute заказ отменён: uuid={order_uuid}, причина={reason}")
    if order_uuid:
        await update_payment_status(order_uuid, "failed")


def create_webhook_app(bot: Bot) -> web.Application:
    """Создать aiohttp приложение для приёма вебхуков"""
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/tribute/webhook", handle_tribute_webhook)
    # Health check endpoint
    app.router.add_get("/health", lambda r: web.json_response({"status": "ok"}))
    return app
