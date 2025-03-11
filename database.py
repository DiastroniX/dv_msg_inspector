import aiosqlite
import time
import os
import asyncio
from typing import Optional, Dict, Callable, Any
from functools import wraps
import logging

DB_PATH = "violations.db"

CREATE_TABLES_SCRIPT = """
-- см. обновлённые CREATE TABLE ... c user_name
CREATE TABLE IF NOT EXISTS users_violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    user_name TEXT,
    group_id INTEGER NOT NULL,
    violation_type TEXT NOT NULL,
    timestamp INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_violations_user_id ON users_violations(user_id);
CREATE INDEX IF NOT EXISTS idx_violations_timestamp ON users_violations(timestamp);

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
    incident_count INTEGER NOT NULL,
    last_incident_ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incidents_timestamp ON users_incidents(last_incident_ts);

-- Добавляем триггер для автоматической очистки старых записей
CREATE TRIGGER IF NOT EXISTS cleanup_old_violations
AFTER INSERT ON users_violations
BEGIN
    DELETE FROM users_violations 
    WHERE timestamp < (strftime('%s', 'now') - 2592000); -- 30 дней
END;

CREATE TRIGGER IF NOT EXISTS cleanup_old_messages
AFTER INSERT ON messages_deleted
BEGIN
    DELETE FROM messages_deleted 
    WHERE timestamp < (strftime('%s', 'now') - 2592000); -- 30 дней
END;
"""

# Создаём пул соединений
_connection_pool = []
MAX_POOL_SIZE = 5

async def get_db_connection():
    """
    Получает соединение из пула или создает новое
    """
    if not _connection_pool:
        conn = await aiosqlite.connect(DB_PATH)
        await conn.execute("PRAGMA journal_mode=WAL")  # Включаем WAL режим
        await conn.execute("PRAGMA synchronous=NORMAL")  # Оптимизируем производительность
        return conn
    return _connection_pool.pop()

async def release_connection(conn):
    """
    Возвращает соединение в пул
    """
    if len(_connection_pool) < MAX_POOL_SIZE:
        _connection_pool.append(conn)
    else:
        await conn.close()

async def retry_on_locked(func: Callable, *args, **kwargs) -> Any:
    """
    Декоратор для повторных попыток при блокировке базы данных.
    Пытается выполнить операцию до 3 раз с интервалом 0.1 секунды.
    """
    max_attempts = 3
    delay = 0.1
    
    for attempt in range(max_attempts):
        try:
            return await func(*args, **kwargs)
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_attempts - 1:
                await asyncio.sleep(delay)
                continue
            raise
    return None

async def init_db():
    # Убедимся, что директория существует
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)

    # Создаём соединение и таблицы
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES_SCRIPT)
        await db.commit()

    # Проверяем, что таблицы действительно созданы
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = await cursor.fetchall()
        await cursor.close()
        
        required_tables = {'users_violations', 'messages_deleted', 'penalties_active', 
                          'violation_counters', 'users_incidents'}
        existing_tables = {table[0] for table in tables}
        
        if not required_tables.issubset(existing_tables):
            missing_tables = required_tables - existing_tables
            raise Exception(f"Failed to create tables: {missing_tables}")

async def cleanup_old_data(config):
    """
    Очищает старые данные из базы данных в соответствии с настройками хранения
    """
    retention_seconds = config.data_retention_days * 24 * 60 * 60
    cutoff_timestamp = int(time.time()) - retention_seconds

    conn = await get_db_connection()
    try:
        async with conn.cursor() as cursor:
            # Очищаем старые нарушения
            await cursor.execute(
                "DELETE FROM users_violations WHERE timestamp < ?",
                (cutoff_timestamp,)
            )
            
            # Очищаем старые удалённые сообщения
            await cursor.execute(
                "DELETE FROM messages_deleted WHERE timestamp < ?",
                (cutoff_timestamp,)
            )
            
            # Очищаем устаревшие активные санкции
            await cursor.execute(
                "DELETE FROM penalties_active WHERE until_date < ? AND until_date IS NOT NULL",
                (cutoff_timestamp,)
            )

        await conn.commit()
    finally:
        await release_connection(conn)

async def start_cleanup_task(config):
    """
    Запускает периодическую очистку старых данных
    """
    while True:
        try:
            await cleanup_old_data(config)
            # Проверяем раз в день
            await asyncio.sleep(24 * 60 * 60)
        except Exception as e:
            logging.error(f"Error in cleanup task: {str(e)}", exc_info=True)
            await asyncio.sleep(60)  # В случае ошибки подождём минуту

