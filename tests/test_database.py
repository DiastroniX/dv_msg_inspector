"""
Тесты работы с базой данных
"""
import os
import pytest
import pytest_asyncio
import aiosqlite

@pytest_asyncio.fixture
async def test_db():
    """Фикстура для создания тестовой базы данных"""
    db_path = "test.db"
    
    # Удаляем существующую тестовую БД если она есть
    if os.path.exists(db_path):
        os.remove(db_path)
        
    # Создаем новую БД и возвращаем соединение
    db = await aiosqlite.connect(db_path)
    yield db
    
    # Закрываем соединение
    await db.close()
    
    # Удаляем тестовую БД после завершения теста
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.mark.asyncio 
async def test_simple_db_operations(test_db):
    """Тест базовых операций с базой данных"""
    # Создаем таблицу
    await test_db.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            violation_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Вставляем тестовую запись
    await test_db.execute(
        "INSERT INTO violations (user_id, chat_id, violation_type) VALUES (?, ?, ?)",
        (123456789, -100123456, "test_violation")
    )
    await test_db.commit()
    
    # Проверяем что запись добавлена
    async with test_db.execute("SELECT * FROM violations") as cursor:
        rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][1] == 123456789  # user_id
        assert rows[0][2] == -100123456  # chat_id
        assert rows[0][3] == "test_violation"  # violation_type 