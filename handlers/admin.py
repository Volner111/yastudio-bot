"""
handlers/admin.py — Панель администратора
Статистика, рассылка, ручная выдача доступа
"""

import asyncio
import logging
from typing import Optional

from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)

from config import config
from database.db import (
    get_stats, get_all_users, get_active_subscribers,
    get_former_subscribers, get_never_paid_users,
    get_user_by_username, activate_subscription
)
from texts import (
    ADMIN_WELCOME_TEXT, ADMIN_STATS_TEXT,
    BROADCAST_SELECT_AUDIENCE, BROADCAST_SELECT_CONTENT,
    BROADCAST_ENTER_TEXT, BROADCAST_ENTER_PHOTO,
    BROADCAST_ENTER_TEXT_AND_PHOTO, BROADCAST_ENTER_VIDEO_NOTE,
    BROADCAST_ENTER_BUTTON, BROADCAST_PREVIEW, BROADCAST_DONE,
    MANUAL_ACCESS_ENTER_USERNAME, MANUAL_ACCESS_SELECT_TARIFF,
    MANUAL_ACCESS_SUCCESS, MANUAL_ACCESS_USER_NOT_FOUND,
    MANUAL_ACCESS_NOTIFICATION
)
from utils.channel import generate_invite_link
from utils.messages import delete_previous_message, save_message_id

logger = logging.getLogger(__name__)
router = Router()


# ==========================================
# FSM STATES
# ==========================================

class BroadcastStates(StatesGroup):
    select_audience = State()
    select_content_type = State()
    enter_text = State()
    enter_photo = State()
    enter_text_for_photo = State()
    enter_photo_for_text = State()
    enter_video_note = State()
    enter_button = State()
    preview = State()


class ManualAccessStates(StatesGroup):
    enter_username = State()
    select_tariff = State()


# ==========================================
# ADMIN CHECK FILTER
# ==========================================

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


# ==========================================
# KEYBOARDS
# ==========================================

def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 За сегодня", callback_data="admin_stats:today"),
            InlineKeyboardButton(text="📈 За 7 дней", callback_data="admin_stats:week"),
        ],
        [
            InlineKeyboardButton(text="📉 За 30 дней", callback_data="admin_stats:month"),
            InlineKeyboardButton(text="👥 Всего", callback_data="admin_stats:all"),
        ],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="👤 Выдать доступ", callback_data="admin_manual_access")],
    ])


def broadcast_audience_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Все пользователи", callback_data="bc_aud:all")],
        [InlineKeyboardButton(text="✅ Активные подписчики", callback_data="bc_aud:active")],
        [InlineKeyboardButton(text="🔄 Бывшие подписчики", callback_data="bc_aud:former")],
        [InlineKeyboardButton(text="🆕 Никогда не платили", callback_data="bc_aud:never_paid")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")],
    ])


def broadcast_content_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data="bc_type:text")],
        [InlineKeyboardButton(text="🖼 Фото", callback_data="bc_type:photo")],
        [InlineKeyboardButton(text="📝+🖼 Текст + Фото", callback_data="bc_type:text_photo")],
        [InlineKeyboardButton(text="⭕ Кружочек", callback_data="bc_type:video_note")],
        [InlineKeyboardButton(text="📝+🔘 Текст + Фото + Кнопка", callback_data="bc_type:text_photo_button")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")],
    ])


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Разослать", callback_data="bc_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel"),
        ]
    ])


def manual_tariff_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📅 1 месяц", callback_data="ma_tariff:month")],
        [InlineKeyboardButton(text=f"📆 3 месяца", callback_data="ma_tariff:3months")],
        [InlineKeyboardButton(text=f"♾️ Навсегда", callback_data="ma_tariff:forever")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")],
    ])

# ==========================================
# /admin COMMAND
# ==========================================

