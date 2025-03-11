import asyncio
import logging
import time
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Callable
from functools import wraps

import aiosqlite
from config import Config

logger = logging.getLogger(__name__)

DB_PATH = "violations.db"

CREATE_TABLES_SCRIPT = """
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

-- Добавляем триггер для автоматической очистки старых записей
CREATE TRIGGER IF NOT EXISTS cleanup_old_violations
AFTER INSERT ON violations
BEGIN
    DELETE FROM violations 
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
    """Получает соединение из пула или создает новое"""
    if not _connection_pool:
        conn = await aiosqlite.connect(DB_PATH)
        await conn.execute("PRAGMA journal_mode=WAL")  # Включаем WAL режим
        await conn.execute("PRAGMA synchronous=NORMAL")  # Оптимизируем производительность
        return conn
    return _connection_pool.pop()

async def release_connection(conn):
    """Возвращает соединение в пул"""
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

async def init_db() -> None:
    """Инициализирует базу данных"""
    logger.info("Инициализация базы данных...")
    
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
        
        required_tables = {'violations', 'messages_deleted', 'penalties_active', 
                          'violation_counters', 'users_incidents'}
        existing_tables = {table[0] for table in tables}
        
        if not required_tables.issubset(existing_tables):
            missing_tables = required_tables - existing_tables
            raise Exception(f"Failed to create tables: {missing_tables}")
            
    logger.info("База данных инициализирована успешно")

async def add_violation(
    user_id: int,
    chat_id: int,
    violation_type: str,
    message_text: str,
    context: Optional[Dict[str, Any]] = None
) -> Dict:
    """Добавляет новое нарушение в базу данных"""
    logger.debug(f"Добавление нарушения: user_id={user_id}, chat_id={chat_id}, type={violation_type}")
    
    now_ts = int(time.time())
    
    async def _add():
        conn = await get_db_connection()
        try:
            async with conn.cursor() as cursor:
                # Записываем нарушение
                await cursor.execute(
                    """
                    INSERT INTO violations (user_id, chat_id, violation_type, message_text, context, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, chat_id, violation_type, message_text, str(context) if context else None, now_ts)
                )
                violation_id = cursor.lastrowid
                
                # Получаем добавленное нарушение
                await cursor.execute(
                    "SELECT * FROM violations WHERE id = ?",
                    (violation_id,)
                )
                row = await cursor.fetchone()
                
            await conn.commit()
            logger.info(f"Добавлено нарушение с ID {violation_id}")
            
            return {
                "id": row[0],
                "user_id": row[1],
                "chat_id": row[2],
                "violation_type": row[3],
                "message_text": row[4],
                "context": eval(row[5]) if row[5] else None,
                "timestamp": datetime.fromtimestamp(row[6])
            }
        finally:
            await release_connection(conn)
    
    return await retry_on_locked(_add)

async def get_user_violations_count(user_id: int, chat_id: int) -> int:
    """Возвращает количество активных нарушений пользователя"""
    logger.debug(f"Подсчет активных нарушений: user_id={user_id}, chat_id={chat_id}")
    
    one_day_ago = int(time.time()) - 86400  # 24 часа в секундах
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT COUNT(*) FROM violations
            WHERE user_id = ? AND chat_id = ?
            AND timestamp > ?
            """,
            (user_id, chat_id, one_day_ago)
        ) as cursor:
            count = (await cursor.fetchone())[0]
            
    logger.debug(f"Найдено {count} активных нарушений")
    return count

async def get_user_active_violations(user_id: int, chat_id: int) -> List[Dict]:
    """Возвращает список активных нарушений пользователя"""
    logger.debug(f"Получение активных нарушений: user_id={user_id}, chat_id={chat_id}")
    
    one_day_ago = int(time.time()) - 86400  # 24 часа в секундах
    violations = []
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT * FROM violations
            WHERE user_id = ? AND chat_id = ?
            AND timestamp > ?
            ORDER BY timestamp DESC
            """,
            (user_id, chat_id, one_day_ago)
        ) as cursor:
            async for row in cursor:
                violations.append({
                    "id": row[0],
                    "user_id": row[1],
                    "chat_id": row[2],
                    "violation_type": row[3],
                    "message_text": row[4],
                    "context": eval(row[5]) if row[5] else None,
                    "timestamp": datetime.fromtimestamp(row[6])
                })
                
    logger.debug(f"Получено {len(violations)} активных нарушений")
    return violations

