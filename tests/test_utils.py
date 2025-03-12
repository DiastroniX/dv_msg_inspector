"""
Тесты базовых утилитарных функций
"""
import pytest
from datetime import datetime, timedelta
import pytz

def test_time_format():
    """Тест форматирования времени"""
    moscow_tz = pytz.timezone('Europe/Moscow')
    time = moscow_tz.localize(datetime(2024, 3, 15, 12, 30))
    
    # Проверяем базовое форматирование
    assert time.strftime("%Y-%m-%d %H:%M") == "2024-03-15 12:30"
    
    # Проверяем временную зону
    assert time.tzname() == "MSK"

def test_time_difference():
    """Тест расчета разницы во времени"""
    time1 = datetime(2024, 3, 15, 12, 0)
    time2 = datetime(2024, 3, 15, 12, 30)
    
    diff = time2 - time1
    assert diff == timedelta(minutes=30)

def test_message_length():
    """Тест проверки длины сообщения"""
    short_msg = "Короткое сообщение"
    long_msg = "А" * 4096  # Максимальная длина сообщения в Telegram
    
    assert len(short_msg) < 4096
    assert len(long_msg) == 4096 