"""
handlers/tariffs.py — Экран тарифов и отработки возражений
"""

import logging
import os

from aiogram import Router, Bot
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from texts import TARIFFS_TEXT, OBJECTIONS_TEXT
from utils.messages import delete_previous_message, save_message_id
from utils.photo_cache import get_file_id

logger = logging.getLogger(__name__)
router = Router()


def tariffs_keyboard() -> InlineKeyboardMarkup:
    discount_3m = round((1 - (config.PRICE_3MONTHS / (config.PRICE_1MONTH * 3))) * 100)
    return InlineKeyboardMarkup(inline_keyboard=[
        # Первая строка: 1 месяц и 3 месяца рядом
        [
            InlineKeyboardButton(
                text=f"• Бот — ${config.PRICE_1MONTH}",
                callback_data="select_tariff:month"
            ),
            InlineKeyboardButton(
                text=f"• Сайт — ${config.PRICE_3MONTHS} (-{discount_3m}%)",
                callback_data="select_tariff:3months"
            ),
        ],
        # Вторая строка: навсегда на всю ширину
        [InlineKeyboardButton(
            text=f"• Дизайн — ${config.PRICE_FOREVER}",
            callback_data="select_tariff:forever"
        )],
        # Третья строка: три кнопки
        [
            InlineKeyboardButton(text="✅ Почему мы ", callback_data="why_us"),
            InlineKeyboardButton(text="💬 Обратная связь", url=config.SUPPORT_LINK),
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start"),
        ],
    ])


def objections_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К тарифам", callback_data="show_tariffs")],
        [InlineKeyboardButton(text="💬 Обратная связь", url=config.SUPPORT_LINK)],
    ])


async def send_tariffs(bot: Bot, user_id: int):
    """Отправить экран тарифов"""
    kb = tariffs_keyboard()
    text = TARIFFS_TEXT()

    file_id = await get_file_id(bot, config.TARIFFS_BANNER, config.ADMIN_IDS[0])

    if file_id:
        msg = await bot.send_photo(
            chat_id=user_id,
            photo=file_id,          # ← мгновенно
            caption=text,
            parse_mode="HTML",
            reply_markup=kb
        )
    elif os.path.exists(config.TARIFFS_BANNER):
        msg = await bot.send_photo(
            chat_id=user_id,
            photo=FSInputFile(config.TARIFFS_BANNER),
            caption=text,
            parse_mode="HTML",
            reply_markup=kb
        )
    else:
        msg = await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML",
            reply_markup=kb
        )
    await save_message_id(user_id, msg.message_id)


@router.callback_query(lambda c: c.data == "show_tariffs")
async def show_tariffs(callback: CallbackQuery, bot: Bot):
    """Показать экран тарифов"""
    await callback.answer()
    await delete_previous_message(bot, callback.from_user.id)
    await send_tariffs(bot, callback.from_user.id)


@router.callback_query(lambda c: c.data == "objections")
async def show_objections(callback: CallbackQuery, bot: Bot):
    """Показать блок отработки возражений"""
    await callback.answer()
    await delete_previous_message(bot, callback.from_user.id)
    msg = await bot.send_message(
        chat_id=callback.from_user.id,
        text=OBJECTIONS_TEXT,
        parse_mode="HTML",
        reply_markup=objections_keyboard()
    )
    await save_message_id(callback.from_user.id, msg.message_id)