async def cleanup_old_violations(config: Config) -> None:
    """Удаляет старые нарушения из базы данных"""
    logger.info("Запуск задачи очистки старых нарушений")
    
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                now = int(time.time())
                cutoff_ts = now - (config.data_retention_days * 86400)  # конвертируем дни в секунды
                
                # Удаляем старые нарушения
                cursor = await db.execute(
                    "DELETE FROM violations WHERE timestamp < ?",
                    (cutoff_ts,)
                )
                violations_deleted = cursor.rowcount

                # Удаляем старые удаленные сообщения
                cursor = await db.execute(
                    "DELETE FROM messages_deleted WHERE timestamp < ?",
                    (cutoff_ts,)
                )
                messages_deleted = cursor.rowcount

                # Удаляем просроченные наказания
                cursor = await db.execute(
                    "DELETE FROM penalties_active WHERE until_date < ? AND until_date IS NOT NULL",
                    (now,)
                )
                penalties_deleted = cursor.rowcount

                await db.commit()
                
                if violations_deleted > 0 or messages_deleted > 0 or penalties_deleted > 0:
                    logger.info(
                        f"Удалено старых записей: "
                        f"нарушений - {violations_deleted}, "
                        f"сообщений - {messages_deleted}, "
                        f"наказаний - {penalties_deleted}"
                    )
                else:
                    logger.debug("Старых записей для удаления не найдено")
                    
        except Exception as e:
            logger.error(f"Ошибка при очистке старых записей: {str(e)}")
            
        # Ждем 24 часа перед следующей проверкой
        await asyncio.sleep(86400)

async def record_violation(user_id: int, user_name: str, group_id: int, violation_type: str, config: Config) -> None:
    """Записывает нарушение и обновляет incidents если нужно"""
    logger.debug(f"Запись нарушения: user_id={user_id}, type={violation_type}")
    
    now_ts = int(time.time())

    # Проверяем правило для данного типа нарушения
    rule = config.violation_rules.get(violation_type)
    if not rule or not rule.enabled:
        logger.debug(f"Правило {violation_type} отключено или не существует")
        return

    async def _record():
        conn = await get_db_connection()
        try:
            async with conn.cursor() as cursor:
                # Записываем нарушение в лог
                await cursor.execute(
                    """
                    INSERT INTO violations (user_id, chat_id, violation_type, message_text, timestamp)
                    VALUES (?,?,?,?,?)
                    """,
                    (user_id, group_id, violation_type, "", now_ts)
                )

                # Увеличиваем счетчик конкретного типа нарушения
                await cursor.execute(
                    """
                    INSERT INTO violation_counters (user_id, violation_type, count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(user_id, violation_type) DO UPDATE
                    SET count = count + 1
                    RETURNING count
                    """,
                    (user_id, violation_type)
                )
                
                row = await cursor.fetchone()
                current_count = row[0] if row else 1

                # Если достигли порога для этого типа нарушения и оно считается как violation
                if (rule.count_as_violation and 
                    current_count >= rule.violations_before_penalty):
                    
                    # Сбрасываем счетчик этого типа нарушения
                    await cursor.execute(
                        """
                        UPDATE violation_counters
                        SET count = 0
                        WHERE user_id=? AND violation_type=?
                        """,
                        (user_id, violation_type)
                    )
                    
                    # Обновляем общий счетчик инцидентов атомарно
                    await cursor.execute(
                        """
                        INSERT INTO users_incidents (user_id, incident_count, last_incident_ts)
                        VALUES (?, 1, ?)
                        ON CONFLICT(user_id) DO UPDATE
                        SET incident_count = incident_count + 1,
                            last_incident_ts = ?
                        """,
                        (user_id, now_ts, now_ts)
                    )

            await conn.commit()
            logger.info(f"Нарушение записано: user_id={user_id}, type={violation_type}, count={current_count}")
        finally:
            await release_connection(conn)

    await retry_on_locked(_record)

