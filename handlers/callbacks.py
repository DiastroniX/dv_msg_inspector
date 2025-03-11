from aiogram import Router, types, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import (
    revoke_penalty,
    get_deleted_message_by_id,
    reset_all_user_data
)
from data.texts import TEXTS
import pytz
import datetime

callbacks_router = Router(name="callbacks_router")


@callbacks_router.callback_query(lambda call: call.data and call.data.startswith("revoke_penalty:"))
async def revoke_penalty_handler(call: CallbackQuery, bot: Bot, config):
    parts = call.data.split(":")
    if len(parts) < 2:
        return
    user_id = int(parts[1])
    
    # 1. Снимаем все санкции в БД
    await revoke_penalty(user_id)
    
    # 2. Сбрасываем все счетчики и историю нарушений
    await reset_all_user_data(user_id)
    
    # 3. Пытаемся разбанить в Telegram (если нужно)
    try:
        for group_id in config.allowed_groups:
            await bot.unban_chat_member(group_id, user_id)
    except Exception:
        pass

    # Обновляем клавиатуру: меняем кнопку "revoke_penalty" на "✅ Выполнено"
    if call.message and call.message.reply_markup:
        markup = call.message.reply_markup
        new_keyboard = []
        for row in markup.inline_keyboard:
            new_row = []
            for button in row:
                if button.callback_data and button.callback_data.startswith("revoke_penalty:"):
                    new_row.append(InlineKeyboardButton(text="✅ Выполнено", callback_data="done"))
                else:
                    new_row.append(button)
            new_keyboard.append(new_row)
        new_markup = InlineKeyboardMarkup(inline_keyboard=new_keyboard)
        await bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=new_markup
        )
    await call.answer("Все ограничения сняты, история нарушений очищена!", show_alert=True)


@callbacks_router.callback_query(lambda call: call.data and call.data.startswith("reset_violations:"))
async def reset_violations_handler(call: CallbackQuery, bot: Bot, config):
    parts = call.data.split(":")
    if len(parts) < 2:
        return
    user_id = int(parts[1])
    
    # Полный сброс всех данных о нарушениях
    await reset_all_user_data(user_id)

    # Обновляем клавиатуру: меняем кнопку "reset_violations" на "✅ Выполнено"
    if call.message and call.message.reply_markup:
        markup = call.message.reply_markup
        new_keyboard = []
        for row in markup.inline_keyboard:
            new_row = []
            for button in row:
                if button.callback_data and button.callback_data.startswith("reset_violations:"):
                    new_row.append(InlineKeyboardButton(text="✅ Выполнено", callback_data="done"))
                else:
                    new_row.append(button)
            new_keyboard.append(new_row)
        new_markup = InlineKeyboardMarkup(inline_keyboard=new_keyboard)
        await bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=new_markup
        )
    await call.answer("Все счетчики нарушений сброшены!", show_alert=True)


@callbacks_router.callback_query(lambda call: call.data and call.data.startswith("restore_message:"))
async def restore_message_handler(call: CallbackQuery, bot: Bot, config):
    parts = call.data.split(":")
    if len(parts) < 2:
        return
    deleted_msg_id = int(parts[1])
    row = await get_deleted_message_by_id(deleted_msg_id)
    if not row:
        await call.answer("Сообщение не найдено в БД.", show_alert=True)
        return
    # row = (id, user_id, user_name, group_id, message_text, timestamp)
    _, usr_id, usr_name, grp_id, msg_text, timestamp = row

    # Конвертируем timestamp в московское время
    msk_tz = pytz.timezone('Europe/Moscow')
    dt = datetime.datetime.fromtimestamp(timestamp, msk_tz)
    formatted_date = dt.strftime("%d/%m/%y %H:%M")

    text_to_post = TEXTS["message_restored"].format(
        user_name=usr_name,
        message_text=msg_text,
        formatted_date=formatted_date
    )
    
    await bot.send_message(grp_id, text_to_post, parse_mode="HTML")

    # Обновляем клавиатуру: меняем кнопку "restore_message" на "✅ Восстановлено"
    if call.message and call.message.reply_markup:
        markup = call.message.reply_markup
        new_keyboard = []
        for row in markup.inline_keyboard:
            new_row = []
            for button in row:
                if button.callback_data and button.callback_data.startswith("restore_message:"):
                    new_row.append(InlineKeyboardButton(text="✅ Восстановлено", callback_data="done"))
                else:
                    new_row.append(button)
            new_keyboard.append(new_row)
        new_markup = InlineKeyboardMarkup(inline_keyboard=new_keyboard)
        await bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=new_markup
        )
    await call.answer("Сообщение восстановлено!", show_alert=True)