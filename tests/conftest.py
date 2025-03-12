"""
Конфигурация для pytest
"""
import pytest
import pytest_asyncio
import shutil
import os
from pathlib import Path

# Настраиваем асинхронный режим
pytest_plugins = ('pytest_asyncio',)

@pytest.fixture(scope="session")
def event_loop():
    """Создает event loop для всей сессии тестирования"""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

def pytest_sessionfinish(session, exitstatus):
    """Очистка после завершения всех тестов"""
    # Удаляем тестовую базу данных если она осталась
    if os.path.exists("test.db"):
        os.remove("test.db")
        
    # Удаляем файл с покрытием кода
    if os.path.exists(".coverage"):
        os.remove(".coverage")
        
    # Удаляем только локальные директории с кэшем
    cache_dirs = [
        "tests/__pycache__",
        "__pycache__",
        ".pytest_cache"
    ]
    
    for cache_dir in cache_dirs:
        if os.path.exists(cache_dir) and not cache_dir.startswith(".venv"):
            shutil.rmtree(cache_dir)

    # Получаем корневую директорию проекта
    root_dir = Path(__file__).parent.parent
    
    # Очищаем кэши во всех поддиректориях
    for cache_dir in cache_dirs:
        # Ищем все директории с таким именем
        for path in root_dir.rglob(cache_dir):
            if path.is_dir():
                shutil.rmtree(path)
                print(f"Удалена директория: {path}")
    
    # Удаляем .pyc файлы
    for pyc_file in root_dir.rglob("*.pyc"):
        os.remove(pyc_file)
        print(f"Удален файл: {pyc_file}") 