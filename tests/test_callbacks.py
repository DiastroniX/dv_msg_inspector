import pytest
from unittest.mock import AsyncMock, patch
from aiogram.types import CallbackQuery, Message, User, Chat
from handlers.callbacks import (
    revoke_penalty_handler,
    reset_violations_handler,
    restore_message_handler
)
from db.operations import init_db, add_violation, record_deleted_message, get_deleted_message_by_id, get_user_violations_count
from tests.test_texts import TEXTS
from unittest.mock import MagicMock

@pytest.fixture
def mock_callback_query():
    """Фикстура создает мок callback query"""
    callback = AsyncMock(spec=CallbackQuery)
    callback.message = AsyncMock(spec=Message)
    callback.message.chat = AsyncMock(spec=Chat)
    callback.message.chat.id = -1001234567890
    callback.message.reply_markup = None
    
    # Создаем from_user с нужными атрибутами
    from_user = AsyncMock(spec=User)
    from_user.id = 123456789  # ID админа из test_config
    from_user.username = "test_admin"
    from_user.full_name = "Test Admin"
    callback.from_user = from_user
    
    callback.message.message_id = 1
    callback.data = ""
    return callback

@pytest.mark.asyncio
async def test_process_revoke_penalty(mock_callback_query, mock_bot, test_config, clean_db):
    """Тест обработки кнопки снятия ограничений"""
    test_db_path = clean_db
    test_config.db_path = test_db_path
    
    # Добавляем нарушения пользователю
    user_id = 987654321
    for _ in range(3):
        await add_violation(
            user_id=user_id,
            chat_id=mock_callback_query.message.chat.id,
            violation_type="no_reply",
            message_text="Test message",
            db_path=test_db_path
        )
    
    # Настраиваем callback data
    mock_callback_query.data = f"revoke_penalty:{user_id}"
    
    # Настраиваем моки
    mock_bot.restrict_chat_member = AsyncMock()
    mock_bot.send_message = AsyncMock()
    mock_callback_query.answer = AsyncMock()
    mock_bot.get_chat_member = AsyncMock(return_value=MagicMock(can_restrict_members=True))
    
    # Вызываем функцию
    await revoke_penalty_handler(mock_callback_query, mock_bot, test_config)
    
    # Проверяем, что ограничения были сняты
    mock_bot.restrict_chat_member.assert_called_once()
    mock_callback_query.answer.assert_called_once()

@pytest.mark.asyncio
async def test_process_reset_violations(mock_callback_query, mock_bot, test_config, clean_db):
    """Тест обработки кнопки сброса нарушений"""
    test_db_path = clean_db
    test_config.db_path = test_db_path
    
    # Добавляем нарушения пользователю
    user_id = 987654321
    for _ in range(3):
        await add_violation(
            user_id=user_id,
            chat_id=mock_callback_query.message.chat.id,
            violation_type="no_reply",
            message_text="Test message",
            db_path=test_db_path
        )
    
    # Настраиваем callback data
    mock_callback_query.data = f"reset_violations:{user_id}"
    
    # Настраиваем моки
    mock_callback_query.answer = AsyncMock()
    mock_bot.send_message = AsyncMock()
    mock_bot.get_chat_member = AsyncMock(return_value=MagicMock(can_restrict_members=True))
    
    # Вызываем функцию
    await reset_violations_handler(mock_callback_query, mock_bot, test_config)
    
    # Проверяем, что нарушения были сброшены
    violations_count = await get_user_violations_count(user_id, mock_callback_query.message.chat.id, test_db_path)
    assert violations_count == 0
    
    mock_callback_query.answer.assert_called_once()
    mock_bot.send_message.assert_called_once()

@pytest.mark.asyncio
async def test_process_restore_message(mock_callback_query, mock_bot, test_config, test_db_path):
    """Тест обработки кнопки восстановления сообщения"""
    # Инициализируем БД
    await init_db(test_db_path)
    test_config.db_path = test_db_path
    
    # Записываем удаленное сообщение
    user_id = 987654321
    deleted_msg_id = await record_deleted_message(
        user_id=user_id,
        user_name="test_user",
        group_id=mock_callback_query.message.chat.id,
        message_text="Test message",
        db_path=test_db_path
    )
    
    # Настраиваем callback data
    mock_callback_query.data = f"restore_message:{deleted_msg_id}"
    
    # Настраиваем моки
    mock_callback_query.answer = AsyncMock()
    mock_bot.send_message = AsyncMock()
    
    # Вызываем функцию
    await restore_message_handler(mock_callback_query, mock_bot, test_config)
    
    # Проверяем, что сообщение было восстановлено
    mock_callback_query.answer.assert_called_once()
    mock_bot.send_message.assert_called_once()

@pytest.mark.asyncio
async def test_process_revoke_penalty_not_admin(mock_callback_query, mock_bot, test_config):
    """Тест обработки кнопки снятия ограничений не админом"""
    # Меняем ID пользователя на не админский
    mock_callback_query.from_user.id = 999999999
    
    # Настраиваем callback data
    mock_callback_query.data = "revoke_penalty:987654321"
    
    # Настраиваем моки
    mock_callback_query.answer = AsyncMock()
    mock_bot.restrict_chat_member = AsyncMock()
    mock_bot.get_chat_member = AsyncMock(return_value=MagicMock(can_restrict_members=False))
    
    # Вызываем функцию
    await revoke_penalty_handler(mock_callback_query, mock_bot, test_config)
    
    # Проверяем, что действие не выполнено
    mock_bot.restrict_chat_member.assert_not_called()
    mock_callback_query.answer.assert_called_once_with(
        "У вас нет прав для выполнения этого действия",
        show_alert=True
    )

@pytest.mark.asyncio
async def test_process_restore_message_invalid_id(mock_callback_query, mock_bot, test_config, test_db_path):
    """Тест обработки кнопки восстановления с неверным ID сообщения"""
    # Инициализируем БД
    await init_db(test_db_path)
    test_config.db_path = test_db_path
    
    # Настраиваем callback data с несуществующим ID
    mock_callback_query.data = "restore_message:99999"
    
    # Настраиваем моки
    mock_callback_query.answer = AsyncMock()
    mock_bot.send_message = AsyncMock()
    
    # Вызываем функцию
    await restore_message_handler(mock_callback_query, mock_bot, test_config)
    
    # Проверяем, что получили сообщение об ошибке
    mock_callback_query.answer.assert_called_once_with(
        "Сообщение не найдено в БД.",
        show_alert=True
    )
    mock_bot.send_message.assert_not_called() 