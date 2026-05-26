"""
handlers/payment.py — Обработка оплаты: выбор метода, создание инвойса, проверка
"""

import asyncio
import logging
import os

from aiogram import Router, Bot
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from database.db import (
    create_payment, update_payment_status, activate_subscription,
    get_pending_payment, set_channel_member
)
from payments.cryptobot import cryptobot
from payments.lava import lava
from payments.tribute import tribute
from texts import PAYMENT_METHOD_TEXT, INVOICE_TEXT, PAYMENT_SUCCESS_TEXT, PAYMENT_PENDING_TEXT, PAYMENT_ERROR_TEXT
from utils.channel import generate_invite_link
from utils.messages import delete_previous_message, save_message_id
from utils.photo_cache import get_file_id
from utils.currency import usd_to_rub

logger = logging.getLogger(__name__)
router = Router()

# Данные тарифов
TARIFFS = {
    "month":   {"name": "1 месяц",  "price": None},
    "3months": {"name": "3 месяца", "price": None},
    "forever": {"name": "Навсегда", "price": None},
}


def get_tariff_price(tariff_key: str) -> float:
    prices = {
        "month":   config.PRICE_1MONTH,
        "3months": config.PRICE_3MONTHS,
        "forever": config.PRICE_FOREVER,
    }
    return prices[tariff_key]


def get_tariff_name(tariff_key: str) -> str:
    names = {
        "month":   "1 месяц",
        "3months": "3 месяца",
        "forever": "Навсегда",
    }
    return names[tariff_key]


def payment_method_keyboard(tariff_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💎 Оплатить криптой (CryptoBot)",
            callback_data=f"pay:cryptobot:{tariff_key}"
        )],
        [InlineKeyboardButton(
            text="💳 Оплатить картой (Tribute)",
            callback_data=f"pay:tribute:{tariff_key}"
        )],
        [InlineKeyboardButton(
            text="💳 Оплатить картой (Lava)",
            callback_data=f"pay:lava:{tariff_key}"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="show_tariffs")],
    ])


def invoice_keyboard(pay_url: str, invoice_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=pay_url)],
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_payment:{invoice_id}")],
        [InlineKeyboardButton(text="🔙 К тарифам", callback_data="show_tariffs")],
    ])


def success_keyboard(invite_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Войти в канал", url=invite_link)],
    ])


# ==========================================
# SELECT TARIFF → PAYMENT METHOD
# ==========================================

@router.callback_query(lambda c: c.data and c.data.startswith("select_tariff:"))
async def select_tariff(callback: CallbackQuery, bot: Bot):
    """Пользователь выбрал тариф — показываем методы оплаты"""
    tariff_key = callback.data.split(":")[1]
    if tariff_key not in ("month", "3months", "forever"):
        await callback.answer("Неверный тариф", show_alert=True)
        return

    await callback.answer()
    price = get_tariff_price(tariff_key)
    name = get_tariff_name(tariff_key)

    await delete_previous_message(bot, callback.from_user.id)

    # Баннер для экрана оплаты (assets/payment.jpg)
    file_id = await get_file_id(bot, config.PAYMENT_BANNER, config.ADMIN_IDS[0])
    text = PAYMENT_METHOD_TEXT(name, price)
    kb = payment_method_keyboard(tariff_key)

    if file_id:
        msg = await bot.send_photo(
            chat_id=callback.from_user.id,
            photo=file_id,
            caption=text,
            parse_mode="HTML",
            reply_markup=kb
        )
    elif os.path.exists(config.PAYMENT_BANNER):
        msg = await bot.send_photo(
            chat_id=callback.from_user.id,
            photo=FSInputFile(config.PAYMENT_BANNER),
            caption=text,
            parse_mode="HTML",
            reply_markup=kb
        )
    else:
        msg = await bot.send_message(
            chat_id=callback.from_user.id,
            text=text,
            parse_mode="HTML",
            reply_markup=kb
        )
    await save_message_id(callback.from_user.id, msg.message_id)


