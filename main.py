import asyncio
import logging

from aiogram.client.bot import Bot, DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram import Dispatcher

from config import Config
from database import init_db, start_cleanup_task
from handlers.callbacks import callbacks_router
from handlers.message_handlers import message_router, init_message_handler


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    logger = logging.getLogger(__name__)

    # 1. Загружаем конфиг
    logger.info("Loading config...")
    config = Config.from_json_file("config.json")
    logger.info("Config loaded successfully")

    # 2. Инициализируем БД
    logger.info("Initializing database...")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # 3. Создаём Bot и Dispatcher
    logger.info("Creating bot and dispatcher...")
    bot = Bot(
        token=config.bot_token,
        session=AiohttpSession(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # 4. Регистрируем роутеры
    dp.include_router(callbacks_router)
    dp.include_router(message_router)

    # 5. Миддлварь для проброса config во все хендлеры
    @dp.update.outer_middleware()
    async def config_middleware(handler, event, data):
        data["config"] = config
        return await handler(event, data)

    # 6. Инициализируем обработчик сообщений
    logger.info("Initializing message handler...")
    await init_message_handler()

    # 7. Запускаем задачу очистки старых данных
    logger.info(f"Starting cleanup task (retention period: {config.data_retention_days} days)...")
    cleanup_task = asyncio.create_task(start_cleanup_task(config))

    # 8. Запуск бота
    try:
        await dp.start_polling(bot)
    finally:
        cleanup_task.cancel()  # Отменяем задачу очистки при завершении
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())