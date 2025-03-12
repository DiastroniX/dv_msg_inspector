import pytest
from admin_notifications import send_admin_notification, make_admin_inline_kb
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from unittest.mock import AsyncMock, patch
from aiogram.exceptions import TelegramAPIError

@pytest.mark.asyncio
async def test_make_admin_inline_kb():
    """Тест создания клавиатуры для админ-уведомлений"""
    user_id = 123456789
    deleted_msg_id = 1
    
    # Тест с deleted_msg_id
    kb = make_admin_inline_kb(user_id, deleted_msg_id)
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 3  # Должно быть 3 кнопки
    
    # Проверяем callback_data кнопок
    assert kb.inline_keyboard[0][0].callback_data == f"revoke_penalty:{user_id}"
    assert kb.inline_keyboard[1][0].callback_data == f"reset_violations:{user_id}"
    assert kb.inline_keyboard[2][0].callback_data == f"restore_message:{deleted_msg_id}"
    
    # Тест без deleted_msg_id
    kb = make_admin_inline_kb(user_id)
    assert len(kb.inline_keyboard) == 2  # Должно быть 2 кнопки

@pytest.mark.asyncio
async def test_send_admin_notification(mock_bot, test_config):
    """Тест отправки уведомления администраторам"""
    # Создаем мок для метода send_message
    mock_bot.send_message = AsyncMock()
    
    user_id = 123456789
    user_name = "test_user"
    violation_type = "no_reply"
    penalty_to_apply = "warning"
    msg_text = "Test message"
    penalty_count = 1
    deleted_msg_id = 1
    
    # Вызываем функцию отправки уведомления
    await send_admin_notification(
        mock_bot,
        test_config,
        user_id,
        user_name,
        violation_type,
        penalty_to_apply,
        msg_text,
        penalty_count,
        deleted_msg_id
    )
    
    # Проверяем, что send_message был вызван с правильными параметрами
    mock_bot.send_message.assert_called_once()
    call_args = mock_bot.send_message.call_args[1]
    
    # Проверяем параметры вызова
    assert call_args["parse_mode"] == "HTML"
    assert isinstance(call_args["reply_markup"], InlineKeyboardMarkup)
    
    # Проверяем обработку составного ID
    admin_chat_id = test_config.admin_chat_id
    if "_" in admin_chat_id:
        chat_id, thread_id = admin_chat_id.split("_")
        assert call_args["chat_id"] == int(chat_id)
        assert call_args["message_thread_id"] == int(thread_id)
    else:
        assert call_args["chat_id"] == int(admin_chat_id)
        assert "message_thread_id" not in call_args

@pytest.mark.asyncio
async def test_send_admin_notification_error_handling(mock_bot, test_config):
    """Тест обработки ошибок при отправке уведомления"""
    # Создаем мок для метода send_message, который вызывает исключение
    mock_bot.send_message = AsyncMock(side_effect=Exception("Test error"))
    mock_bot.get_chat = AsyncMock(side_effect=Exception("Chat not found"))
    
    user_id = 123456789
    user_name = "test_user"
    violation_type = "no_reply"
    penalty_to_apply = "warning"
    msg_text = "Test message"
    penalty_count = 1
    
    # Проверяем, что функция корректно обрабатывает ошибку
    await send_admin_notification(
        mock_bot,
        test_config,
        user_id,
        user_name,
        violation_type,
        penalty_to_apply,
        msg_text,
        penalty_count
    )
    
    # Проверяем, что были вызваны оба метода
    mock_bot.send_message.assert_called_once()
    mock_bot.get_chat.assert_called_once()

@pytest.mark.asyncio
async def test_send_admin_notification_network_error(mock_bot, test_config):
    """Тест обработки сетевой ошибки при отправке уведомления"""
    # Настраиваем мок для имитации сетевой ошибки
    mock_bot.send_message = AsyncMock(side_effect=TelegramAPIError("Network error", "Network error"))
    
    # Вызываем функцию
    await send_admin_notification(
        bot=mock_bot,
        config=test_config,
        user_id=123456789,
        user_name="test_user",
        violation_type="no_reply",
        penalty_to_apply="warning",
        msg_text="Test message",
        penalty_count=1
    )

@pytest.mark.asyncio
async def test_send_admin_notification_invalid_chat(mock_bot, test_config):
    """Тест обработки ошибки неверного chat_id"""
    # Настраиваем мок для имитации ошибки неверного чата
    mock_bot.send_message = AsyncMock(side_effect=TelegramAPIError("Bad Request: chat not found", "Bad Request: chat not found"))
    
    # Вызываем функцию
    await send_admin_notification(
        bot=mock_bot,
        config=test_config,
        user_id=123456789,
        user_name="test_user",
        violation_type="no_reply",
        penalty_to_apply="warning",
        msg_text="Test message",
        penalty_count=1
    )

@pytest.mark.asyncio
async def test_send_admin_notification_multiple_chats(mock_bot, test_config):
    """Тест отправки уведомления в несколько админ-чатов"""
    # Настраиваем несколько админ-чатов
    test_config.admin_chat_id = "123_1"  # Используем один составной ID
    mock_bot.send_message = AsyncMock()
    
    # Вызываем функцию
    await send_admin_notification(
        bot=mock_bot,
        config=test_config,
        user_id=123456789,
        user_name="test_user",
        violation_type="no_reply",
        penalty_to_apply="warning",
        msg_text="Test message",
        penalty_count=1
    )
    
    # Проверяем, что сообщение было отправлено
    mock_bot.send_message.assert_called_once()
    call_args = mock_bot.send_message.call_args[1]
    assert call_args["chat_id"] == 123
    assert call_args["message_thread_id"] == 1

@pytest.mark.asyncio
async def test_make_admin_inline_kb_all_buttons():
    """Тест создания клавиатуры со всеми кнопками"""
    user_id = 123456789
    deleted_msg_id = 1
    
    # Тест с deleted_msg_id
    kb = make_admin_inline_kb(user_id, deleted_msg_id)
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 3  # Должно быть 3 кнопки
    
    # Проверяем callback_data кнопок
    assert kb.inline_keyboard[0][0].callback_data == f"revoke_penalty:{user_id}"
    assert kb.inline_keyboard[1][0].callback_data == f"reset_violations:{user_id}"
    assert kb.inline_keyboard[2][0].callback_data == f"restore_message:{deleted_msg_id}"

@pytest.mark.asyncio
async def test_make_admin_inline_kb_no_restore():
    """Тест создания клавиатуры без кнопки восстановления"""
    user_id = 123456789
    
    # Тест без deleted_msg_id
    kb = make_admin_inline_kb(user_id)
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 2  # Должно быть 2 кнопки
    
    # Проверяем callback_data кнопок
    assert kb.inline_keyboard[0][0].callback_data == f"revoke_penalty:{user_id}"
    assert kb.inline_keyboard[1][0].callback_data == f"reset_violations:{user_id}"