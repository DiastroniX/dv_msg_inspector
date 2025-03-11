# Бот-модератор для Telegram чатов

Бот для модерации Telegram чатов с функциями:
- Контроль спама и флуда
- Система предупреждений и наказаний
- Автоматическая очистка старых данных
- Панель администратора

## Установка

1. Клонируйте репозиторий
```bash
git clone [url репозитория]
cd [папка проекта]
```

2. Создайте виртуальное окружение и установите зависимости
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
# или
venv\Scripts\activate  # для Windows
pip install -r requirements.txt
```

3. Настройка конфигурации
```bash
cp config.example.json config.json
```
Отредактируйте `config.json`:
- Укажите токен бота (`bot_token`)
- Добавьте ID разрешенных групп (`allowed_groups`)
- Укажите ID администраторов (`admin_ids`)
- Настройте ID чата для админ-уведомлений (`admin_chat_id`)

## Запуск

```bash
python main.py
```

## Конфигурация

Основные параметры в `config.json`:

- `message_length_limit`: Максимальная длина сообщения для проверки правил
- `reply_cooldown_seconds`: Временное окно для проверки повторных реплаев
- `mute_duration_seconds`: Длительность мута в секундах
- `temp_ban_duration_seconds`: Длительность временного бана в секундах
- `data_retention_days`: Срок хранения данных в днях

Полное описание параметров смотрите в `config.example.json` 