import json
from dataclasses import dataclass
from typing import Dict, List


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
    admin_chat_id: int

    # Параметры проверки сообщений
    message_length_limit: int  # Максимальная длина сообщения для проверки правил
    reply_cooldown_seconds: int  # Временное окно для проверки повторных реплаев
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

    # Настройки хранения данных
    data_retention_days: int  # Сколько дней хранить историю нарушений

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

        return Config(
            bot_token=data["bot_token"],
            allowed_groups=data["allowed_groups"],
            admin_ids=data["admin_ids"],
            admin_chat_id=data["admin_chat_id"],

            message_length_limit=data.get("long_message_threshold", 500),
            reply_cooldown_seconds=data.get("reply_rules_time_window", 10),
            ignore_bot_thread_replies=data.get("ignore_bot_replies_in_thread", True),

            violation_rules=violation_rules,

            penalties=data["penalties"],
            notifications=data["notifications"],
            mute_duration_seconds=data.get("read_only_duration", 3600),
            temp_ban_duration_seconds=data.get("kick_ban_duration", 86400),

            delete_bot_messages=data.get("bot_deletes_own_messages_in_group", False),
            bot_message_lifetime_seconds=data.get("delete_own_messages_after_secs", 0),
            
            data_retention_days=data.get("data_retention_days", 360)  # По умолчанию 360 дней
        )