@router.message(Command("admin"))
async def cmd_admin(message: Message, bot: Bot):
    """Главное меню администратора"""
    if not is_admin(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    await delete_previous_message(bot, message.from_user.id)
    msg = await bot.send_message(
        chat_id=message.from_user.id,
        text=ADMIN_WELCOME_TEXT,
        parse_mode="HTML",
        reply_markup=admin_main_keyboard()
    )
    await save_message_id(message.from_user.id, msg.message_id)


# ==========================================
# STATISTICS
# ==========================================

@router.callback_query(lambda c: c.data and c.data.startswith("admin_stats:"))
async def show_stats(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    period = callback.data.split(":")[1]
    await callback.answer()

    stats = await get_stats(period)

    if period == "all":
        text = ADMIN_STATS_TEXT(
            period="all",
            new_users=0, new_payments=0, total_amount=0,
            total_users=stats["total_users"],
            active_subs=stats["active_subs"],
            total_earned=stats["total_earned"]
        )
    else:
        text = ADMIN_STATS_TEXT(
            period=period,
            new_users=stats["new_users"],
            new_payments=stats["new_payments"],
            total_amount=stats["total_amount"]
        )

    await delete_previous_message(bot, callback.from_user.id)
    msg = await bot.send_message(
        chat_id=callback.from_user.id,
        text=text,
        parse_mode="HTML",
        reply_markup=admin_main_keyboard()
    )
    await save_message_id(callback.from_user.id, msg.message_id)


# ==========================================
# BROADCAST
# ==========================================

@router.callback_query(lambda c: c.data == "admin_broadcast")
async def start_broadcast(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    await state.set_state(BroadcastStates.select_audience)
    await delete_previous_message(bot, callback.from_user.id)
    msg = await bot.send_message(
        chat_id=callback.from_user.id,
        text=BROADCAST_SELECT_AUDIENCE,
        parse_mode="HTML",
        reply_markup=broadcast_audience_keyboard()
    )
    await save_message_id(callback.from_user.id, msg.message_id)


@router.callback_query(lambda c: c.data and c.data.startswith("bc_aud:"))
async def select_audience(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    audience = callback.data.split(":")[1]
    await state.update_data(audience=audience)
    await state.set_state(BroadcastStates.select_content_type)
    await callback.answer()
    await delete_previous_message(bot, callback.from_user.id)
    msg = await bot.send_message(
        chat_id=callback.from_user.id,
        text=BROADCAST_SELECT_CONTENT,
        parse_mode="HTML",
        reply_markup=broadcast_content_keyboard()
    )
    await save_message_id(callback.from_user.id, msg.message_id)


@router.callback_query(lambda c: c.data and c.data.startswith("bc_type:"))
async def select_content_type(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    content_type = callback.data.split(":")[1]
    await state.update_data(content_type=content_type)
    await callback.answer()
    await delete_previous_message(bot, callback.from_user.id)

    if content_type == "text":
        await state.set_state(BroadcastStates.enter_text)
        prompt = BROADCAST_ENTER_TEXT
    elif content_type == "photo":
        await state.set_state(BroadcastStates.enter_photo)
        prompt = BROADCAST_ENTER_PHOTO
    elif content_type in ("text_photo", "text_photo_button"):
        await state.set_state(BroadcastStates.enter_text_for_photo)
        prompt = BROADCAST_ENTER_TEXT_AND_PHOTO
    elif content_type == "video_note":
        await state.set_state(BroadcastStates.enter_video_note)
        prompt = BROADCAST_ENTER_VIDEO_NOTE
    else:
        prompt = "Отправь контент:"

    msg = await bot.send_message(
        chat_id=callback.from_user.id,
        text=prompt,
        parse_mode="HTML"
    )
    await save_message_id(callback.from_user.id, msg.message_id)


@router.message(BroadcastStates.enter_text)
async def bc_got_text(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(text=message.text or message.caption)
    await message.delete()
    await _show_broadcast_preview(bot, message.from_user.id, state)


@router.message(BroadcastStates.enter_photo)
async def bc_got_photo(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.photo:
        await message.reply("Пожалуйста, отправь фото.")
        return
    await state.update_data(photo_id=message.photo[-1].file_id)
    await message.delete()
    await _show_broadcast_preview(bot, message.from_user.id, state)


@router.message(BroadcastStates.enter_text_for_photo)
async def bc_got_text_for_photo(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(text=message.text or message.caption)
    await state.set_state(BroadcastStates.enter_photo_for_text)
    await message.delete()
    await delete_previous_message(bot, message.from_user.id)
    msg = await bot.send_message(
        chat_id=message.from_user.id,
        text="Теперь отправь фото:"
    )
    await save_message_id(message.from_user.id, msg.message_id)


@router.message(BroadcastStates.enter_photo_for_text)
async def bc_got_photo_for_text(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.photo:
        await message.reply("Пожалуйста, отправь фото.")
        return
    await state.update_data(photo_id=message.photo[-1].file_id)
    data = await state.get_data()
    await message.delete()

    if data.get("content_type") == "text_photo_button":
        await state.set_state(BroadcastStates.enter_button)
        await delete_previous_message(bot, message.from_user.id)
        msg = await bot.send_message(
            chat_id=message.from_user.id,
            text=BROADCAST_ENTER_BUTTON,
            parse_mode="HTML"
        )
        await save_message_id(message.from_user.id, msg.message_id)
    else:
        await _show_broadcast_preview(bot, message.from_user.id, state)


@router.message(BroadcastStates.enter_button)
async def bc_got_button(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    text = message.text or ""
    if "|" not in text:
        await message.reply("Неверный формат. Используй: <code>Текст кнопки | https://url.com</code>", parse_mode="HTML")
        return
    btn_text, btn_url = text.split("|", 1)
    await state.update_data(button_text=btn_text.strip(), button_url=btn_url.strip())
    await message.delete()
    await _show_broadcast_preview(bot, message.from_user.id, state)


@router.message(BroadcastStates.enter_video_note)
async def bc_got_video_note(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.video_note:
        await message.reply("Пожалуйста, отправь видео-кружочек.")
        return
    await state.update_data(video_note_id=message.video_note.file_id)
    await message.delete()
    await _show_broadcast_preview(bot, message.from_user.id, state)


async def _show_broadcast_preview(bot: Bot, user_id: int, state: FSMContext):
    """Показать превью рассылки"""
    await state.set_state(BroadcastStates.preview)
    data = await state.get_data()
    await delete_previous_message(bot, user_id)

    content_type = data.get("content_type")
    text = data.get("text", "")
    photo_id = data.get("photo_id")
    video_note_id = data.get("video_note_id")
    btn_text = data.get("button_text")
    btn_url = data.get("button_url")

    btn_kb = None
    if btn_text and btn_url:
        btn_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, url=btn_url)]
        ])

    # Отправить превью
    try:
        if content_type == "text":
            await bot.send_message(chat_id=user_id, text=f"👁 ПРЕВЬЮ:\n\n{text}", parse_mode="HTML")
        elif content_type == "photo":
            await bot.send_photo(chat_id=user_id, photo=photo_id, caption="👁 ПРЕВЬЮ")
        elif content_type in ("text_photo", "text_photo_button"):
            await bot.send_photo(
                chat_id=user_id, photo=photo_id,
                caption=f"👁 ПРЕВЬЮ:\n\n{text}", parse_mode="HTML",
                reply_markup=btn_kb
            )
        elif content_type == "video_note":
            await bot.send_video_note(chat_id=user_id, video_note=video_note_id)
    except Exception as e:
        logger.error(f"Ошибка показа превью: {e}")

    msg = await bot.send_message(
        chat_id=user_id,
        text=BROADCAST_PREVIEW,
        parse_mode="HTML",
        reply_markup=broadcast_confirm_keyboard()
    )
    await save_message_id(user_id, msg.message_id)


@router.callback_query(lambda c: c.data == "bc_confirm")
async def confirm_broadcast(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("Начинаю рассылку...")

    data = await state.get_data()
    audience = data.get("audience", "all")

    # Получить список получателей
    if audience == "all":
        users = await get_all_users()
    elif audience == "active":
        users = await get_active_subscribers()
    elif audience == "former":
        users = await get_former_subscribers()
    elif audience == "never_paid":
        users = await get_never_paid_users()
    else:
        users = []

    await state.clear()
    await delete_previous_message(bot, callback.from_user.id)

    # Уведомить об начале рассылки
    status_msg = await bot.send_message(
        chat_id=callback.from_user.id,
        text=f"📢 Начинаю рассылку для {len(users)} пользователей..."
    )
    await save_message_id(callback.from_user.id, status_msg.message_id)

    content_type = data.get("content_type")
    text = data.get("text", "")
    photo_id = data.get("photo_id")
    video_note_id = data.get("video_note_id")
    btn_text = data.get("button_text")
    btn_url = data.get("button_url")

    btn_kb = None
    if btn_text and btn_url:
        btn_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, url=btn_url)]
        ])

    sent = 0
    errors = 0

    for user in users:
        uid = user["user_id"]
        try:
            if content_type == "text":
                await bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            elif content_type == "photo":
                await bot.send_photo(chat_id=uid, photo=photo_id)
            elif content_type in ("text_photo", "text_photo_button"):
                await bot.send_photo(
                    chat_id=uid, photo=photo_id,
                    caption=text, parse_mode="HTML",
                    reply_markup=btn_kb
                )
            elif content_type == "video_note":
                await bot.send_video_note(chat_id=uid, video_note=video_note_id)
            sent += 1
        except Exception as e:
            logger.warning(f"Ошибка рассылки для {uid}: {e}")
            errors += 1

        # Защита от флуда
        await asyncio.sleep(0.05)

    await delete_previous_message(bot, callback.from_user.id)
    msg = await bot.send_message(
        chat_id=callback.from_user.id,
        text=BROADCAST_DONE(sent, errors),
        parse_mode="HTML",
        reply_markup=admin_main_keyboard()
    )
    await save_message_id(callback.from_user.id, msg.message_id)


# ==========================================
# MANUAL ACCESS
# ==========================================

@router.callback_query(lambda c: c.data == "admin_manual_access")
async def start_manual_access(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(ManualAccessStates.enter_username)
    await delete_previous_message(bot, callback.from_user.id)
    msg = await bot.send_message(
        chat_id=callback.from_user.id,
        text=MANUAL_ACCESS_ENTER_USERNAME,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")]
        ])
    )
    await save_message_id(callback.from_user.id, msg.message_id)


@router.message(ManualAccessStates.enter_username)
async def got_username(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    username = (message.text or "").strip().lstrip("@")
    user = await get_user_by_username(username)
    await message.delete()

    if not user:
        await delete_previous_message(bot, message.from_user.id)
        msg = await bot.send_message(
            chat_id=message.from_user.id,
            text=MANUAL_ACCESS_USER_NOT_FOUND,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_manual_access")]
            ])
        )
        await save_message_id(message.from_user.id, msg.message_id)
        return

    await state.update_data(target_user_id=user["user_id"], target_username=username)
    await state.set_state(ManualAccessStates.select_tariff)
    await delete_previous_message(bot, message.from_user.id)
    msg = await bot.send_message(
        chat_id=message.from_user.id,
        text=MANUAL_ACCESS_SELECT_TARIFF,
        parse_mode="HTML",
        reply_markup=manual_tariff_keyboard()
    )
    await save_message_id(message.from_user.id, msg.message_id)


@router.callback_query(lambda c: c.data and c.data.startswith("ma_tariff:"))
async def manual_access_tariff(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    tariff_key = callback.data.split(":")[1]
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    target_username = data.get("target_username")
    await state.clear()

    tariff_names = {"month": "1 месяц", "3months": "3 месяца", "forever": "Навсегда"}
    tariff_name = tariff_names.get(tariff_key, tariff_key)

    # Активировать подписку (ручная выдача)
    await activate_subscription(
        user_id=target_user_id,
        subscription_type=tariff_key,
        amount=0,
        manual=True
    )

    # Генерируем инвайт-ссылку
    invite_link = await generate_invite_link(bot)

    # Уведомить пользователя
    if invite_link:
        try:
            await bot.send_message(
                chat_id=target_user_id,
                text=MANUAL_ACCESS_NOTIFICATION(tariff_name),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Войти в канал", url=invite_link)]
                ])
            )
        except Exception as e:
            logger.warning(f"Не удалось уведомить пользователя {target_user_id}: {e}")

    await callback.answer()
    await delete_previous_message(bot, callback.from_user.id)
    msg = await bot.send_message(
        chat_id=callback.from_user.id,
        text=MANUAL_ACCESS_SUCCESS(target_username, tariff_name),
        parse_mode="HTML",
        reply_markup=admin_main_keyboard()
    )
    await save_message_id(callback.from_user.id, msg.message_id)


# ==========================================
# CANCEL
# ==========================================

@router.callback_query(lambda c: c.data == "admin_cancel")
async def admin_cancel(callback: CallbackQuery, bot: Bot, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.answer()
    await delete_previous_message(bot, callback.from_user.id)
    msg = await bot.send_message(
        chat_id=callback.from_user.id,
        text=ADMIN_WELCOME_TEXT,
        parse_mode="HTML",
        reply_markup=admin_main_keyboard()
    )
    await save_message_id(callback.from_user.id, msg.message_id)
