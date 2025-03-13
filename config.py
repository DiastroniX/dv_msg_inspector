import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Any


@dataclass
class LoggingModules:
    bot: bool
    handlers: bool
    database: bool
    admin: bool


@dataclass
class LoggingConfig:
    enabled: bool
    level: str
    modules: LoggingModules
    message_deletion: bool
    violations: bool
    penalties: bool
    config: bool


@dataclass
class ViolationRule:
    enabled: bool  # Включено ли правило
    count_as_violation: bool  # Считать ли как нарушение
    violations_before_penalty: int  # Сколько раз нужно нарушить до penalties


@dataclass
class Config:
    # Основные параметры бота
    bot_token: str
    allowed_groups: List[int]
    admin_ids: List[int]
    admin_chat_id: str

    # Параметры проверки сообщений
    message_length_limit: int  # Максимальная длина сообщения для проверки правил
    check_reply_cooldown: bool  # Включить/выключить проверку временного интервала
    reply_cooldown_seconds: Optional[int]  # Временное окно для проверки повторных реплаев
    warn_admins: bool  # Предупреждать ли администраторов о нарушениях без наказаний
    ignore_bot_thread_replies: bool  # Игнорировать ли реплаи на сообщения бота в тредах

    # Правила нарушений
    violation_rules: Dict[str, ViolationRule]

    # Наказания
    penalties: Dict[str, str]  # "1":"warning","2":"read-only","3":"kick","4":"kick+ban","5":"ban"
    notifications: Dict[str, bool]  # Уведомления о наказаниях
    mute_duration_seconds: int  # Длительность мута в секундах
    temp_ban_duration_seconds: int  # Длительность временного бана в секундах

    # Настройки сообщений бота
    delete_bot_messages: bool  # Удалять ли сообщения бота в группе
    bot_message_lifetime_seconds: int  # Через сколько секунд удалять сообщения бота
    delete_penalty_messages: bool  # Удалять ли сообщения о наказаниях
    penalty_message_lifetime_seconds: int  # Через сколько секунд удалять сообщения о наказаниях
    bot_message_delay_seconds: int  # Задержка перед отправкой сообщений бота

    # Настройки хранения данных
    data_retention_days: int  # Сколько дней хранить историю нарушений

    # Настройки логирования
    logging: LoggingConfig

    def __init__(self, data: Dict[str, Any]):
        self.bot_token = data["bot_token"]
        self.allowed_groups = data["allowed_groups"]
        self.admin_ids = data["admin_ids"]
        self.admin_chat_id = str(data["admin_chat_id"])  # Храним как строку для поддержки составного ID

        # Остальные параметры инициализируем через метод from_json_file

    @staticmethod
    def from_json_file(path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Преобразуем правила нарушений в объекты ViolationRule
        violation_rules = {}
        for rule_type, rule_data in data.get("violation_rules", {}).items():
            violation_rules[rule_type] = ViolationRule(
                enabled=rule_data.get("enabled", True),
                count_as_violation=rule_data.get("count_as_violation", True),
                violations_before_penalty=rule_data.get("violations_before_penalty", 1)
            )

        # Если правила не заданы, используем значения по умолчанию
        if not violation_rules:
            violation_rules = {
                "no_reply": ViolationRule(enabled=True, count_as_violation=True, violations_before_penalty=1),
                "double_reply": ViolationRule(enabled=True, count_as_violation=True, violations_before_penalty=1),
                "self_reply": ViolationRule(enabled=True, count_as_violation=True, violations_before_penalty=1)
            }

        # Настройки логирования
        logging_data = data.get("logging", {})
        modules_data = logging_data.get("modules", {})
        logging_config = LoggingConfig(
            enabled=logging_data.get("enabled", True),
            level=logging_data.get("level", "INFO"),
            modules=LoggingModules(
                bot=modules_data.get("bot", True),
                handlers=modules_data.get("handlers", True),
                database=modules_data.get("database", True),
                admin=modules_data.get("admin", True)
            ),
            message_deletion=logging_data.get("message_deletion", True),
            violations=logging_data.get("violations", True),
            penalties=logging_data.get("penalties", True),
            config=logging_data.get("config", True)
        )

        return Config(
            bot_token=data["bot_token"],
            allowed_groups=data["allowed_groups"],
            admin_ids=data["admin_ids"],
            admin_chat_id=str(data["admin_chat_id"]),

            message_length_limit=data.get("message_length_limit", 500),
            check_reply_cooldown=data.get("check_reply_cooldown", True),
            reply_cooldown_seconds=data.get("reply_cooldown_seconds", 3600),
            warn_admins=data.get("warn_admins", True),
            ignore_bot_thread_replies=data.get("ignore_bot_thread_replies", True),

            violation_rules=violation_rules,

            penalties=data["penalties"],
            notifications=data["notifications"],
            mute_duration_seconds=data.get("mute_duration_seconds", 3600),
            temp_ban_duration_seconds=data.get("temp_ban_duration_seconds", 86400),

            delete_bot_messages=data.get("delete_bot_messages", False),
            bot_message_lifetime_seconds=data.get("bot_message_lifetime_seconds", 0),
            delete_penalty_messages=data.get("delete_penalty_messages", False),
            penalty_message_lifetime_seconds=data.get("penalty_message_lifetime_seconds", 300),
            bot_message_delay_seconds=data.get("bot_message_delay_seconds", 2),
            
            data_retention_days=data.get("data_retention_days", 360),
            
            logging=logging_config
        )