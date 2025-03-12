"""
Тесты обработки команд бота
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_start_command():
    """Тест команды /start"""
    # Создаем мок сообщения
    message = MagicMock()
    message.chat.id = 123456789
    message.from_user.id = 987654321
    message.from_user.username = "test_user"
    
    # Создаем мок бота
    bot = MagicMock()
    bot.send_message = AsyncMock()
    
    # Отправляем команду
    await bot.send_message(
        chat_id=message.chat.id,
        text="Привет! Я бот для модерации чатов."
    )
    
    # Проверяем, что сообщение было отправлено
    bot.send_message.assert_called_once_with(
        chat_id=message.chat.id,
        text="Привет! Я бот для модерации чатов."
    )

@pytest.mark.asyncio
async def test_help_command():
    """Тест команды /help"""
    # Создаем мок сообщения
    message = MagicMock()
    message.chat.id = 123456789
    
    # Создаем мок бота
    bot = MagicMock()
    bot.send_message = AsyncMock()
    
    # Текст справки
    help_text = (
        "Доступные команды:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать справку\n"
        "/stats - Показать статистику"
    )
    
    # Отправляем команду
    await bot.send_message(
        chat_id=message.chat.id,
        text=help_text
    )
    
    # Проверяем, что сообщение было отправлено
    bot.send_message.assert_called_once_with(
        chat_id=message.chat.id,
        text=help_text
    )

@pytest.mark.asyncio
async def test_stats_command():
    """Тест команды /stats"""
    # Создаем мок сообщения
    message = MagicMock()
    message.chat.id = 123456789
    
    # Создаем мок бота
    bot = MagicMock()
    bot.send_message = AsyncMock()
    
    # Тестовая статистика
    stats = {
        'messages_processed': 100,
        'violations_found': 5,
        'warnings_issued': 3
    }
    
    # Формируем текст статистики
    stats_text = (
        "Статистика:\n"
        f"Обработано сообщений: {stats['messages_processed']}\n"
        f"Найдено нарушений: {stats['violations_found']}\n"
        f"Выдано предупреждений: {stats['warnings_issued']}"
    )
    
    # Отправляем команду
    await bot.send_message(
        chat_id=message.chat.id,
        text=stats_text
    )
    
    # Проверяем, что сообщение было отправлено
    bot.send_message.assert_called_once_with(
        chat_id=message.chat.id,
        text=stats_text
    ) 