# ==========================================
# CREATE INVOICE
# ==========================================

@router.callback_query(lambda c: c.data and c.data.startswith("pay:"))
async def create_invoice(callback: CallbackQuery, bot: Bot):
    """Создать инвойс в выбранной платёжной системе"""
    _, payment_system, tariff_key = callback.data.split(":")
    user_id = callback.from_user.id
    price = get_tariff_price(tariff_key)
    name = get_tariff_name(tariff_key)

    await callback.answer("Создаю счёт на оплату...")
    await delete_previous_message(bot, user_id)

    invoice_id = None
    pay_url = None

    if payment_system == "cryptobot":
        result = await cryptobot.create_invoice(
            amount=price,
            description=f"Подписка CryptoInsider Pro — {name}",
            payload=f"{user_id}:{tariff_key}"
        )
        if result:
            invoice_id = str(result["invoice_id"])
            pay_url = result["pay_url"]

    elif payment_system == "tribute":
        # Tribute принимает рубли — конвертируем USD
        rub_amount = await usd_to_rub(price)
        result = await tribute.create_order(
            user_id=user_id,
            amount_rub=rub_amount,
            title=f"Подписка — {name}",
            description="Доступ к закрытому каналу CryptoInsider Pro",
            subscription_type=tariff_key,
        )
        if result:
            invoice_id = str(result["uuid"])
            pay_url = result.get("paymentUrl") or result.get("webappPaymentUrl")

    elif payment_system == "lava":
        # Конвертируем USD → RUB по актуальному курсу
        rub_amount = await usd_to_rub(price)
        result = await lava.create_invoice(
            amount_rub=rub_amount,
            order_id=f"{user_id}_{tariff_key}_{int(__import__('time').time())}",
            description=f"Подписка CryptoInsider Pro — {name}"
        )
        if result:
            invoice_id = str(result["id"])
            pay_url = result.get("url") or result.get("payUrl")

    if not invoice_id or not pay_url:
        msg = await bot.send_message(
            chat_id=user_id,
            text="❌ Ошибка создания счёта. Попробуй позже или обратись в поддержку.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К тарифам", callback_data="show_tariffs")]
            ])
        )
        await save_message_id(user_id, msg.message_id)
        return

    # Сохранить платёж в БД вместе с pay_url
    await create_payment(
        user_id=user_id,
        amount=price,
        payment_system=payment_system,
        invoice_id=invoice_id,
        subscription_type=tariff_key,
        pay_url=pay_url
    )

    ps_name = "CryptoBot" if payment_system == "cryptobot" else "Lava"

    # Для Lava показываем сумму в рублях
    if payment_system == "lava":
        rub_display = await usd_to_rub(price)
        invoice_text = INVOICE_TEXT(name, price, ps_name) + f"\n💱 Сумма к оплате: <b>{rub_display:.0f} ₽</b>"
    else:
        invoice_text = INVOICE_TEXT(name, price, ps_name)

    msg = await bot.send_message(
        chat_id=user_id,
        text=invoice_text,
        parse_mode="HTML",
        reply_markup=invoice_keyboard(pay_url, invoice_id)
    )
    await save_message_id(user_id, msg.message_id)
    logger.info(f"Инвойс создан: user={user_id}, system={payment_system}, invoice={invoice_id}")

    # Запустить фоновую автопроверку каждые 5 секунд
    # Если у пользователя уже была задача — отменяем старую
    if user_id in _polling_tasks:
        _polling_tasks[user_id].cancel()
    task = asyncio.create_task(
        _auto_poll(bot, user_id, invoice_id, msg.message_id)
    )
    _polling_tasks[user_id] = task


# ==========================================
# AUTO POLLING — проверка каждые 5 секунд
# ==========================================

# Хранит задачи автопроверки: user_id → asyncio.Task
_polling_tasks: dict[int, asyncio.Task] = {}


