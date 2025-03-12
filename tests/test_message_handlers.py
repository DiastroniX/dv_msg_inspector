import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aiogram.types import Message, Chat, User, ChatPermissions
from handlers.message_handlers import (
    process_group_message,
    apply_penalties_if_needed,
    is_admin,
    process_violation
)
from db.operations import (
    init_db,
    add_violation,
    get_user_violations_count,
    record_deleted_message
)
from datetime import datetime, timedelta
import time
import asyncio

@pytest.fixture
def mock_message():
    """Фикстура создает мок сообщения"""
    message = AsyncMock(spec=Message)
    message.message_id = 1
    message.chat = AsyncMock(spec=Chat)
    message.chat.id = -1001234567890
    message.chat.type = "supergroup"
    message.from_user = AsyncMock(spec=User)
    message.from_user.id = 123456789
    message.from_user.username = "test_user"
    message.from_user.full_name = "Test User"
    message.from_user.is_bot = False
    message.text = "Test message"
    message.reply_to_message = None
    message.sender_chat = None
    message.new_chat_members = None
    message.left_chat_member = None
    message.new_chat_title = None
    message.new_chat_photo = None
    message.delete_chat_photo = None
    message.group_chat_created = None
    message.message_thread_id = None
    message.message_auto_delete_timer_changed = None
    message.pinned_message = None
    return message

@pytest.mark.asyncio
async def test_process_group_message_admin_chat(mock_message, mock_bot, test_config):
    """Тест обработки сообщения в админ чате"""
    # Устанавливаем ID чата равным админскому
    mock_message.chat.id = int(test_config.admin_chat_id.split('_')[0])
    mock_message.message_thread_id = int(test_config.admin_chat_id.split('_')[1])
    
    # Вызываем функцию
    result = await process_group_message(mock_message, mock_bot, mock_message.from_user, config=test_config)
    
    # Проверяем, что сообщение в админ чате игнорируется
    assert result is None
    mock_message.delete.assert_not_called()

@pytest.mark.asyncio
async def test_process_group_message_not_allowed_group(mock_message, mock_bot, test_config):
    """Тест обработки сообщения в не разрешенной группе"""
    # Устанавливаем ID чата, которого нет в разрешенных
    mock_message.chat.id = -9999999999
    
    # Вызываем функцию
    result = await process_group_message(mock_message, mock_bot, mock_message.from_user, config=test_config)
    
    # Проверяем, что сообщение игнорируется
    assert result is None
    mock_message.delete.assert_not_called()

@pytest.mark.asyncio
async def test_process_group_message_bot_message(mock_message, mock_bot, test_config):
    """Тест обработки сообщения от бота"""
    mock_message.from_user.is_bot = True
    
    # Вызываем функцию
    result = await process_group_message(mock_message, mock_bot, mock_message.from_user, config=test_config)
    
    # Проверяем, что сообщение от бота игнорируется
    assert result is None
    mock_message.delete.assert_not_called()

@pytest.mark.asyncio
async def test_process_group_message_no_reply_violation(mock_message, mock_bot, test_config, clean_db):
    """Тест обработки нарушения 'no_reply'"""
    test_db_path = clean_db
    test_config.db_path = test_db_path
    
    # Настраиваем правила
    test_config.violation_rules["no_reply"].enabled = True
    test_config.violation_rules["no_reply"].count_as_violation = True
    test_config.check_reply_cooldown = True
    test_config.reply_cooldown_seconds = 0.05
    
    # Настраиваем моки
    mock_bot.send_message = AsyncMock()
    mock_bot.delete_message = AsyncMock()
    mock_message.delete = AsyncMock()
    mock_bot.get_chat_member = AsyncMock(return_value=MagicMock(can_restrict_members=True))
    mock_message.from_user.is_bot = False
    
    # Первое сообщение
    await process_group_message(mock_message, mock_bot, mock_message.from_user, config=test_config)
    
    # Имитируем короткий промежуток времени
    await asyncio.sleep(0.1)
    
    # Второе сообщение без реплая
    await process_group_message(mock_message, mock_bot, mock_message.from_user, config=test_config)
    
    # Проверяем, что сообщение было удалено
    mock_message.delete.assert_called()

