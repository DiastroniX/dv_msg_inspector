from aiogram import Router, types, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from db.operations import (
    revoke_penalty,
    get_deleted_message_by_id,
    reset_all_user_data
)
from data.texts import TEXTS
import pytz
import datetime
import logging

logger = logging.getLogger("handlers")
callbacks_router = Router(name="callbacks_router")


@callbacks_router.callback_query(lambda call: call.data and call.data.startswith("revoke_penalty:"))
async def revoke_penalty_handler(call: CallbackQuery, bot: Bot, config):
    if not config.logging.enabled or not config.logging.modules.handlers:
        return await _handle_revoke_penalty(call, bot, config)
        
    logger.info(f"Обработка запроса на снятие ограничений от {call.from_user.id} ({call.from_user.username or call.from_user.full_name})")
    try:
        await _handle_revoke_penalty(call, bot, config)
    except Exception as e:
        logger.error(f"Ошибка при обработке revoke_penalty: {str(e)}")
        await call.answer("Произошла ошибка при снятии ограничений", show_alert=True)

async def _handle_revoke_penalty(call: CallbackQuery, bot: Bot, config):
    parts = call.data.split(":")
    if len(parts) < 2:
        if config.logging.enabled and config.logging.modules.handlers:
            logger.error("Некорректный формат callback_data для revoke_penalty")
        return
    user_id = int(parts[1])
    
    # 1. Снимаем все санкции в БД
    if config.logging.enabled and config.logging.modules.handlers:
        logger.debug(f"Снятие санкций для пользователя {user_id}")
    await revoke_penalty(user_id)
    
    # 2. Сбрасываем все счетчики и историю нарушений
    if config.logging.enabled and config.logging.modules.handlers:
        logger.debug(f"Сброс данных о нарушениях для пользователя {user_id}")
    await reset_all_user_data(user_id)
    
    # 3. Пытаемся разбанить в Telegram (если нужно)
    try:
        for group_id in config.allowed_groups:
            if config.logging.enabled and config.logging.modules.handlers:
                logger.debug(f"Попытка разбана пользователя {user_id} в группе {group_id}")
            await bot.unban_chat_member(group_id, user_id)
    except Exception as e:
        if config.logging.enabled and config.logging.modules.handlers:
            logger.error(f"Ошибка при разбане пользователя {user_id}: {str(e)}")

    # Обновляем клавиатуру
    if call.message and call.message.reply_markup:
        if config.logging.enabled and config.logging.modules.handlers:
            logger.debug("Обновление клавиатуры сообщения")
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
    if config.logging.enabled and config.logging.modules.handlers:
        logger.info(f"Ограничения успешно сняты для пользователя {user_id}")
    await call.answer("Все ограничения сняты, история нарушений очищена!", show_alert=True)


@callbacks_router.callback_query(lambda call: call.data and call.data.startswith("reset_violations:"))
async def reset_violations_handler(call: CallbackQuery, bot: Bot, config):
    if not config.logging.enabled or not config.logging.modules.handlers:
        return await _handle_reset_violations(call, bot, config)
        
    logger.info(f"Обработка запроса на сброс нарушений от {call.from_user.id} ({call.from_user.username or call.from_user.full_name})")
    try:
        await _handle_reset_violations(call, bot, config)
    except Exception as e:
        logger.error(f"Ошибка при обработке reset_violations: {str(e)}")
        await call.answer("Произошла ошибка при сбросе нарушений", show_alert=True)

async def _handle_reset_violations(call: CallbackQuery, bot: Bot, config):
    parts = call.data.split(":")
    if len(parts) < 2:
        if config.logging.enabled and config.logging.modules.handlers:
            logger.error("Некорректный формат callback_data для reset_violations")
        return
    user_id = int(parts[1])
    
    # Полный сброс всех данных о нарушениях
    if config.logging.enabled and config.logging.modules.handlers:
        logger.debug(f"Сброс всех данных о нарушениях для пользователя {user_id}")
    await reset_all_user_data(user_id)

    # Обновляем клавиатуру
    if call.message and call.message.reply_markup:
        if config.logging.enabled and config.logging.modules.handlers:
            logger.debug("Обновление клавиатуры сообщения")
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
    if config.logging.enabled and config.logging.modules.handlers:
        logger.info(f"Счетчики нарушений успешно сброшены для пользователя {user_id}")
    await call.answer("Все счетчики нарушений сброшены!", show_alert=True)


@callbacks_router.callback_query(lambda call: call.data and call.data.startswith("restore_message:"))
async def restore_message_handler(call: CallbackQuery, bot: Bot, config):
    if not config.logging.enabled or not config.logging.modules.handlers:
        return await _handle_restore_message(call, bot, config)
        
    logger.info(f"Обработка запроса на восстановление сообщения от {call.from_user.id} ({call.from_user.username or call.from_user.full_name})")
    try:
        await _handle_restore_message(call, bot, config)
    except Exception as e:
        logger.error(f"Ошибка при обработке restore_message: {str(e)}")
        await call.answer("Произошла ошибка при восстановлении сообщения", show_alert=True)

async def _handle_restore_message(call: CallbackQuery, bot: Bot, config):
    parts = call.data.split(":")
    if len(parts) < 2:
        if config.logging.enabled and config.logging.modules.handlers:
            logger.error("Некорректный формат callback_data для restore_message")
        return
    deleted_msg_id = int(parts[1])
    
    if config.logging.enabled and config.logging.modules.handlers:
        logger.debug(f"Поиск удаленного сообщения с ID {deleted_msg_id}")
    row = await get_deleted_message_by_id(deleted_msg_id)
    if not row:
        if config.logging.enabled and config.logging.modules.handlers:
            logger.warning(f"Сообщение с ID {deleted_msg_id} не найдено в БД")
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
    
    if config.logging.enabled and config.logging.modules.handlers:
        logger.debug(f"Восстановление сообщения в группе {grp_id}")
    await bot.send_message(grp_id, text_to_post, parse_mode="HTML")

    # Обновляем клавиатуру
    if call.message and call.message.reply_markup:
        if config.logging.enabled and config.logging.modules.handlers:
            logger.debug("Обновление клавиатуры сообщения")
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
    if config.logging.enabled and config.logging.modules.handlers:
        logger.info(f"Сообщение {deleted_msg_id} успешно восстановлено")
    await call.answer("Сообщение восстановлено!", show_alert=True)