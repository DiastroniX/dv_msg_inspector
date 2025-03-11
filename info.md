# Бот-модератор для Telegram групп

## Описание
Бот следит за правилами общения в группе и автоматически применяет санкции к нарушителям. Основная задача - поддержание культуры общения через систему реплаев.

## Основные функции
- Контроль за использованием реплаев
- Предотвращение спама через повторные ответы
- Система предупреждений и наказаний
- Автоматическая очистка старых данных
- Уведомления администраторов о нарушениях
- Панель управления для администраторов

## Настройка бота (config.json)

### Основные параметры
- `bot_token` - Токен бота Telegram
- `allowed_groups` - Список ID групп, где бот может работать
- `admin_ids` - Список ID администраторов
- `admin_chat_id` - ID чата для админ-уведомлений

### Правила сообщений
- `message_length_limit` - Максимальная длина сообщения (в символах) для проверки правил
- `reply_cooldown_seconds` - Временное окно (в секундах) для проверки повторных реплаев
- `ignore_bot_thread_replies` - Игнорировать ли ответы на сообщения бота в тредах

### Правила нарушений
Для каждого типа нарушения (`no_reply`, `double_reply`, `self_reply`):
```json
{
    "enabled": true,           // Включено ли правило
    "count_as_violation": true, // Считать ли как нарушение
    "violations_before_penalty": 1 // Сколько нарушений до наказания
}
```

### Наказания и санкции
- `penalties` - Соответствие количества нарушений и типа наказания:
  - `"warning"` - Предупреждение
  - `"read-only"` - Временный мут
  - `"kick"` - Исключение из группы
  - `"kick+ban"` - Временный бан
  - `"ban"` - Перманентный бан

### Длительности наказаний
- `mute_duration_seconds` - Длительность мута в секундах
- `temp_ban_duration_seconds` - Длительность временного бана в секундах

### Уведомления
- `notifications` - Настройки уведомлений о наказаниях:
  ```json
  {
    "new_violation": true,    // О новом нарушении
    "mute_applied": true,     // О муте
    "kick_applied": true,     // Об исключении
    "ban_applied": true       // О бане
  }
  ```

### Управление сообщениями бота
- `delete_bot_messages` - Удалять ли сообщения бота в группе
- `bot_message_lifetime_seconds` - Через сколько секунд удалять сообщения бота
- `delete_penalty_messages` - Удалять ли сообщения о наказаниях
- `penalty_message_lifetime_seconds` - Через сколько секунд удалять сообщения о наказаниях

### Хранение данных
- `data_retention_days` - Сколько дней хранить историю нарушений

### Логирование
- `logging.enabled` - Включить/выключить логирование
- `logging.level` - Уровень логирования (INFO/DEBUG/ERROR)
- `logging.modules` - Настройки логирования по модулям:
  ```json
  {
    "bot": true,        // Основной модуль бота
    "handlers": true,   // Обработчики сообщений
    "database": true,   // Операции с БД
    "admin": true       // Админ-функции
  }
  ```
- `logging.message_deletion` - Логировать удаление сообщений
- `logging.violations` - Логировать нарушения
- `logging.penalties` - Логировать наказания
- `logging.config` - Логировать изменения конфигурации

## Примеры конфигурации

### Базовая настройка
```json
{
  "message_length_limit": 500,
  "reply_cooldown_seconds": 10,
  "mute_duration_seconds": 3600,
  "temp_ban_duration_seconds": 86400,
  "data_retention_days": 360,
  "delete_bot_messages": true,
  "bot_message_lifetime_seconds": 30,
  "delete_penalty_messages": false,
  "penalty_message_lifetime_seconds": 300
}
```

### Строгие правила
```json
{
  "message_length_limit": 300,
  "reply_cooldown_seconds": 30,
  "mute_duration_seconds": 7200,
  "temp_ban_duration_seconds": 172800,
  "data_retention_days": 720,
  "delete_bot_messages": true,
  "bot_message_lifetime_seconds": 15,
  "delete_penalty_messages": true,
  "penalty_message_lifetime_seconds": 60
}
```

## База данных

### Таблицы

#### violations
- Хранит информацию о нарушениях
- Автоматическая очистка через триггер (30 дней)
- Индексы по user_id и timestamp

#### messages_deleted
- Хранит удаленные сообщения
- Автоматическая очистка через триггер (30 дней)
- Индексы по user_id и timestamp

#### penalties_active
- Активные наказания пользователей
- Автоматическая очистка просроченных наказаний
- Индекс по until_date

#### violation_counters
- Счетчики нарушений по типам
- Составной первичный ключ (user_id, violation_type)

#### users_incidents
- Общие счетчики инцидентов пользователей
- Индекс по last_incident_ts 