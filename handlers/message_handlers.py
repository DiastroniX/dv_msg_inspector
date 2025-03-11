import time
import asyncio
import datetime
import pytz
import logging
from typing import Dict, Tuple
from collections import defaultdict

from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions
from data.texts import TEXTS
from config import Config
from database import (
    record_violation,
    record_deleted_message,
    get_incidents_count
)
from admin_notifications import send_admin_notification
from data.admin_texts import VIOLATION_DESCRIPTIONS, ADMIN_VIOLATION_WARNING

message_router = Router(name="message_router")

# Кэш для хранения информации о последнем реплае: user_id -> (last_reply_msg_id, timestamp)
# Если значение -1, значит последнее сообщение было без реплая.
last_reply_info: Dict[int, Tuple[int, float]] = {}

# Время жизни записи в кэше (30 минут)
CACHE_TTL = 1800

async def cleanup_old_cache_entries():
    """
    Периодически очищает старые записи из кэша last_reply_info
    """
    while True:
        try:
            current_time = time.time()
            to_remove = []
            
            for user_id, (msg_id, timestamp) in last_reply_info.items():
                if current_time - timestamp > CACHE_TTL:
                    to_remove.append(user_id)
            
            for user_id in to_remove:
                del last_reply_info[user_id]
                
            await asyncio.sleep(300)  # Проверяем каждые 5 минут
        except Exception as e:
            logging.error(f"Error in cache cleanup: {str(e)}", exc_info=True)
            await asyncio.sleep(60)  # В случае ошибки, подождем минуту

async def init_message_handler():
    """
    Инициализация обработчика сообщений и запуск фоновых задач
    """
    # Запускаем очистку кэша в фоновом режиме
    asyncio.create_task(cleanup_old_cache_entries())

def is_admin(user_id: int, config: Config) -> bool:
    return user_id in config.admin_ids

async def schedule_delete(bot: Bot, chat_id: int, message_id: int, delay_secs: int):
    """
    Удаляет сообщение бота через delay_secs секунд, если оно ещё существует.
    """
    await asyncio.sleep(delay_secs)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass

async def safe_delete_bot_message(bot: Bot, message: Message, config: Config):
    """
    Безопасно удаляет сообщение бота, если это разрешено в конфигурации.
    """
    if config.delete_bot_messages and config.bot_message_lifetime_seconds > 0:
        await schedule_delete(bot, message.chat.id, message.message_id, config.bot_message_lifetime_seconds)

async def _delete_message_safe(message: Message):
    try:
        await message.delete()
    except Exception:
        pass