async def get_violation_counts(user_id: int) -> Dict[str, int]:
    """Возвращает словарь с количеством нарушений каждого типа"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT violation_type, count FROM violation_counters WHERE user_id=?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return {row[0]: row[1] for row in rows}

async def increment_violation_counter(user_id: int, violation_type: str):
    """Увеличивает счетчик определенного типа нарушения"""
    async def _increment():
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO violation_counters (user_id, violation_type, count)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, violation_type) DO UPDATE
                SET count = count + 1
            """, (user_id, violation_type))
            await db.commit()
    
    await retry_on_locked(_increment)

async def record_violation(user_id: int, user_name: str, group_id: int, violation_type: str, config):
    """
    Записываем нарушение и обновляем incidents если нужно
    """
    now_ts = int(time.time())

    # Проверяем правило для данного типа нарушения
    rule = config.violation_rules.get(violation_type)
    if not rule or not rule.enabled:
        return

    async def _record():
        conn = await get_db_connection()
        try:
            async with conn.cursor() as cursor:
                # Записываем нарушение в лог
                await cursor.execute(
                    "INSERT INTO users_violations (user_id, user_name, group_id, violation_type, timestamp) VALUES (?,?,?,?,?)",
                    (user_id, user_name, group_id, violation_type, now_ts)
                )

                # Увеличиваем счетчик конкретного типа нарушения
                await cursor.execute("""
                    INSERT INTO violation_counters (user_id, violation_type, count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(user_id, violation_type) DO UPDATE
                    SET count = count + 1
                    RETURNING count
                """, (user_id, violation_type))
                
                row = await cursor.fetchone()
                current_count = row[0] if row else 1

                # Если достигли порога для этого типа нарушения и оно считается как violation
                if (rule.count_as_violation and 
                    current_count >= rule.violations_before_penalty):
                    
                    # Сбрасываем счетчик этого типа нарушения
                    await cursor.execute(
                        "UPDATE violation_counters SET count = 0 WHERE user_id=? AND violation_type=?",
                        (user_id, violation_type)
                    )
                    
                    # Обновляем общий счетчик инцидентов атомарно
                    await cursor.execute("""
                        INSERT INTO users_incidents (user_id, incident_count, last_incident_ts)
                        VALUES (?, 1, ?)
                        ON CONFLICT(user_id) DO UPDATE
                        SET incident_count = incident_count + 1,
                            last_incident_ts = ?
                    """, (user_id, now_ts, now_ts))

            await conn.commit()
        finally:
            await release_connection(conn)

    await retry_on_locked(_record)

async def record_deleted_message(user_id: int, user_name: str, group_id: int, message_text: str):
    now_ts = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO messages_deleted (user_id, user_name, group_id, message_text, timestamp) VALUES (?,?,?,?,?)",
            (user_id, user_name, group_id, message_text, now_ts)
        )
        deleted_msg_id = cursor.lastrowid
        await db.commit()
        return deleted_msg_id

# --- Активные санкции ---
async def set_penalty(user_id: int, user_name: str, penalty_type: str, until_date: Optional[int]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO penalties_active (user_id, user_name, penalty_type, until_date)
            VALUES (?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE
              SET user_name=excluded.user_name,
                  penalty_type=excluded.penalty_type,
                  until_date=excluded.until_date
        """, (user_id, user_name, penalty_type, until_date))
        await db.commit()

async def get_penalty(user_id: int) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT penalty_type, until_date FROM penalties_active WHERE user_id=?",
            (user_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
    if row:
        ptype, until = row
        return ptype
    return None

async def revoke_penalty(user_id: int):
    """Убираем любую активную санкцию."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM penalties_active WHERE user_id=?",
            (user_id,)
        )
        await db.commit()

async def get_deleted_message_by_id(deleted_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, user_id, user_name, group_id, message_text, timestamp 
            FROM messages_deleted 
            WHERE id = ?
            """,
            (deleted_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        return row

async def get_incidents_count(user_id: int) -> int:
    """
    Возвращает текущее число 'инцидентов' для пользователя
    """
    conn = await get_db_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT incident_count FROM users_incidents WHERE user_id=?",
                (user_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else 0
    finally:
        await release_connection(conn)

async def reset_violation_counters(user_id: int):
    """Сбрасывает все счетчики нарушений для пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM violation_counters WHERE user_id=?",
            (user_id,)
        )
        await db.commit()

async def reset_all_user_data(user_id: int):
    """Полностью сбрасывает все данные о нарушениях пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Сбрасываем счетчики отдельных нарушений
        await db.execute(
            "DELETE FROM violation_counters WHERE user_id=?",
            (user_id,)
        )
        # Сбрасываем общий счетчик инцидентов
        await db.execute(
            "DELETE FROM users_incidents WHERE user_id=?",
            (user_id,)
        )
        # Очищаем историю нарушений
        await db.execute(
            "DELETE FROM users_violations WHERE user_id=?",
            (user_id,)
        )
        await db.commit()