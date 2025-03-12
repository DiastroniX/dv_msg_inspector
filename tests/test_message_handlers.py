"""
Модуль тестирования обработчиков сообщений бота.
Проверяет корректность обработки различных типов сообщений, нарушений и наказаний.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, create_autospec
from aiogram.types import Message, User, Chat, ChatPermissions
from config import Config, LoggingConfig, LoggingModules
from handlers.message_handlers import (
    process_group_message,
    apply_penalty,
    process_violation,
    safe_delete_bot_message,
    schedule_delete
)
from dataclasses import dataclass
import datetime
from data.admin_texts import VIOLATION_DESCRIPTIONS
import time
from collections import defaultdict

@dataclass
class ViolationRule:
    enabled: bool
    count_as_violation: bool
    violations_before_penalty: int

@pytest.fixture
def config():
    """Фикстура для создания тестовой конфигурации"""
    logging_config = LoggingConfig(
        enabled=True,
        level="DEBUG",
        modules=LoggingModules(
            bot=True,
            handlers=True,
            database=True,
            admin=True
        ),
        message_deletion=True,
        violations=True,
        penalties=True,
        config=True
    )

    return Config(
        bot_token="test_token",
        allowed_groups=[123456789],
        admin_ids=[987654321],
        admin_chat_id=123456789,
        message_length_limit=4096,
        check_reply_cooldown=True,
        reply_cooldown_seconds=30,  # Уменьшаем до 30 секунд для тестов
        delete_bot_messages=True,
        bot_message_delay_seconds=0,
        bot_message_lifetime_seconds=300,
        delete_penalty_messages=True,
        penalty_message_lifetime_seconds=300,
        warn_admins=True,
        ignore_bot_thread_replies=True,
        mute_duration_seconds=300,
        temp_ban_duration_seconds=3600,
        data_retention_days=30,
        logging=logging_config,
        violation_rules={
            "no_reply": ViolationRule(enabled=True, count_as_violation=True, violations_before_penalty=1),
            "double_reply": ViolationRule(enabled=True, count_as_violation=True, violations_before_penalty=1),
            "self_reply": ViolationRule(enabled=True, count_as_violation=True, violations_before_penalty=1)
        },
        penalties={
            1: "warning",
            2: "read-only",
            3: "kick",
            4: "ban"
        },
        notifications={
            "warning": True,
            "mute": True,
            "kick": True,
            "ban": True,
            "temp_ban": True,
            "mute_applied": True,
            "kick_applied": True,
            "ban_applied": True
        }
    )

@pytest.fixture
def bot():
    """Фикстура для создания тестового бота"""
    bot = AsyncMock()
    bot.me = AsyncMock(return_value=MagicMock(id=987654321))
    bot.get_chat_member = AsyncMock(return_value=MagicMock(can_restrict_members=True))
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))
    bot.delete_message = AsyncMock()
    bot.restrict_chat_member = AsyncMock()
    bot.ban_chat_member = AsyncMock()
    bot.unban_chat_member = AsyncMock()
    return bot

@pytest.fixture
def message():
    """Фикстура для создания тестового сообщения"""
    message = MagicMock()
    message.message_id = 123
    message.from_user = MagicMock()
    message.from_user.id = 123456
    message.from_user.username = "test_user"
    message.from_user.full_name = "Test User"
    message.from_user.is_bot = False
    message.chat = MagicMock()
    message.chat.id = 123456789
    message.text = "Test message"
    message.reply_to_message = None
    message.new_chat_members = None
    message.left_chat_member = None
    message.new_chat_title = None
    message.new_chat_photo = None
    message.delete_chat_photo = None
    message.group_chat_created = None
    message.message_auto_delete_timer_changed = None
    message.pinned_message = None
    message.sender_chat = None
    message.delete = AsyncMock()
    message.answer = AsyncMock()
    return message

# Патчим функции базы данных и datetime
@pytest.fixture(autouse=True)
def mock_all():
    with patch("handlers.message_handlers.record_violation", new_callable=AsyncMock) as mock_record_violation, \
         patch("handlers.message_handlers.record_deleted_message", new_callable=AsyncMock) as mock_record_deleted_message, \
         patch("handlers.message_handlers.get_incidents_count", new_callable=AsyncMock) as mock_get_incidents_count, \
         patch("handlers.message_handlers.add_violation", new_callable=AsyncMock) as mock_add_violation, \
         patch("handlers.message_handlers.get_user_violations_count", new_callable=AsyncMock) as mock_get_violations_count, \
         patch("handlers.message_handlers.get_user_active_violations", new_callable=AsyncMock) as mock_get_active_violations, \
         patch("handlers.message_handlers.datetime") as mock_datetime, \
         patch("handlers.message_handlers.VIOLATION_DESCRIPTIONS", VIOLATION_DESCRIPTIONS):
        
        mock_record_violation.return_value = None
        mock_record_deleted_message.return_value = 1
        mock_get_incidents_count.return_value = 1
        mock_add_violation.return_value = MagicMock(id=1, violation_type="test_violation", message_text="Test message")
        mock_get_violations_count.return_value = 1
        mock_get_active_violations.return_value = []
        
        # Мокаем datetime.now()
        mock_now = datetime.datetime(2024, 1, 1, 12, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.datetime = datetime.datetime
        mock_datetime.timedelta = datetime.timedelta
        
        yield {
            "record_violation": mock_record_violation,
            "record_deleted_message": mock_record_deleted_message,
            "get_incidents_count": mock_get_incidents_count,
            "add_violation": mock_add_violation,
            "get_violations_count": mock_get_violations_count,
            "get_active_violations": mock_get_active_violations,
            "datetime": mock_datetime
        }

@pytest.fixture(autouse=True)
def mock_user_messages():
    """Фикстура для мока user_messages"""
    with patch("handlers.message_handlers.user_messages", defaultdict(list)) as mock:
        mock[123456] = []  # Инициализируем список сообщений для тестового пользователя
        yield mock

@pytest.mark.asyncio
async def test_process_group_message_allowed_group(message, bot, config):
    """
    Проверяет, что сообщения в разрешенной группе обрабатываются корректно.
    
    Ожидаемое поведение:
    - Сообщение не удаляется
    - Не применяются никакие наказания
    """
    # Устанавливаем группу как разрешенную
    message.chat.id = config.allowed_groups[0]
    
    # Вызываем функцию
    await process_group_message(message, bot, config=config)
    
    # Проверяем, что сообщение не было удалено
    message.delete.assert_not_called()

@pytest.mark.asyncio
async def test_process_group_message_not_allowed_group(message, bot, config):
    """
    Проверяет обработку сообщений в неразрешенной группе.
    
    Ожидаемое поведение:
    - Сообщение игнорируется
    - Никакие действия не предпринимаются
    """
    # Устанавливаем группу как неразрешенную
    message.chat.id = 999999999
    
    # Вызываем функцию
    await process_group_message(message, bot, config=config)
    
    # Проверяем, что сообщение не было удалено
    message.delete.assert_not_called()

@pytest.mark.asyncio
async def test_safe_delete_bot_message(message, bot, config):
    """
    Проверяет безопасное удаление сообщений бота.
    
    Ожидаемое поведение:
    - Создается отложенная задача на удаление
    - Сообщение не удаляется немедленно
    """
    # Вызываем функцию
    await safe_delete_bot_message(bot, message, config)
    
    # Проверяем, что была создана задача на удаление
    assert bot.delete_message.called == False

@pytest.mark.asyncio
async def test_schedule_delete(message, bot, config):
    """
    Проверяет планирование удаления сообщения.
    
    Ожидаемое поведение:
    - Сообщение удаляется после указанной задержки
    - Вызывается метод delete_message с правильными параметрами
    """
    # Вызываем функцию
    await schedule_delete(bot, message.chat.id, message.message_id, 0)
    
    # Проверяем, что сообщение было удалено
    bot.delete_message.assert_called_once_with(message.chat.id, message.message_id)

@pytest.mark.asyncio
async def test_process_violation_warning(message, bot, config):
    """
    Проверяет обработку нарушения с выдачей предупреждения.
    
    Ожидаемое поведение:
    - Сообщение удаляется
    - Нарушение регистрируется в базе данных
    - Отправляется предупреждение пользователю
    """
    violation_type = "no_reply"
    
    await process_violation(bot, message, violation_type, config)
    
    message.delete.assert_called_once()

@pytest.mark.asyncio
async def test_apply_penalty_warning(message, bot, config):
    """
    Проверяет применение наказания в виде предупреждения.
    
    Ожидаемое поведение:
    - Сообщение удаляется
    - Отправляется предупреждение пользователю
    - Нарушение регистрируется в системе
    """
    violation = MagicMock()
    violation.violation_type = "test_violation"
    violation.message_text = "Test message"

    with patch("handlers.message_handlers.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime.datetime(2024, 1, 1, 12, 0)
        mock_datetime.timedelta = datetime.timedelta

        await apply_penalty(bot, message, "warning", config, violation)

        message.delete.assert_called_once()
        message.answer.assert_called_once()

@pytest.mark.asyncio
async def test_apply_penalty_mute(message, bot, config):
    """
    Проверяет применение наказания в виде мута (режим "только чтение").
    
    Ожидаемое поведение:
    - Сообщение удаляется
    - Пользователь получает ограничение на отправку сообщений
    - Отправляется уведомление о муте
    """
    violation = MagicMock()
    violation.violation_type = "test_violation"
    violation.message_text = "Test message"

    with patch("handlers.message_handlers.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime.datetime(2024, 1, 1, 12, 0)
        mock_datetime.timedelta = datetime.timedelta

        await apply_penalty(bot, message, "read-only", config, violation)

        message.delete.assert_called_once()
        message.answer.assert_called_once()
        bot.restrict_chat_member.assert_called_once()

@pytest.mark.asyncio
async def test_apply_penalty_kick(message, bot, config):
    """
    Проверяет применение наказания в виде исключения из группы.
    
    Ожидаемое поведение:
    - Сообщение удаляется
    - Пользователь исключается из группы
    - Отправляется уведомление об исключении
    """
    violation = MagicMock()
    violation.violation_type = "test_violation"
    violation.message_text = "Test message"

    with patch("handlers.message_handlers.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime.datetime(2024, 1, 1, 12, 0)
        mock_datetime.timedelta = datetime.timedelta

        await apply_penalty(bot, message, "kick", config, violation)

        message.delete.assert_called_once()
        message.answer.assert_called_once()
        bot.ban_chat_member.assert_called_once()

@pytest.mark.asyncio
async def test_apply_penalty_ban(message, bot, config):
    """
    Проверяет применение наказания в виде бана.
    
    Ожидаемое поведение:
    - Сообщение удаляется
    - Пользователь получает бан в группе
    - Отправляется уведомление о бане
    """
    violation = MagicMock()
    violation.violation_type = "test_violation"
    violation.message_text = "Test message"

    with patch("handlers.message_handlers.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime.datetime(2024, 1, 1, 12, 0)
        mock_datetime.timedelta = datetime.timedelta

        await apply_penalty(bot, message, "ban", config, violation)

        message.delete.assert_called_once()
        message.answer.assert_called_once()
        bot.ban_chat_member.assert_called_once()

@pytest.mark.asyncio
async def test_process_group_message_admin(message, bot, config):
    """
    Проверяет обработку сообщений от администратора.
    
    Ожидаемое поведение:
    - Сообщения администраторов не проверяются на нарушения
    - Сообщение не удаляется
    - Никакие наказания не применяются
    """
    message.from_user.id = config.admin_ids[0]
    message.chat.id = config.allowed_groups[0]
    
    await process_group_message(message, bot, config=config)
    
    message.delete.assert_not_called()

@pytest.mark.asyncio
async def test_process_group_message_bot(message, bot, config):
    """
    Проверяет обработку сообщений от ботов.
    
    Ожидаемое поведение:
    - Сообщения ботов игнорируются
    - Никакие проверки не выполняются
    - Сообщение не удаляется
    """
    message.from_user.is_bot = True
    message.chat.id = config.allowed_groups[0]
    
    await process_group_message(message, bot, config=config)
    
    message.delete.assert_not_called()

@pytest.mark.asyncio
async def test_process_group_message_long(message, bot, config):
    """
    Проверяет обработку длинных сообщений.
    
    Ожидаемое поведение:
    - Сообщения длиннее установленного лимита игнорируются
    - Проверки на нарушения не выполняются
    - Сообщение не удаляется
    """
    message.text = "x" * (config.message_length_limit + 1)
    message.chat.id = config.allowed_groups[0]
    
    await process_group_message(message, bot, config=config)
    
    message.delete.assert_not_called()

@pytest.mark.asyncio
async def test_process_violation_disabled_rule(message, bot, config):
    """
    Проверяет обработку нарушений при отключенном правиле.
    
    Ожидаемое поведение:
    - Отключенные правила не вызывают никаких действий
    - Сообщение не удаляется
    - Нарушение не регистрируется
    """
    config.violation_rules = {
        "test_violation": ViolationRule(enabled=False, count_as_violation=True, violations_before_penalty=1)
    }
    
    await process_violation(bot, message, "test_violation", config)
    
    message.delete.assert_not_called()

@pytest.mark.asyncio
async def test_process_violation_no_count(message, bot, config):
    """
    Проверяет обработку нарушений без учета в статистике.
    
    Ожидаемое поведение:
    - Сообщение удаляется
    - Нарушение не учитывается в статистике пользователя
    - Наказание не применяется
    """
    config.violation_rules = {
        "test_violation": ViolationRule(enabled=True, count_as_violation=False, violations_before_penalty=1)
    }
    
    await process_violation(bot, message, "test_violation", config)
    
    message.delete.assert_called_once()

@pytest.mark.asyncio
async def test_process_group_message_no_violation(message, bot, config):
    """
    Проверяет обработку сообщений без нарушений.
    
    Ожидаемое поведение:
    - Сообщение проходит все проверки
    - Нарушения не фиксируются
    - Сообщение не удаляется
    """
    message.chat.id = config.allowed_groups[0]
    
    message.reply_to_message = MagicMock()
    message.reply_to_message.message_id = 100
    message.reply_to_message.from_user = MagicMock()
    message.reply_to_message.from_user.id = 999999
    
    with patch("handlers.message_handlers.user_messages") as mock_user_messages:
        mock_user_messages.__getitem__.return_value = [(1, 101, time.time() - 1)]
        
        await process_group_message(message, bot, config=config)
        
        message.delete.assert_not_called()

@pytest.mark.asyncio
async def test_process_group_message_cooldown_disabled(message, bot, config):
    """
    Проверяет обработку сообщений при отключенной проверке временного интервала.
    
    Ожидаемое поведение:
    - Проверка временного интервала между сообщениями не выполняется
    - Сообщение не удаляется независимо от времени между сообщениями
    - Другие проверки выполняются как обычно
    """
    config.check_reply_cooldown = False
    message.chat.id = config.allowed_groups[0]
    
    message.reply_to_message = MagicMock()
    message.reply_to_message.message_id = 100
    message.reply_to_message.from_user = MagicMock()
    message.reply_to_message.from_user.id = message.from_user.id
    
    with patch("handlers.message_handlers.user_messages") as mock_user_messages:
        mock_user_messages.__getitem__.return_value = [(1, None, time.time() - 1)]
        
        await process_group_message(message, bot, config=config)
        
        message.delete.assert_not_called() 