async def record_deleted_message(user_id: int, user_name: str, group_id: int, message_text: str) -> int:
    """Записывает удаленное сообщение"""
    logger.debug(f"Запись удаленного сообщения: user_id={user_id}")
    
    now_ts = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO messages_deleted (user_id, user_name, group_id, message_text, timestamp)
            VALUES (?,?,?,?,?)
            """,
            (user_id, user_name, group_id, message_text, now_ts)
        )
        deleted_msg_id = cursor.lastrowid
        await db.commit()
        
        logger.info(f"Записано удаленное сообщение с ID {deleted_msg_id}")
        return deleted_msg_id

async def get_incidents_count(user_id: int) -> int:
    """Возвращает текущее число инцидентов для пользователя"""
    logger.debug(f"Получение количества инцидентов: user_id={user_id}")
    
    conn = await get_db_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT incident_count FROM users_incidents WHERE user_id=?",
                (user_id,)
            )
            row = await cursor.fetchone()
            count = row[0] if row else 0
            
            logger.debug(f"Количество инцидентов для user_id={user_id}: {count}")
            return count
    finally:
        await release_connection(conn)

# Функции для работы с наказаниями
async def set_penalty(user_id: int, user_name: str, penalty_type: str, until_date: Optional[int]) -> None:
    """Устанавливает наказание для пользователя"""
    logger.debug(f"Установка наказания: user_id={user_id}, type={penalty_type}")
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO penalties_active (user_id, user_name, penalty_type, until_date)
            VALUES (?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE
            SET user_name=excluded.user_name,
                penalty_type=excluded.penalty_type,
                until_date=excluded.until_date
            """,
            (user_id, user_name, penalty_type, until_date)
        )
        await db.commit()
        
    logger.info(f"Установлено наказание {penalty_type} для user_id={user_id}")

async def get_penalty(user_id: int) -> Optional[str]:
    """Получает текущее наказание пользователя"""
    logger.debug(f"Получение наказания: user_id={user_id}")
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT penalty_type, until_date FROM penalties_active WHERE user_id=?",
            (user_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        
    if row:
        ptype, until = row
        logger.debug(f"Найдено наказание {ptype} для user_id={user_id}")
        return ptype
        
    logger.debug(f"Наказаний не найдено для user_id={user_id}")
    return None

async def revoke_penalty(user_id: int) -> None:
    """Отменяет наказание пользователя"""
    logger.debug(f"Отмена наказания: user_id={user_id}")
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM penalties_active WHERE user_id=?",
            (user_id,)
        )
        await db.commit()
        
    logger.info(f"Наказание отменено для user_id={user_id}")

async def reset_violation_counters(user_id: int) -> None:
    """Сбрасывает все счетчики нарушений для пользователя"""
    logger.debug(f"Сброс счетчиков нарушений: user_id={user_id}")
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM violation_counters WHERE user_id=?",
            (user_id,)
        )
        await db.commit()
        
    logger.info(f"Счетчики нарушений сброшены для user_id={user_id}")

async def reset_all_user_data(user_id: int) -> None:
    """Полностью сбрасывает все данные о нарушениях пользователя"""
    logger.debug(f"Полный сброс данных пользователя: user_id={user_id}")
    
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
            "DELETE FROM violations WHERE user_id=?",
            (user_id,)
        )
        await db.commit()
        
    logger.info(f"Все данные пользователя user_id={user_id} сброшены")

async def get_deleted_message_by_id(message_id: int) -> Optional[tuple]:
    """Получает информацию об удаленном сообщении по его ID"""
    logger.debug(f"Получение удаленного сообщения: message_id={message_id}")
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, user_id, user_name, group_id, message_text, timestamp
            FROM messages_deleted
            WHERE id = ?
            """,
            (message_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        
        if row:
            logger.debug(f"Найдено удаленное сообщение с ID {message_id}")
        else:
            logger.debug(f"Удаленное сообщение с ID {message_id} не найдено")
            
        return row 