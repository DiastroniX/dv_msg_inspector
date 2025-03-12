import time
import asyncio
import datetime
import pytz
import logging
from typing import Dict, Tuple, Optional, Any, List
from collections import defaultdict

from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions, User
from data.texts import TEXTS
from config import Config
from db.operations import (
    record_violation,
    record_deleted_message,
    get_incidents_count
)
from admin_notifications import send_admin_notification
from data.admin_texts import VIOLATION_DESCRIPTIONS, ADMIN_VIOLATION_WARNING
from db.models import Violation
from db.operations import (
    add_violation,
    get_user_violations_count,
    get_user_active_violations
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

message_router = Router(name="message_router")

# Кэш для хранения информации о последних сообщениях пользователя
# user_id -> List[Tuple[message_id, reply_to_message_id, timestamp]]
user_messages: Dict[int, List[Tuple[int, Optional[int], float]]] = defaultdict(list)

# Время жизни записи в кэше (60 минут)
CACHE_TTL = 3600

logger = logging.getLogger(__name__)

async def cleanup_old_cache_entries():
    """Периодически очищает старые записи из кэша user_messages"""
    while True:
        try:
            current_time = time.time()
            for user_id in list(user_messages.keys()):
                # Удаляем сообщения старше CACHE_TTL
                user_messages[user_id] = [
                    msg for msg in user_messages[user_id]
                    if current_time - msg[2] <= CACHE_TTL
                ]
                # Если список пуст, удаляем запись пользователя
                if not user_messages[user_id]:
                    del user_messages[user_id]
            await asyncio.sleep(300)  # Проверяем каждые 5 минут
        except Exception as e:
            logging.error(f"Error in cache cleanup: {str(e)}", exc_info=True)
            await asyncio.sleep(60)

async def init_message_handler():
    """
    Инициализация обработчика сообщений и запуск фоновых задач
    """
    # Запускаем очистку кэша в фоновом режиме
    asyncio.create_task(cleanup_old_cache_entries())

def is_admin(user_id: int, config: Config) -> bool:
    return user_id in config.admin_ids

async def schedule_delete(bot: Bot, chat_id: int, message_id: int, delay_seconds: int) -> None:
    """Планирует удаление сообщения через указанное время"""
    try:
        logger.debug(f"Запланировано удаление сообщения {message_id} в чате {chat_id} через {delay_seconds} секунд")
        await asyncio.sleep(delay_seconds)
        logger.debug(f"Попытка удаления сообщения {message_id} в чате {chat_id}")
        await bot.delete_message(chat_id, message_id)
        logger.info(f"Сообщение {message_id} успешно удалено из чата {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения {message_id} из чата {chat_id}: {str(e)}")

async def safe_delete_bot_message(bot: Bot, message: Message, config: Config, is_penalty_message: bool = False) -> None:
    """Безопасно удаляет сообщение бота с учетом настроек"""
    if config.logging.message_deletion:
        logger.debug(f"Проверка условий удаления сообщения {message.message_id}")
        logger.debug(f"is_penalty_message={is_penalty_message}, delete_penalty_messages={config.delete_penalty_messages}, delete_bot_messages={config.delete_bot_messages}")

    if is_penalty_message and config.delete_penalty_messages:
        if config.logging.message_deletion:
            logger.info(f"Планирование удаления штрафного сообщения {message.message_id} через {config.penalty_message_lifetime_seconds} секунд")
        asyncio.create_task(schedule_delete(
            bot, message.chat.id, message.message_id,
            config.penalty_message_lifetime_seconds
        ))
    elif not is_penalty_message and config.delete_bot_messages:
        if config.logging.message_deletion:
            logger.info(f"Планирование удаления сообщения бота {message.message_id} через {config.bot_message_lifetime_seconds} секунд")
        asyncio.create_task(schedule_delete(
            bot, message.chat.id, message.message_id,
            config.bot_message_lifetime_seconds
        ))

async def _delete_message_safe(message: Message):
    try:
        await message.delete()
    except Exception:
        pass

@message_router.message(F.chat.type.in_({"group", "supergroup"}))
async def process_group_message(message: Message, bot: Bot, event_from_user: User = None, **data):
    config = data["config"]
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

    # Игнорируем служебные сообщения (вход/выход из группы и т.д.)
    if message.new_chat_members is not None or message.left_chat_member is not None:
        return
    if message.new_chat_title or message.new_chat_photo or message.delete_chat_photo or message.group_chat_created:
        return
    if message.message_auto_delete_timer_changed or message.pinned_message:
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
        return

    # Получаем ID сообщения, на которое отвечают (если есть)
    reply_to_msg_id = message.reply_to_message.message_id if message.reply_to_message else None
    
    # Добавляем текущее сообщение в историю
    user_messages[user_id].append((message.message_id, reply_to_msg_id, now_ts))
    
    # Сортируем сообщения по времени
    user_messages[user_id].sort(key=lambda x: x[2])
    
    violation_type = None
    delete_msg = False

    # Получаем предыдущее сообщение пользователя
    prev_messages = [msg for msg in user_messages[user_id][:-1] if now_ts - msg[2] <= CACHE_TTL]
    
    if prev_messages:
        prev_msg = prev_messages[-1]
        prev_msg_id, prev_reply_id, prev_ts = prev_msg

        # Проверяем временной интервал только если включена соответствующая опция
        time_violation = False
        if config.check_reply_cooldown and config.reply_cooldown_seconds:
            time_violation = (now_ts - prev_ts) < config.reply_cooldown_seconds

        if reply_to_msg_id:
            if message.reply_to_message.from_user:
                # Self-reply: реплай на своё сообщение
                if message.reply_to_message.from_user.id == user_id:
                    if time_violation:
                        violation_type = "self_reply"
                        delete_msg = not is_admin_user
                # Double-reply: повторный ответ на то же сообщение
                elif prev_reply_id == reply_to_msg_id and time_violation:
                    violation_type = "double_reply"
                    delete_msg = not is_admin_user
        else:
            # No-reply: сообщение без реплая после предыдущего без реплая
            if not prev_reply_id and time_violation:
                violation_type = "no_reply"
                delete_msg = not is_admin_user

    if violation_type:
        try:
            if is_admin_user:
                if config.warn_admins:
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
                    if sent_msg and config.delete_bot_messages:
                        await safe_delete_bot_message(bot, sent_msg, config, is_penalty_message=False)
                
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
        if sent_msg and config.delete_penalty_messages:  # Используем delete_penalty_messages для предупреждений
            await safe_delete_bot_message(bot, sent_msg, config, is_penalty_message=True)
    elif penalty_to_apply == "read-only":
        until_date = int(time.time()) + config.mute_duration_seconds
        if config.logging.enabled and config.logging.modules.handlers:
            logger.info(f"Попытка установить мут пользователю {user_id} в группе {group_id} до {datetime.datetime.fromtimestamp(until_date)}")
        
        try:
            # Проверяем права бота
            bot_member = await bot.get_chat_member(group_id, (await bot.me()).id)
            if not bot_member.can_restrict_members:
                if config.logging.enabled and config.logging.modules.handlers:
                    logger.error(f"Бот не имеет прав для ограничения пользователей в группе {group_id}")
                return
            
            await bot.restrict_chat_member(
                group_id,
                user_id,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_polls=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False,
                    can_invite_users=True,
                    can_change_info=False,
                    can_pin_messages=False
                ),
                until_date=until_date
            )
            if config.logging.enabled and config.logging.modules.handlers:
                logger.info(f"Мут успешно установлен пользователю {user_id}")
        except Exception as e:
            if config.logging.enabled and config.logging.modules.handlers:
                logger.error(f"Ошибка при установке мута для пользователя {user_id}: {str(e)}")
            pass
        if config.notifications.get("mute_applied"):
            msk = pytz.timezone("Europe/Moscow")
            msk_time = datetime.datetime.fromtimestamp(until_date, msk).strftime("%d.%m.%Y %H:%M")
            minutes = max(1, (config.mute_duration_seconds + 59) // 60)  # округление вверх
            
            # Получаем описание нарушения
            violation_desc = VIOLATION_DESCRIPTIONS.get(violation_type, violation_type)
            
            # Добавляем задержку перед отправкой сообщения
            await asyncio.sleep(config.bot_message_delay_seconds)
            
            txt = TEXTS["mute_applied"].format(
                name=user_name,
                violations_count=count_incidents,
                minutes=minutes,
                datetime=msk_time
            )
            sent_msg = await bot.send_message(group_id, txt, parse_mode="HTML")
            if sent_msg and config.delete_penalty_messages:  # Используем delete_penalty_messages для мута
                await safe_delete_bot_message(bot, sent_msg, config, is_penalty_message=True)
    elif penalty_to_apply == "kick":
        try:
            await bot.ban_chat_member(group_id, user_id, until_date=int(time.time()) + 60)
            await bot.unban_chat_member(group_id, user_id)
        except Exception:
            pass
        if config.notifications.get("kick_applied"):
            txt = TEXTS["kick_applied"].format(name=user_name)
            sent_msg = await bot.send_message(group_id, txt, parse_mode="HTML")
            if sent_msg and config.delete_penalty_messages:  # Используем delete_penalty_messages для кика
                await safe_delete_bot_message(bot, sent_msg, config, is_penalty_message=True)
    elif penalty_to_apply == "kick+ban":
        ban_until = int(time.time()) + config.temp_ban_duration_seconds
        try:
            await bot.ban_chat_member(group_id, user_id, until_date=ban_until)
        except Exception:
            pass
        msk = pytz.timezone("Europe/Moscow")
        date_str = datetime.datetime.fromtimestamp(ban_until, msk).strftime("%d.%m.%Y %H:%M")
        minutes = max(1, (config.temp_ban_duration_seconds + 59) // 60)  # округление вверх
        txt = TEXTS["kick_ban_applied"].format(name=user_name, date_str=date_str, minutes=minutes)
        sent_msg = await bot.send_message(group_id, txt, parse_mode="HTML")
        if sent_msg and config.delete_penalty_messages:  # Используем delete_penalty_messages для временного бана
            await safe_delete_bot_message(bot, sent_msg, config, is_penalty_message=True)
    elif penalty_to_apply == "ban":
        try:
            await bot.ban_chat_member(group_id, user_id)
        except Exception:
            pass
        if config.notifications.get("ban_applied"):
            txt = TEXTS["ban_applied"].format(name=user_name)
            sent_msg = await bot.send_message(group_id, txt, parse_mode="HTML")
            if sent_msg and config.delete_penalty_messages:  # Используем delete_penalty_messages для бана
                await safe_delete_bot_message(bot, sent_msg, config, is_penalty_message=True)

async def process_violation(
    bot: Bot,
    message: Message,
    violation_type: str,
    config: Config,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """Обрабатывает нарушение правил"""
    if config.logging.violations:
        logger.info(f"Обработка нарушения типа {violation_type} от пользователя {message.from_user.id}")

    # Проверяем, включено ли правило
    rule = config.violation_rules.get(violation_type)
    if not rule or not rule.enabled:
        if config.logging.violations:
            logger.debug(f"Правило {violation_type} отключено или не существует")
        return

    # Если нарушение не считается за violation, просто удаляем сообщение
    if not rule.count_as_violation:
        if config.logging.violations:
            logger.debug(f"Правило {violation_type} не считается за нарушение, удаляем сообщение")
        try:
            await message.delete()
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения: {str(e)}")
        return

    # Добавляем нарушение в базу
    violation = await add_violation(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        violation_type=violation_type,
        message_text=message.text or "",
        context=context
    )

    if config.logging.violations:
        logger.info(f"Добавлено нарушение {violation.id} для пользователя {message.from_user.id}")

    # Получаем количество активных нарушений
    violations_count = await get_user_violations_count(message.from_user.id, message.chat.id)
    active_violations = await get_user_active_violations(message.from_user.id, message.chat.id)

    if config.logging.violations:
        logger.debug(f"Активных нарушений у пользователя {message.from_user.id}: {violations_count}")

    # Определяем наказание на основе количества нарушений
    penalty = None
    for threshold, penalty_type in sorted(config.penalties.items(), key=lambda x: int(x[0])):
        if violations_count >= int(threshold):
            penalty = penalty_type

    if config.logging.penalties and penalty:
        logger.info(f"Применяется наказание {penalty} к пользователю {message.from_user.id}")

    # Применяем наказание
    if penalty:
        await apply_penalty(bot, message, penalty, config, violation)

async def apply_penalty(
    bot: Bot,
    message: Message,
    penalty: str,
    config: Config,
    violation: Violation
) -> None:
    """Применяет наказание к пользователю"""
    if config.logging.penalties:
        logger.info(f"Применение наказания {penalty} к пользователю {message.from_user.id}")

    try:
        # Удаляем сообщение-нарушение
        await message.delete()
        if config.logging.penalties:
            logger.debug(f"Удалено сообщение-нарушение {message.message_id}")
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения-нарушения: {str(e)}")

    # Получаем описание нарушения
    violation_description = VIOLATION_DESCRIPTIONS.get(violation.violation_type, "неизвестное нарушение")

    try:
        if penalty == "warning":
            if config.notifications["warning"]:
                txt = f"⚠️ {message.from_user.full_name}, вы получили предупреждение за {violation_description}.\n"
                txt += f"Текст сообщения: {violation.message_text}"
                sent_msg = await message.answer(txt)
                await safe_delete_bot_message(bot, sent_msg, config, is_penalty_message=True)

        elif penalty == "read-only":
            # Вычисляем время окончания мута
            mute_minutes = config.mute_duration_seconds // 60
            mute_until = datetime.now() + datetime.timedelta(seconds=config.mute_duration_seconds)
            msk_time = (mute_until + datetime.timedelta(hours=3)).strftime("%H:%M")

            if config.notifications["mute"]:
                txt = f"🤐 {message.from_user.full_name}, вы получили мут на {mute_minutes} минут за {violation_description}.\n"
                txt += f"Мут истекает в {msk_time} по МСК.\n"
                txt += f"Текст сообщения: {violation.message_text}"
                sent_msg = await message.answer(txt)
                await safe_delete_bot_message(bot, sent_msg, config, is_penalty_message=True)

            try:
                await bot.restrict_chat_member(
                    chat_id=message.chat.id,
                    user_id=message.from_user.id,
                    until_date=mute_until,
                    permissions={"can_send_messages": False}
                )
                if config.logging.penalties:
                    logger.info(f"Пользователь {message.from_user.id} получил мут до {mute_until}")
            except Exception as e:
                logger.error(f"Ошибка при установке мута: {str(e)}")

        elif penalty == "kick":
            if config.notifications["kick"]:
                txt = f"👞 {message.from_user.full_name} исключен из чата за {violation_description}.\n"
                txt += f"Текст сообщения: {violation.message_text}"
                sent_msg = await message.answer(txt)
                await safe_delete_bot_message(bot, sent_msg, config, is_penalty_message=True)

            try:
                await bot.ban_chat_member(
                    chat_id=message.chat.id,
                    user_id=message.from_user.id,
                    until_date=datetime.now() + datetime.timedelta(seconds=1)
                )
                if config.logging.penalties:
                    logger.info(f"Пользователь {message.from_user.id} исключен из чата")
            except Exception as e:
                logger.error(f"Ошибка при исключении пользователя: {str(e)}")

        elif penalty == "kick+ban":
            ban_until = datetime.now() + datetime.timedelta(seconds=config.temp_ban_duration_seconds)
            if config.notifications["temp_ban"]:
                txt = f"🚫 {message.from_user.full_name} получил временный бан за {violation_description}.\n"
                txt += f"Текст сообщения: {violation.message_text}"
                sent_msg = await message.answer(txt)
                await safe_delete_bot_message(bot, sent_msg, config, is_penalty_message=True)

            try:
                await bot.ban_chat_member(
                    chat_id=message.chat.id,
                    user_id=message.from_user.id,
                    until_date=ban_until
                )
                if config.logging.penalties:
                    logger.info(f"Пользователь {message.from_user.id} получил временный бан до {ban_until}")
            except Exception as e:
                logger.error(f"Ошибка при установке временного бана: {str(e)}")

        elif penalty == "ban":
            if config.notifications["ban"]:
                txt = f"⛔️ {message.from_user.full_name} получил перманентный бан за {violation_description}.\n"
                txt += f"Текст сообщения: {violation.message_text}"
                sent_msg = await message.answer(txt)
                await safe_delete_bot_message(bot, sent_msg, config, is_penalty_message=True)

            try:
                await bot.ban_chat_member(
                    chat_id=message.chat.id,
                    user_id=message.from_user.id
                )
                if config.logging.penalties:
                    logger.info(f"Пользователь {message.from_user.id} получил перманентный бан")
            except Exception as e:
                logger.error(f"Ошибка при установке бана: {str(e)}")

    except Exception as e:
        logger.error(f"Ошибка при применении наказания {penalty}: {str(e)}")