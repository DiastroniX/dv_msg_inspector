import datetime
import pytz
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from data.texts import TEXTS
from data.admin_texts import VIOLATION_DESCRIPTIONS, get_penalty_descriptions, ADMIN_NOTIFICATION
from config import Config
from aiogram import Bot

def make_admin_inline_kb(user_id: int, deleted_msg_id: int = None) -> InlineKeyboardMarkup:
    """
    Создает inline клавиатуру для админ-уведомлений.
    Кнопки:
      - "🚫 Снять ограничения" (revoke_penalty)
      - "🔄 Сброс нарушений" (reset_violations)
      - Если задан deleted_msg_id, добавляется кнопка "💾 Восстановить сообщение" (restore_message)
    """
    # Создаем клавиатуру с пустым списком для inline_keyboard
    kb = InlineKeyboardMarkup(inline_keyboard=[])

    # Добавляем кнопки по одной в строку для увеличения их размера
    kb.inline_keyboard.append([
        InlineKeyboardButton(
            text="🚫 Снять все ограничения",
            callback_data=f"revoke_penalty:{user_id}"
        )
    ])
    
    kb.inline_keyboard.append([
        InlineKeyboardButton(
            text="🔄 Сброс счетчика нарушений",
            callback_data=f"reset_violations:{user_id}"
        )
    ])

    # Если имеется deleted_msg_id, добавляем кнопку восстановления
    if deleted_msg_id is not None:
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text="📤 Восстановить сообщение",
                callback_data=f"restore_message:{deleted_msg_id}"
            )
        ])
    return kb

async def send_admin_notification(
    bot: Bot,
    config: Config,
    user_id: int,
    user_name: str,
    violation_type: str,
    penalty_to_apply: str,
    msg_text: str,
    penalty_count: int,
    deleted_msg_id: int = None
):
    """
    Формирует и отправляет уведомление в админ-чат с HTML форматированием и inline кнопками.
    В уведомлении отображается информация о нарушении, номер инцидента и применённая санкция.
    Если задан deleted_msg_id, то добавляется кнопка для восстановления сообщения.
    """
    violation_desc = VIOLATION_DESCRIPTIONS.get(violation_type, violation_type)
    penalty_desc = get_penalty_descriptions(config).get(penalty_to_apply, penalty_to_apply)
    
    text_report = ADMIN_NOTIFICATION.format(
        user_name=user_name,
        user_id=user_id,
        penalty_count=penalty_count,
        violation_desc=violation_desc,
        violation_type=violation_type,
        penalty_desc=penalty_desc,
        penalty_to_apply=penalty_to_apply,
        msg_text=msg_text
    )

    kb = make_admin_inline_kb(user_id, deleted_msg_id)
    await bot.send_message(
        config.admin_chat_id,
        text_report,
        parse_mode="HTML",
        reply_markup=kb
    )