@pytest.mark.asyncio
async def test_apply_penalties_warning(mock_message, mock_bot, test_config, clean_db):
    """Тест применения наказания 'warning'"""
    test_db_path = clean_db
    test_config.db_path = test_db_path
    
    # Настраиваем правила наказаний
    test_config.penalties = {"2": "warning"}
    test_config.violation_rules["no_reply"].enabled = True
    test_config.violation_rules["no_reply"].count_as_violation = True
    
    # Добавляем нарушения до порога warning
    for _ in range(2):
        await add_violation(
            user_id=mock_message.from_user.id,
            chat_id=mock_message.chat.id,
            violation_type="no_reply",
            message_text="Test message",
            db_path=test_db_path
        )
    
    # Настраиваем моки
    mock_bot.send_message = AsyncMock()
    mock_bot.get_chat_member = AsyncMock(return_value=MagicMock(can_restrict_members=True))
    
    # Применяем наказание
    await apply_penalties_if_needed(
        user_id=mock_message.from_user.id,
        user_name=mock_message.from_user.username,
        group_id=mock_message.chat.id,
        config=test_config,
        violation_type="no_reply",
        msg_text="Test message",
        bot=mock_bot
    )
    
    # Проверяем, что было отправлено предупреждение
    mock_bot.send_message.assert_called()

@pytest.mark.asyncio
async def test_apply_penalties_mute(mock_message, mock_bot, test_config, clean_db):
    """Тест применения наказания 'read-only'"""
    test_db_path = clean_db
    test_config.db_path = test_db_path
    
    # Настраиваем правила наказаний
    test_config.penalties = {"3": "read-only"}
    test_config.violation_rules["no_reply"].enabled = True
    test_config.violation_rules["no_reply"].count_as_violation = True
    
    # Добавляем нарушения до порога read-only
    for _ in range(3):
        await add_violation(
            user_id=mock_message.from_user.id,
            chat_id=mock_message.chat.id,
            violation_type="no_reply",
            message_text="Test message",
            db_path=test_db_path
        )
    
    # Настраиваем моки
    mock_bot.restrict_chat_member = AsyncMock()
    mock_bot.send_message = AsyncMock()
    mock_bot.get_chat_member = AsyncMock(return_value=MagicMock(can_restrict_members=True))
    
    # Применяем наказание
    await apply_penalties_if_needed(
        user_id=mock_message.from_user.id,
        user_name=mock_message.from_user.username,
        group_id=mock_message.chat.id,
        config=test_config,
        violation_type="no_reply",
        msg_text="Test message",
        bot=mock_bot
    )
    
    # Проверяем, что был установлен мут
    mock_bot.restrict_chat_member.assert_called_once()

@pytest.mark.asyncio
async def test_process_violation_disabled_rule(mock_message, mock_bot, test_config, test_db_path):
    """Тест обработки отключенного правила"""
    # Отключаем правило
    test_config.violation_rules["no_reply"].enabled = False
    test_config.db_path = test_db_path
    
    # Вызываем функцию
    await process_violation(
        bot=mock_bot,
        message=mock_message,
        violation_type="no_reply",
        config=test_config
    )
    
    # Проверяем, что ничего не произошло
    mock_message.delete.assert_not_called()
    mock_bot.send_message.assert_not_called()

@pytest.mark.asyncio
async def test_process_violation_not_counted(mock_message, mock_bot, test_config, test_db_path):
    """Тест обработки нарушения, которое не считается за violation"""
    # Настраиваем правило
    test_config.violation_rules["no_reply"].count_as_violation = False
    test_config.db_path = test_db_path
    
    # Вызываем функцию
    await process_violation(
        bot=mock_bot,
        message=mock_message,
        violation_type="no_reply",
        config=test_config
    )
    
    # Проверяем, что сообщение удалено, но нарушение не записано
    mock_message.delete.assert_called_once()
    mock_bot.send_message.assert_not_called()

@pytest.mark.asyncio
async def test_process_group_message_double_reply(mock_message, mock_bot, test_config, clean_db):
    """Тест обработки нарушения 'double_reply'"""
    test_db_path = clean_db
    test_config.db_path = test_db_path
    
    # Настраиваем правила
    test_config.violation_rules["double_reply"].enabled = True
    test_config.violation_rules["double_reply"].count_as_violation = True
    
    # Создаем сообщение, на которое будет реплай
    original_message = AsyncMock(spec=Message)
    original_message.message_id = 100
    original_message.from_user = AsyncMock(spec=User)
    original_message.from_user.id = 111111  # другой пользователь
    
    # Настраиваем первый реплай
    mock_message.reply_to_message = original_message
    mock_message.message_id = 101
    mock_message.delete = AsyncMock()
    mock_bot.get_chat_member = AsyncMock(return_value=MagicMock(can_restrict_members=True))
    mock_message.from_user.is_bot = False
    
    # Первый реплай
    await process_group_message(mock_message, mock_bot, mock_message.from_user, config=test_config)
    
    # Имитируем короткий промежуток времени
    await asyncio.sleep(0.1)
    
    # Второй реплай на то же сообщение
    mock_message.message_id = 102
    await process_group_message(mock_message, mock_bot, mock_message.from_user, config=test_config)
    
    # Проверяем, что второе сообщение было удалено
    mock_message.delete.assert_called()

