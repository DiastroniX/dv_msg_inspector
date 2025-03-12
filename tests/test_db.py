import pytest
import asyncio
import sqlite3
from datetime import datetime, timedelta
from db.operations import (
    init_db,
    add_violation,
    get_user_violations_count,
    get_user_active_violations,
    cleanup_old_violations,
    record_deleted_message,
    get_incidents_count,
    get_deleted_message_by_id,
)
from config import Config
import aiosqlite
import time

@pytest.fixture
async def clean_db(test_db_path):
    """Фикстура для очистки базы перед каждым тестом"""
    await init_db(test_db_path)
    async with aiosqlite.connect(test_db_path) as db:
        await db.execute("DELETE FROM violations")
        await db.execute("DELETE FROM messages_deleted")
        await db.execute("DELETE FROM penalties_active")
        await db.commit()
    return test_db_path

@pytest.mark.asyncio
async def test_db_initialization(test_db_path):
    """Тест инициализации базы данных"""
    await init_db(test_db_path)
    # Если инициализация прошла успешно, исключений не будет

@pytest.mark.asyncio
async def test_add_violation(test_db_path, test_config):
    """Тест добавления нарушения"""
    await init_db(test_db_path)
    
    user_id = 123456789
    chat_id = -1001234567890
    violation_type = "no_reply"
    message_text = "Test message"
    
    violation = await add_violation(
        user_id=user_id,
        chat_id=chat_id,
        violation_type=violation_type,
        message_text=message_text,
        db_path=test_db_path
    )
    
    assert violation["user_id"] == user_id
    assert violation["chat_id"] == chat_id
    assert violation["violation_type"] == violation_type
    assert violation["message_text"] == message_text

@pytest.mark.asyncio
async def test_get_violations_count(clean_db):
    """Тест подсчета нарушений пользователя"""
    test_db_path = clean_db
    
    user_id = 123456789
    chat_id = -1001234567890
    
    # Добавляем несколько нарушений
    for _ in range(3):
        await add_violation(
            user_id=user_id,
            chat_id=chat_id,
            violation_type="no_reply",
            message_text="Test message",
            db_path=test_db_path
        )
    
    # Проверяем количество нарушений
    count = await get_user_violations_count(user_id, chat_id, db_path=test_db_path)
    assert count == 3, f"Expected 3 violations, but got {count}"

async def cleanup_old_violations_once(days: int, db_path: str) -> None:
    """Однократная очистка старых нарушений без бесконечного цикла"""
    async with aiosqlite.connect(db_path) as db:
        now = int(time.time())
        cutoff_ts = now - (days * 86400)
        
        await db.execute("DELETE FROM violations WHERE timestamp < ?", (cutoff_ts,))
        await db.execute("DELETE FROM messages_deleted WHERE timestamp < ?", (cutoff_ts,))
        await db.execute(
            "DELETE FROM penalties_active WHERE until_date < ? AND until_date IS NOT NULL",
            (now,)
        )
        await db.commit()

@pytest.mark.asyncio
async def test_cleanup_old_violations(test_db_path):
    """Тест очистки старых нарушений"""
    await init_db(test_db_path)
    
    user_id = 123456789
    chat_id = -1001234567890
    
    # Добавляем нарушение
    await add_violation(
        user_id=user_id,
        chat_id=chat_id,
        violation_type="no_reply",
        message_text="Test message",
        db_path=test_db_path
    )
    
    # Изменяем время нарушения на старое (более 24 часов назад)
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    old_time = int(time.time()) - 86401  # 24 часа + 1 секунда
    cursor.execute(
        "UPDATE violations SET timestamp = ? WHERE user_id = ?",
        (old_time, user_id)
    )
    conn.commit()
    conn.close()
    
    # Проверяем количество активных нарушений (должно быть 0, так как все старые)
    count = await get_user_violations_count(user_id, chat_id, test_db_path)
    assert count == 0, f"Expected 0 active violations after 24 hours, but got {count}"

@pytest.mark.asyncio
async def test_record_deleted_message(test_db_path):
    """Тест записи удаленного сообщения"""
    await init_db(test_db_path)
    
    user_id = 123456789
    user_name = "test_user"
    group_id = -1001234567890
    message_text = "Test message"
    
    msg_id = await record_deleted_message(
        user_id=user_id,
        user_name=user_name,
        group_id=group_id,
        message_text=message_text,
        db_path=test_db_path
    )
    
    assert msg_id is not None  # Проверяем, что сообщение записано

@pytest.mark.asyncio
async def test_init_db(test_db_path):
    """Тест инициализации базы данных"""
    # Инициализируем БД
    await init_db(test_db_path)
    
    # Проверяем, что таблицы созданы
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    
    # Проверяем таблицу violations
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='violations'")
    assert cursor.fetchone() is not None
    
    # Проверяем таблицу messages_deleted
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages_deleted'")
    assert cursor.fetchone() is not None
    
    conn.close()

