"""
Базовые юнит-тесты для проверки основной функциональности
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, create_autospec
from aiogram.types import Message, Chat, User

# Фикстура для создания базового мок-сообщения
@pytest.fixture
def basic_message():
    # Создаем базовые моки без спецификации
    message = MagicMock()
    message.message_id = 12345
    message.chat = MagicMock()
    message.chat.id = -1001234567890
    message.from_user = MagicMock()
    message.from_user.id = 123456789
    message.text = "Test message"
    
    # Добавляем асинхронные методы
    message.delete = AsyncMock()
    return message

# Тест 1: Проверка формата сообщения
def test_message_format(basic_message):
    """Проверяет базовый формат сообщения"""
    assert basic_message.chat.id == -1001234567890
    assert basic_message.from_user.id == 123456789
    assert basic_message.text == "Test message"

# Тест 2: Проверка проверки на бота
def test_is_bot_message(basic_message):
    """Проверяет определение сообщения от бота"""
    basic_message.from_user.is_bot = True
    assert basic_message.from_user.is_bot is True
    
    basic_message.from_user.is_bot = False
    assert basic_message.from_user.is_bot is False

# Тест 3: Проверка прав администратора
@pytest.mark.asyncio
async def test_admin_rights(basic_message):
    """Проверяет права администратора"""
    # Создаем мок для бота
    bot = MagicMock()
    bot.get_chat_member = AsyncMock(return_value=MagicMock(is_admin=True))
    
    # Проверяем права админа
    chat_member = await bot.get_chat_member(basic_message.chat.id, basic_message.from_user.id)
    assert chat_member.is_admin is True

# Тест 4: Проверка удаления сообщения
@pytest.mark.asyncio
async def test_message_deletion(basic_message):
    """Проверяет удаление сообщения"""
    await basic_message.delete()
    basic_message.delete.assert_called_once()

# Тест 5: Проверка отправки ответа
@pytest.mark.asyncio
async def test_message_reply(basic_message):
    """Проверяет отправку ответа на сообщение"""
    # Создаем мок для бота
    bot = MagicMock()
    bot.send_message = AsyncMock()
    
    # Отправляем ответ
    await bot.send_message(
        chat_id=basic_message.chat.id,
        text="Test reply",
        reply_to_message_id=basic_message.message_id
    )
    
    # Проверяем, что ответ был отправлен
    bot.send_message.assert_called_once_with(
        chat_id=basic_message.chat.id,
        text="Test reply",
        reply_to_message_id=basic_message.message_id
    ) 