@message_router.message(F.chat.type.in_({"group", "supergroup"}))
async def process_group_message(message: Message, bot: Bot, config: Config):
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return

    # Проверяем, что группа входит в список разрешённых
    if chat_id not in config.allowed_groups:
        return

    # Игнорируем сообщения от ботов или отправленные от имени канала
    if user.is_bot or message.sender_chat:
        return

    user_id = user.id
    user_name = f"@{user.username}" if user.username else user.full_name

    # Проверяем, является ли пользователь администратором
    is_admin_user = is_admin(user_id, config)
    # Добавляем пометку администратора к имени
    if is_admin_user:
        user_name = f"👮‍♂️ {user_name} (Администратор)"

    text = message.text or message.caption or ""
    text_len = len(text)
    now_ts = time.time()

    # Если сообщение длинное — пропускаем проверки
    if text_len >= config.message_length_limit:
        if message.reply_to_message:
            if not (message.reply_to_message.from_user and
                    message.reply_to_message.from_user.is_bot and
                    config.ignore_bot_thread_replies):
                last_reply_info[user_id] = (message.reply_to_message.message_id, now_ts)
        else:
            last_reply_info[user_id] = (-1, now_ts)
        return  # Длинное сообщение не считается нарушением

    violation_type = None
    delete_msg = False

    if message.reply_to_message:
        if (message.reply_to_message.from_user and
                message.reply_to_message.from_user.is_bot and
                config.ignore_bot_thread_replies):
            pass
        else:
            replied_msg_id = message.reply_to_message.message_id
            # Если self-reply: реплай на своё же сообщение
            if message.reply_to_message.from_user and message.reply_to_message.from_user.id == user_id:
                if (now_ts - message.reply_to_message.date.timestamp()) < config.reply_cooldown_seconds:
                    violation_type = "self_reply"
                    delete_msg = not is_admin_user  # Не удаляем сообщения администраторов
            else:
                # Реплай на чужое сообщение
                if user_id in last_reply_info:
                    prev_msg_id, prev_ts = last_reply_info[user_id]
                    if prev_msg_id == replied_msg_id and (now_ts - prev_ts) < config.reply_cooldown_seconds:
                        violation_type = "double_reply"
                        delete_msg = not is_admin_user  # Не удаляем сообщения администраторов
                    else:
                        last_reply_info[user_id] = (replied_msg_id, now_ts)
                else:
                    last_reply_info[user_id] = (replied_msg_id, now_ts)
    else:
        # Сообщение без реплая
        if user_id in last_reply_info:
            prev_msg_id, prev_ts = last_reply_info[user_id]
            if prev_msg_id == -1 and (now_ts - prev_ts) < config.reply_cooldown_seconds:
                violation_type = "no_reply"
                delete_msg = not is_admin_user  # Не удаляем сообщения администраторов
            else:
                last_reply_info[user_id] = (-1, now_ts)
        else:
            last_reply_info[user_id] = (-1, now_ts)

    if violation_type:
        try:
            if is_admin_user:
                # Отправляем предупреждение в админ-чат
                violation_desc = VIOLATION_DESCRIPTIONS.get(violation_type, violation_type)
                warning_text = ADMIN_VIOLATION_WARNING.format(
                    user_name=user_name,
                    violation_desc=violation_desc,
                    msg_text=text
                )
                await bot.send_message(config.admin_chat_id, warning_text, parse_mode="HTML")
            else:
                if delete_msg:
                    # Сначала пытаемся удалить сообщение
                    await _delete_message_safe(message)
                
                # Записываем удалённое сообщение и нарушение
                deleted_msg_id = await record_deleted_message(user_id, user_name, chat_id, text)
                await record_violation(user_id, user_name, chat_id, violation_type, config)

                # Отправляем уведомление о нарушении
                notification_text = None
                if violation_type == "no_reply":
                    notification_text = TEXTS["no_reply"].format(name=user_name)
                elif violation_type == "double_reply":
                    notification_text = TEXTS["double_reply"].format(name=user_name)
                elif violation_type == "self_reply":
                    minutes = max(1, (config.reply_cooldown_seconds + 59) // 60)  # округление вверх
                    notification_text = TEXTS["self_reply"].format(name=user_name, minutes=minutes)

                if notification_text:
                    sent_msg = await bot.send_message(chat_id, notification_text, parse_mode="HTML")
                    if sent_msg:
                        await safe_delete_bot_message(bot, sent_msg, config)
                
                # Проверяем необходимость применения санкций
                await apply_penalties_if_needed(user_id, user_name, chat_id, config, violation_type, text, bot, deleted_msg_id)

        except Exception as e:
            logging.error(f"Error processing violation for user {user_name}: {str(e)}", exc_info=True)

async def apply_penalties_if_needed(
    user_id: int,
    user_name: str,
    group_id: int,
    config: Config,
    violation_type: str,
    msg_text: str,
    bot: Bot,
    deleted_msg_id: int = None
):
    count_incidents = await get_incidents_count(user_id)
    penalty_count = count_incidents  # для отображения номера наказания

    best_key = 0
    penalty_to_apply = None
    for k_str, p_type in config.penalties.items():
        k = int(k_str)
        if count_incidents >= k and k > best_key:
            best_key = k
            penalty_to_apply = p_type

    if not penalty_to_apply:
        return

    # Отправка уведомления в админ-чат
    await send_admin_notification(
        bot,
        config,
        user_id,
        user_name,
        violation_type,
        penalty_to_apply,
        msg_text,
        penalty_count,
        deleted_msg_id=deleted_msg_id
    )

    if penalty_to_apply == "warning":
        # Находим следующее наказание
        next_penalty_threshold = float('inf')
        next_penalty_type = None
        current_violations = count_incidents
        
        for k_str, p_type in config.penalties.items():
            k = int(k_str)
            if k > current_violations and k < next_penalty_threshold:
                next_penalty_threshold = k
                next_penalty_type = p_type
        
        # Преобразуем тип наказания в понятное описание
        penalty_descriptions = {
            "warning": "предупреждение",
            "read-only": f"временный мут на {max(1, config.mute_duration_seconds // 60)} минут",
            "kick": "исключение из группы",
            "kick+ban": f"бан на {config.temp_ban_duration_seconds // 60} минут",
            "ban": "перманентный бан"
        }
        
        next_penalty_description = penalty_descriptions.get(next_penalty_type, "неизвестно")
        violations_until_next = next_penalty_threshold - current_violations if next_penalty_type else 0
        
        warn_text = TEXTS["official_warning"].format(
            name=user_name,
            current_violations=current_violations,
            next_penalty_description=next_penalty_description,
            violations_until_next=violations_until_next
        )
        sent_msg = await bot.send_message(group_id, warn_text, parse_mode="HTML")
        if sent_msg:
            await safe_delete_bot_message(bot, sent_msg, config)
    elif penalty_to_apply == "read-only":
        until_date = int(time.time()) + config.mute_duration_seconds
        try:
            await bot.restrict_chat_member(
                group_id,
                user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
        except Exception:
            pass
        if config.notifications.get("mute_applied"):
            msk = pytz.timezone("Europe/Moscow")
            msk_time = datetime.datetime.fromtimestamp(until_date, msk).strftime("%Y-%m-%d %H:%M:%S MSK")
            minutes = max(1, (config.mute_duration_seconds + 59) // 60)  # округление вверх
            txt = (
                f"{TEXTS['mute_applied'].format(name=user_name, minutes=minutes)}\n"
                f"{TEXTS['mute_until_time'].format(until_time=msk_time)}"
            )
            sent_msg = await bot.send_message(group_id, txt, parse_mode="HTML")
            if sent_msg:
                await safe_delete_bot_message(bot, sent_msg, config)
    elif penalty_to_apply == "kick":
        try:
            await bot.ban_chat_member(group_id, user_id, until_date=int(time.time()) + 60)
            await bot.unban_chat_member(group_id, user_id)
        except Exception:
            pass
        if config.notifications.get("kick_applied"):
            txt = TEXTS["kick_applied"].format(name=user_name)
            sent_msg = await bot.send_message(group_id, txt, parse_mode="HTML")
            if sent_msg:
                await safe_delete_bot_message(bot, sent_msg, config)
    elif penalty_to_apply == "kick+ban":
        ban_until = int(time.time()) + config.temp_ban_duration_seconds
        try:
            await bot.ban_chat_member(group_id, user_id, until_date=ban_until)
        except Exception:
            pass
        msk = pytz.timezone("Europe/Moscow")
        date_str = datetime.datetime.fromtimestamp(ban_until, msk).strftime("%Y-%m-%d %H:%M:%S MSK")
        minutes = max(1, (config.temp_ban_duration_seconds + 59) // 60)  # округление вверх
        txt = TEXTS["kick_ban_applied"].format(name=user_name, date_str=date_str, minutes=minutes)
        sent_msg = await bot.send_message(group_id, txt, parse_mode="HTML")
        if sent_msg:
            await safe_delete_bot_message(bot, sent_msg, config)
    elif penalty_to_apply == "ban":
        try:
            await bot.ban_chat_member(group_id, user_id)
        except Exception:
            pass
        if config.notifications.get("ban_applied"):
            txt = TEXTS["ban_applied"].format(name=user_name)
            sent_msg = await bot.send_message(group_id, txt, parse_mode="HTML")
            if sent_msg:
                await safe_delete_bot_message(bot, sent_msg, config)