async def _auto_poll(bot: Bot, user_id: int, invoice_id: str, message_id: int):
    """
    Фоновая задача: проверяет статус каждые 5 секунд.
    Как только оплата подтверждена — удаляет сообщение с инвойсом
    и отправляет сообщение об успехе. Останавливается через 30 минут.
    """
    payment = await get_pending_payment(user_id)
    if not payment:
        return

    payment_system = payment["payment_system"]
    tariff_key = payment["subscription_type"]
    deadline = asyncio.get_event_loop().time() + 1800  # 30 минут

    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(5)

        try:
            if payment_system == "cryptobot":
                status = await cryptobot.check_payment(invoice_id)
            else:
                status = await lava.check_payment(invoice_id)
        except Exception:
            continue

        if status == "paid":
            await update_payment_status(invoice_id, "paid")
            await activate_subscription(
                user_id=user_id,
                subscription_type=tariff_key,
                amount=payment["amount"]
            )
            await set_channel_member(user_id, True)

            # Удалить сообщение с инвойсом
            try:
                await bot.delete_message(chat_id=user_id, message_id=message_id)
            except Exception:
                pass

            invite_link = await generate_invite_link(bot)
            text = PAYMENT_SUCCESS_TEXT
            kb = success_keyboard(invite_link) if invite_link else None
            msg = await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="HTML",
                reply_markup=kb
            )
            await save_message_id(user_id, msg.message_id)
            logger.info(f"Автопроверка: оплата подтверждена user={user_id}")
            break

        elif status in ("expired", "failed"):
            await update_payment_status(invoice_id, status)
            break

    # Убрать задачу из словаря
    _polling_tasks.pop(user_id, None)


# ==========================================
# CHECK PAYMENT — по кнопке "Я оплатил"
# ==========================================

@router.callback_query(lambda c: c.data and c.data.startswith("check_payment:"))
async def check_payment(callback: CallbackQuery, bot: Bot):
    """Проверить статус платежа по нажатию 'Я оплатил'"""
    invoice_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    payment = await get_pending_payment(user_id)
    if not payment or payment["invoice_id"] != invoice_id:
        await callback.answer("❌ Платёж не найден. Создай новый счёт.", show_alert=True)
        return

    payment_system = payment["payment_system"]
    tariff_key = payment["subscription_type"]

    if payment_system == "cryptobot":
        status = await cryptobot.check_payment(invoice_id)
    elif payment_system == "lava":
        status = await lava.check_payment(invoice_id)
    else:
        status = "failed"

    if status == "paid":
        await callback.answer()
        await update_payment_status(invoice_id, "paid")
        await activate_subscription(
            user_id=user_id,
            subscription_type=tariff_key,
            amount=payment["amount"]
        )
        await set_channel_member(user_id, True)

        # Удалить сообщение с инвойсом
        try:
            await bot.delete_message(chat_id=user_id, message_id=callback.message.message_id)
        except Exception:
            pass

        invite_link = await generate_invite_link(bot)
        msg = await bot.send_message(
            chat_id=user_id,
            text=PAYMENT_SUCCESS_TEXT,
            parse_mode="HTML",
            reply_markup=success_keyboard(invite_link) if invite_link else None
        )
        await save_message_id(user_id, msg.message_id)
        logger.info(f"Оплата подтверждена: user={user_id}, tariff={tariff_key}")

        # Остановить фоновую задачу если была
        if user_id in _polling_tasks:
            _polling_tasks[user_id].cancel()
            _polling_tasks.pop(user_id, None)

    elif status in ("expired", "failed"):
        await callback.answer("❌ Счёт истёк или отменён. Создай новый счёт.", show_alert=True)
        await update_payment_status(invoice_id, status)

    else:  # pending
        await callback.answer(
            "⏳ Оплата пока не поступила. Подожди немного — бот проверяет автоматически.",
            show_alert=True
        )