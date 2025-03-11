import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from typing import Any, Callable, Dict, Awaitable
from aiogram.types import TelegramObject

from config import Config
from handlers.message_handlers import message_router, init_message_handler
from handlers.callbacks import callbacks_router
from db.operations import init_db, cleanup_old_violations

def setup_logging(config: Config):
    """Настраивает логирование на основе конфигурации"""
    if not config.logging.enabled:
        return

    # Настраиваем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(config.logging.level)

    # Создаем форматтер для логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Добавляем вывод в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Настраиваем уровни логирования для разных модулей
    if config.logging.modules.bot:
        logging.getLogger("bot").setLevel(config.logging.level)
    if config.logging.modules.handlers:
        logging.getLogger("handlers").setLevel(config.logging.level)
    if config.logging.modules.database:
        logging.getLogger("db").setLevel(config.logging.level)
    if config.logging.modules.admin:
        logging.getLogger("admin").setLevel(config.logging.level)

    logger = logging.getLogger(__name__)
    logger.info("Логирование настроено")

    # Логируем важные параметры конфигурации
    if config.logging.config:
        logger.info("Параметры конфигурации:")
        logger.info(f"delete_bot_messages: {config.delete_bot_messages}")
        logger.info(f"bot_message_lifetime_seconds: {config.bot_message_lifetime_seconds}")
        logger.info(f"delete_penalty_messages: {config.delete_penalty_messages}")
        logger.info(f"penalty_message_lifetime_seconds: {config.penalty_message_lifetime_seconds}")
        logger.info(f"message_length_limit: {config.message_length_limit}")
        logger.info(f"reply_cooldown_seconds: {config.reply_cooldown_seconds}")
        logger.info(f"mute_duration_seconds: {config.mute_duration_seconds}")
        logger.info(f"temp_ban_duration_seconds: {config.temp_ban_duration_seconds}")

# Добавляем middleware для конфигурации
class ConfigMiddleware:
    def __init__(self, config: Config):
        self.config = config

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        data["config"] = self.config
        return await handler(event, data)

async def main():
    # Загружаем конфигурацию
    config = Config.from_json_file("config.json")
    
    # Настраиваем логирование
    setup_logging(config)
    
    logger = logging.getLogger(__name__)
    logger.info("Запуск бота...")

    # Инициализируем базу данных
    await init_db()
    logger.info("База данных инициализирована")

    # Создаем бота и диспетчер с новыми настройками
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Добавляем middleware для конфигурации
    dp.update.outer_middleware(ConfigMiddleware(config))

    # Регистрируем обработчики
    dp.include_router(message_router)
    dp.include_router(callbacks_router)
    await init_message_handler()
    logger.info("Обработчики сообщений и callback-запросов зарегистрированы")

    # Запускаем задачу очистки старых нарушений
    asyncio.create_task(cleanup_old_violations(config))
    logger.info("Запущена задача очистки старых нарушений")

    try:
        # Запускаем поллинг
        logger.info("Запуск поллинга...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при работе бота: {str(e)}")
    finally:
        logger.info("Завершение работы бота")
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен пользователем")
    except Exception as e:
        logging.error(f"Критическая ошибка: {str(e)}")
        sys.exit(1)