@pytest.mark.asyncio
async def test_add_and_get_violations(clean_db):
    """Тест добавления и получения нарушений"""
    test_db_path = clean_db
    
    user_id = 123456789
    chat_id = -1001234567890
    
    # Добавляем нарушения
    await add_violation(user_id, chat_id, "no_reply", "Test message", db_path=test_db_path)
    await add_violation(user_id, chat_id, "double_reply", "Test message 2", db_path=test_db_path)
    
    # Проверяем количество нарушений
    count = await get_user_violations_count(user_id, chat_id, db_path=test_db_path)
    assert count == 2, f"Expected 2 violations, but got {count}"

@pytest.mark.asyncio
async def test_clean_old_violations(test_db_path):
    """Тест очистки старых нарушений (более 7 дней)"""
    await init_db(test_db_path)
    
    user_id = 123456789
    chat_id = -1001234567890
    
    # Добавляем нарушение
    await add_violation(user_id, chat_id, "no_reply", "Test message", db_path=test_db_path)
    
    # Изменяем время нарушения на старое
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    old_time = datetime.now() - timedelta(days=8)
    cursor.execute(
        "UPDATE violations SET timestamp = ? WHERE user_id = ?",
        (old_time.timestamp(), user_id)
    )
    conn.commit()
    conn.close()
    
    # Очищаем старые нарушения с таймаутом
    try:
        async with asyncio.timeout(5):
            await cleanup_old_violations_once(7, test_db_path)
    except asyncio.TimeoutError:
        pytest.fail("Тест clean_old_violations превысил таймаут в 5 секунд")
    
    # Проверяем, что нарушение удалено
    count = await get_user_violations_count(user_id, chat_id, test_db_path)
    assert count == 0

@pytest.mark.asyncio
async def test_record_and_get_deleted_message(test_db_path):
    """Тест записи и получения удаленного сообщения"""
    await init_db(test_db_path)
    
    user_id = 123456789
    group_id = -1001234567890
    message_text = "Test message"
    user_name = "test_user"
    
    # Записываем удаленное сообщение
    msg_id = await record_deleted_message(
        user_id=user_id,
        user_name=user_name,
        group_id=group_id,
        message_text=message_text,
        db_path=test_db_path
    )
    
    # Получаем удаленное сообщение
    msg = await get_deleted_message_by_id(msg_id, test_db_path)
    
    # Проверяем данные
    assert msg[1] == user_id  # user_id
    assert msg[3] == group_id  # group_id
    assert msg[4] == message_text  # message_text
    assert msg[2] == user_name  # user_name

@pytest.mark.asyncio
async def test_delete_old_messages(test_db_path):
    """Тест удаления старых сообщений"""
    await init_db(test_db_path)
    
    user_id = 123456789
    group_id = -1001234567890
    message_text = "Test message"
    user_name = "test_user"
    
    # Записываем сообщение
    msg_id = await record_deleted_message(
        user_id=user_id,
        user_name=user_name,
        group_id=group_id,
        message_text=message_text,
        db_path=test_db_path
    )
    
    # Изменяем время сообщения на старое
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    old_time = datetime.now() - timedelta(days=8)
    cursor.execute(
        "UPDATE messages_deleted SET timestamp = ? WHERE id = ?",
        (old_time.timestamp(), msg_id)
    )
    conn.commit()
    conn.close()
    
    # Удаляем старые сообщения
    try:
        async with asyncio.timeout(5):
            await cleanup_old_violations_once(7, test_db_path)
    except asyncio.TimeoutError:
        pytest.fail("Тест delete_old_messages превысил таймаут в 5 секунд")
    
    # Проверяем, что сообщение удалено
    msg = await get_deleted_message_by_id(msg_id, test_db_path)
    assert msg is None

@pytest.mark.asyncio
async def test_concurrent_violations(clean_db):
    """Тест одновременного добавления нарушений"""
    test_db_path = clean_db
    
    user_id = 123456789
    chat_id = -1001234567890
    
    # Добавляем нарушения одновременно
    await asyncio.gather(
        add_violation(user_id, chat_id, "no_reply", "Test 1", db_path=test_db_path),
        add_violation(user_id, chat_id, "no_reply", "Test 2", db_path=test_db_path),
        add_violation(user_id, chat_id, "no_reply", "Test 3", db_path=test_db_path)
    )
    
    # Проверяем количество нарушений
    count = await get_user_violations_count(user_id, chat_id, db_path=test_db_path)
    assert count == 3, f"Expected 3 violations, but got {count}"

@pytest.mark.asyncio
async def test_get_nonexistent_message(test_db_path):
    """Тест получения несуществующего сообщения"""
    await init_db(test_db_path)
    
    # Пытаемся получить несуществующее сообщение
    msg = await get_deleted_message_by_id(999999, test_db_path)
    assert msg is None 