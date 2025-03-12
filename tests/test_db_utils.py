import asyncio
import os
import aiosqlite
import logging
from typing import Optional, List, Set

logger = logging.getLogger(__name__)

CREATE_TEST_TABLES_SCRIPT = """
CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    violation_type TEXT NOT NULL,
    message_text TEXT,
    context TEXT,
    timestamp INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_violations_user_id ON violations(user_id);
CREATE INDEX IF NOT EXISTS idx_violations_timestamp ON violations(timestamp);

CREATE TABLE IF NOT EXISTS messages_deleted (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    user_name TEXT,
    group_id INTEGER NOT NULL,
    message_text TEXT,
    timestamp INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages_deleted(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages_deleted(timestamp);

CREATE TABLE IF NOT EXISTS penalties_active (
    user_id INTEGER PRIMARY KEY,
    user_name TEXT,
    penalty_type TEXT NOT NULL,
    until_date INTEGER
);
CREATE INDEX IF NOT EXISTS idx_penalties_until_date ON penalties_active(until_date);

CREATE TABLE IF NOT EXISTS violation_counters (
    user_id INTEGER NOT NULL,
    violation_type TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, violation_type)
);

CREATE TABLE IF NOT EXISTS users_incidents (
    user_id INTEGER PRIMARY KEY,
    incident_count INTEGER NOT NULL DEFAULT 0,
    last_incident_ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incidents_timestamp ON users_incidents(last_incident_ts);
"""

async def init_test_db(db_path: str) -> None:
    """Инициализирует тестовую базу данных"""
    logger.info(f"Инициализация тестовой БД: {db_path}")
    
    # Убедимся, что директория существует
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)

    # Создаём соединение и таблицы
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(CREATE_TEST_TABLES_SCRIPT)
        await db.commit()

        # Проверяем, что таблицы созданы
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] async for row in cursor]
        await cursor.close()

        required_tables = {'violations', 'messages_deleted', 'penalties_active', 
                         'violation_counters', 'users_incidents'}
        
        if not required_tables.issubset(set(tables)):
            missing = required_tables - set(tables)
            raise Exception(f"Не удалось создать таблицы: {missing}")

async def cleanup_test_db(db_path: str) -> None:
    """Очищает все таблицы в тестовой базе данных"""
    logger.info(f"Очистка тестовой БД: {db_path}")
    
    async with aiosqlite.connect(db_path) as db:
        # Получаем список всех таблиц
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] async for row in cursor]
        await cursor.close()

        # Очищаем каждую таблицу
        for table in tables:
            await db.execute(f"DELETE FROM {table}")
        await db.commit()

async def verify_table_exists(db_path: str, table_name: str) -> bool:
    """Проверяет существование таблицы в базе данных"""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        exists = await cursor.fetchone() is not None
        await cursor.close()
        return exists

async def get_table_names(db_path: str) -> Set[str]:
    """Возвращает множество имен таблиц в базе данных"""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] async for row in cursor}
        await cursor.close()
        return tables

async def get_table_row_count(db_path: str, table_name: str) -> int:
    """Возвращает количество строк в таблице"""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = (await cursor.fetchone())[0]
        await cursor.close()
        return count

async def verify_db_state(db_path: str) -> bool:
    """Проверяет состояние базы данных"""
    try:
        required_tables = {'violations', 'messages_deleted', 'penalties_active', 
                         'violation_counters', 'users_incidents'}
        
        existing_tables = await get_table_names(db_path)
        
        # Проверяем наличие всех необходимых таблиц
        if not required_tables.issubset(existing_tables):
            missing = required_tables - existing_tables
            logger.error(f"Отсутствуют таблицы: {missing}")
            return False
            
        # Проверяем возможность выполнения базовых операций
        for table in required_tables:
            try:
                count = await get_table_row_count(db_path, table)
                logger.debug(f"Таблица {table}: {count} строк")
            except Exception as e:
                logger.error(f"Ошибка при проверке таблицы {table}: {e}")
                return False
                
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при проверке состояния БД: {e}")
        return False 