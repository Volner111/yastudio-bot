"""
handlers/start.py — Главный экран и воронка
Welcome → Как работает → Возможности → Почему мы → Цены
"""

import asyncio
import logging
import os

from aiogram import Router, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from database.db import upsert_user, get_user
from texts import WELCOME_TEXT, BOT_FEATURES_TEXT, CAPABILITIES_TEXT, WHY_US_TEXT
from utils.messages import delete_previous_message, save_message_id
from utils.photo_cache import get_file_id

logger = logging.getLogger(__name__)
router = Router()


# ==========================================
# KEYBOARDS
# ==========================================

def welcome_keyboard_first() -> InlineKeyboardMarkup:
    """Новый пользователь — без кнопки тарифов"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="• Как это работает •", callback_data="bot_features")],
        [InlineKeyboardButton(text="💬 Обсудить проект", url=config.SUPPORT_LINK)],
    ])


def welcome_keyboard_returning() -> InlineKeyboardMarkup:
    """Вернувшийся — с кнопкой тарифов"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="• Как это работает •", callback_data="bot_features")],
        [InlineKeyboardButton(text="Цены", callback_data="show_tariffs"),
        InlineKeyboardButton(text="💬 Обсудить проект", url=config.SUPPORT_LINK)],
    ])


def bot_features_keyboard() -> InlineKeyboardMarkup:
    """Как это работает"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="• Возможности •", callback_data="capabilities")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_start"),
        InlineKeyboardButton(text="💬 Обсудить проект", url=config.SUPPORT_LINK),
        InlineKeyboardButton(text="Цены", callback_data="show_tariffs"),]
    ])


def capabilities_keyboard() -> InlineKeyboardMarkup:
    """Возможности"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="• Цены •", callback_data="show_tariffs")],
        [InlineKeyboardButton(text="Назад", callback_data="bot_features"),
        InlineKeyboardButton(text="💬 Обсудить проект", url=config.SUPPORT_LINK)],
    ])


def why_us_keyboard() -> InlineKeyboardMarkup:
    """Почему мы"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="• Посмотреть цены •", callback_data="show_tariffs")],
        [InlineKeyboardButton(text="💬 Обсудить проект", url=config.SUPPORT_LINK)],
    ])


# ==========================================
# SEND WELCOME
# ==========================================

async def send_welcome(bot: Bot, user_id: int, is_returning: bool = False):
    kb = welcome_keyboard_returning() if is_returning else welcome_keyboard_first()
    file_id = await get_file_id(bot, config.WELCOME_BANNER, config.ADMIN_IDS[0])

    if file_id:
        msg = await bot.send_photo(
            chat_id=user_id, photo=file_id,
            caption=WELCOME_TEXT, parse_mode="HTML", reply_markup=kb
        )
    elif os.path.exists(config.WELCOME_BANNER):
        msg = await bot.send_photo(
            chat_id=user_id, photo=FSInputFile(config.WELCOME_BANNER),
            caption=WELCOME_TEXT, parse_mode="HTML", reply_markup=kb
        )
    else:
        msg = await bot.send_message(
            chat_id=user_id, text=WELCOME_TEXT,
            parse_mode="HTML", reply_markup=kb
        )
    await save_message_id(user_id, msg.message_id)


# ==========================================
# /start
# ==========================================

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user = message.from_user
    existing = await get_user(user.id)
    is_returning = existing is not None

    await upsert_user(user_id=user.id, username=user.username, full_name=user.full_name)

    # Для новых — точка убирает плашку «Старт», остаётся навсегда
    if not is_returning:
        try:
            await message.delete()
            await bot.send_message(chat_id=user.id, text="·")
        except Exception:
            pass
    else:
        try:
            await message.delete()
        except Exception:
            pass

    await delete_previous_message(bot, user.id)
    await send_welcome(bot, user.id, is_returning=is_returning)
    logger.info(f"{'Возврат' if is_returning else 'Новый'} пользователь {user.id} (@{user.username})")


# ==========================================
# BACK TO START
# ==========================================

@router.callback_query(lambda c: c.data == "back_to_start")
async def back_to_start(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    await delete_previous_message(bot, callback.from_user.id)
    await send_welcome(bot, callback.from_user.id, is_returning=True)


# ==========================================
# КАК ЭТО РАБОТАЕТ
# ==========================================

@router.callback_query(lambda c: c.data == "bot_features")
async def show_bot_features(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    await delete_previous_message(bot, callback.from_user.id)
    msg = await bot.send_message(
        chat_id=callback.from_user.id,
        text=BOT_FEATURES_TEXT,
        parse_mode="HTML",
        reply_markup=bot_features_keyboard()
    )
    await save_message_id(callback.from_user.id, msg.message_id)


# ==========================================
# ВОЗМОЖНОСТИ
# ==========================================

@router.callback_query(lambda c: c.data == "capabilities")
async def show_capabilities(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    await delete_previous_message(bot, callback.from_user.id)
    msg = await bot.send_message(
        chat_id=callback.from_user.id,
        text=CAPABILITIES_TEXT,
        parse_mode="HTML",
        reply_markup=capabilities_keyboard()
    )
    await save_message_id(callback.from_user.id, msg.message_id)


# ==========================================
# ПОЧЕМУ МЫ
# ==========================================

@router.callback_query(lambda c: c.data == "why_us")
async def show_why_us(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    await delete_previous_message(bot, callback.from_user.id)
    msg = await bot.send_message(
        chat_id=callback.from_user.id,
        text=WHY_US_TEXT,
        parse_mode="HTML",
        reply_markup=why_us_keyboard()
    )
    await save_message_id(callback.from_user.id, msg.message_id)


# ==========================================
# /info
# ==========================================

@router.message(Command("info"))
async def cmd_info(message: Message, bot: Bot):
    try:
        dot = await message.answer("·")
        await message.delete()
        await dot.delete()
    except Exception:
        pass

    await delete_previous_message(bot, message.from_user.id)
    msg = await bot.send_message(
        chat_id=message.from_user.id,
        text="ℹ️ <b>Информация для клиента</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📄 Политика конфиденциальности",
                url="https://telegra.ph/Politika-konfidencialnosti-04-01-26"
            )],
            [InlineKeyboardButton(
                text="📋 Пользовательское соглашение",
                url="https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"
            )],
        ])
    )
    await save_message_id(message.from_user.id, msg.message_id)
