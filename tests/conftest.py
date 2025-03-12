import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from config import Config
import os
import json
from unittest.mock import AsyncMock
from aiogram.types import Message, User, Chat
import aiosqlite
import asyncio
from .test_db_utils import init_test_db, cleanup_test_db, verify_db_state

@pytest.fixture(scope="session")
def test_config():
    """Фикстура с тестовой конфигурацией"""
    config_data = {
        "bot_token": "test_token",
        "allowed_groups": [-1001234567890],
        "admin_ids": [123456789],
        "admin_chat_id": "-1001234567890_1",
        "message_length_limit": 500,
        "check_reply_cooldown": True,
        "reply_cooldown_seconds": 3600,
        "warn_admins": True,
        "mute_duration_seconds": 300,
        "temp_ban_duration_seconds": 3600,
        "violation_rules": {
            "no_reply": {
                "enabled": True,
                "count_as_violation": True,
                "violations_before_penalty": 1
            },
            "double_reply": {
                "enabled": True,
                "count_as_violation": True,
                "violations_before_penalty": 1
            },
            "self_reply": {
                "enabled": True,
                "count_as_violation": True,
                "violations_before_penalty": 1
            }
        },
        "penalties": {
            "1": "warning",
            "3": "read-only",
            "5": "kick",
            "7": "kick+ban",
            "10": "ban"
        },
        "notifications": {
            "new_violation": True,
            "mute_applied": True,
            "kick_applied": True,
            "ban_applied": True,
            "admin": True
        },
        "delete_bot_messages": True,
        "bot_message_lifetime_seconds": 30,
        "delete_penalty_messages": True,
        "penalty_message_lifetime_seconds": 60,
        "bot_message_delay_seconds": 1,
        "data_retention_days": 30,
        "logging": {
            "enabled": True,
            "level": "DEBUG",
            "modules": {
                "bot": True,
                "handlers": True,
                "database": True,
                "admin": True
            },
            "message_deletion": True,
            "violations": True,
            "penalties": True,
            "config": True
        }
    }
    return Config.from_dict(config_data)

@pytest_asyncio.fixture(scope="function")
async def test_db_path(tmp_path):
    """Фикстура создает временную тестовую базу данных"""
    db_path = tmp_path / "test_violations.db"
    return str(db_path)

@pytest_asyncio.fixture(scope="function")
async def clean_db(test_db_path):
    """Фикстура для инициализации и очистки базы перед каждым тестом"""
    # Инициализируем тестовую базу данных
    await init_test_db(test_db_path)
    
    # Проверяем состояние БД
    assert await verify_db_state(test_db_path), "Ошибка инициализации тестовой БД"
    
    yield test_db_path
    
    # Очищаем БД после теста
    await cleanup_test_db(test_db_path)
    
    # Удаляем файл БД
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except:
            pass

@pytest.fixture(scope="function")
def mock_bot():
    """Фикстура с моком бота для тестов"""
    bot = AsyncMock(spec=Bot)
    bot.send_message = AsyncMock()
    bot.delete_message = AsyncMock()
    bot.restrict_chat_member = AsyncMock()
    bot.ban_chat_member = AsyncMock()
    bot.unban_chat_member = AsyncMock()
    return bot

@pytest.fixture(scope="function")
def mock_message():
    """Создает мок сообщения"""
    message = AsyncMock(spec=Message)
    message.message_id = 1
    message.from_user = AsyncMock(spec=User)
    message.from_user.id = 123456789
    message.from_user.username = "test_user"
    message.chat = AsyncMock(spec=Chat)
    message.chat.id = -1001234567890
    message.text = "Test message"
    message.message_auto_delete_timer_changed = None
    message.pinned_message = None
    return message

@pytest.fixture(scope="function")
def mock_callback_query():
    """Фикстура с моком callback query для тестов"""
    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.chat.id = -1001234567890
    callback.from_user = AsyncMock()
    callback.from_user.id = 123456789
    callback.from_user.username = "test_user"
    callback.from_user.full_name = "Test User"
    callback.data = "test_data"
    return callback 