@pytest.mark.asyncio
async def test_process_group_message_self_reply(mock_message, mock_bot, test_config, clean_db):
    """Тест обработки нарушения 'self_reply'"""
    test_db_path = clean_db
    test_config.db_path = test_db_path
    
    # Настраиваем правила
    test_config.violation_rules["self_reply"].enabled = True
    test_config.violation_rules["self_reply"].count_as_violation = True
    
    # Создаем сообщение, на которое будет реплай
    original_message = AsyncMock(spec=Message)
    original_message.message_id = 100
    original_message.from_user = AsyncMock(spec=User)
    original_message.from_user.id = mock_message.from_user.id  # тот же пользователь
    
    # Настраиваем реплай
    mock_message.reply_to_message = original_message
    mock_message.delete = AsyncMock()
    mock_bot.get_chat_member = AsyncMock(return_value=MagicMock(can_restrict_members=True))
    mock_message.from_user.is_bot = False
    
    # Вызываем функцию
    await process_group_message(mock_message, mock_bot, mock_message.from_user, config=test_config)
    
    # Проверяем, что сообщение было удалено
    mock_message.delete.assert_called()

@pytest.mark.asyncio
async def test_process_group_message_long_message(mock_message, mock_bot, test_config):
    """Тест обработки длинного сообщения"""
    # Создаем сообщение длиннее лимита
    mock_message.text = "a" * (test_config.message_length_limit + 1)
    
    # Отправляем сообщение
    await process_group_message(mock_message, mock_bot, mock_message.from_user, config=test_config)
    
    # Проверяем, что сообщение не было обработано как нарушение
    mock_message.delete.assert_not_called()

@pytest.mark.asyncio
async def test_process_group_message_admin_user(mock_message, mock_bot, test_config):
    """Тест обработки сообщения от администратора"""
    # Делаем пользователя администратором
    mock_message.from_user.id = test_config.admin_ids[0]
    
    # Отправляем сообщение без реплая
    await process_group_message(mock_message, mock_bot, mock_message.from_user, config=test_config)
    
    # Проверяем, что сообщение не было удалено
    mock_message.delete.assert_not_called()

@pytest.mark.asyncio
async def test_apply_penalties_kick(mock_message, mock_bot, test_config, clean_db):
    """Тест применения наказания 'kick'"""
    test_db_path = clean_db
    test_config.db_path = test_db_path
    
    # Настраиваем правила наказаний
    test_config.penalties = {"5": "kick"}
    test_config.violation_rules["no_reply"].enabled = True
    test_config.violation_rules["no_reply"].count_as_violation = True
    
    # Добавляем нарушения до порога kick
    for _ in range(5):
        await add_violation(
            user_id=mock_message.from_user.id,
            chat_id=mock_message.chat.id,
            violation_type="no_reply",
            message_text="Test message",
            db_path=test_db_path
        )
    
    # Настраиваем моки
    mock_bot.ban_chat_member = AsyncMock()
    mock_bot.unban_chat_member = AsyncMock()
    mock_bot.send_message = AsyncMock()
    mock_bot.get_chat_member = AsyncMock(return_value=MagicMock(can_restrict_members=True))
    
    # Применяем наказание
    await apply_penalties_if_needed(
        user_id=mock_message.from_user.id,
        user_name=mock_message.from_user.username,
        group_id=mock_message.chat.id,
        config=test_config,
        violation_type="no_reply",
        msg_text="Test message",
        bot=mock_bot
    )
    
    # Проверяем, что был выполнен кик
    mock_bot.ban_chat_member.assert_called_once()

@pytest.mark.asyncio
async def test_apply_penalties_ban(mock_message, mock_bot, test_config, clean_db):
    """Тест применения наказания 'ban'"""
    test_db_path = clean_db
    test_config.db_path = test_db_path
    
    # Настраиваем правила наказаний
    test_config.penalties = {"10": "ban"}
    test_config.violation_rules["no_reply"].enabled = True
    test_config.violation_rules["no_reply"].count_as_violation = True
    
    # Добавляем нарушения до порога ban
    for _ in range(10):
        await add_violation(
            user_id=mock_message.from_user.id,
            chat_id=mock_message.chat.id,
            violation_type="no_reply",
            message_text="Test message",
            db_path=test_db_path
        )
    
    # Настраиваем моки
    mock_bot.ban_chat_member = AsyncMock()
    mock_bot.send_message = AsyncMock()
    mock_bot.get_chat_member = AsyncMock(return_value=MagicMock(can_restrict_members=True))
    
    # Применяем наказание
    await apply_penalties_if_needed(
        user_id=mock_message.from_user.id,
        user_name=mock_message.from_user.username,
        group_id=mock_message.chat.id,
        config=test_config,
        violation_type="no_reply",
        msg_text="Test message",
        bot=mock_bot
    )
    
    # Проверяем, что был выполнен бан
    mock_bot.ban_chat_member.assert_called_once() 