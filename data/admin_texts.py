"""
Тексты для административных уведомлений и описания нарушений/наказаний
"""

VIOLATION_DESCRIPTIONS = {
    "no_reply": "Отправка сообщения без реплая",
    "double_reply": "Двойной реплай на одно сообщение",
    "self_reply": "Ответ на своё сообщение"
}

def get_penalty_descriptions(config):
    """
    Возвращает словарь с описаниями наказаний, используя значения из конфига
    """
    return {
        "warning": "Предупреждение",
        "read-only": f"Временный мут ({config.mute_duration_seconds // 60} мин)",
        "kick": "Исключение из группы",
        "kick+ban": f"Временный бан ({config.temp_ban_duration_seconds // 60} мин)",
        "ban": "Перманентный бан"
    }

ADMIN_NOTIFICATION = """<b>Нарушение!</b>
<b>Пользователь</b>: {user_name}
<b>ID</b>: {user_id}
<b>Нарушение №</b>: {penalty_count}
<b>Тип нарушения</b>: {violation_desc} ({violation_type})
<b>Применено наказание</b>: {penalty_desc} ({penalty_to_apply})
<b>Текст сообщения</b>:<blockquote>{msg_text}</blockquote>"""

ADMIN_VIOLATION_WARNING = """⚠️ <b>Нарушение правил администратором!</b>

<b>Нарушитель</b>: {user_name}
<b>Тип нарушения</b>: {violation_desc}

❗️ Обратите внимание:
- Как администратор, вы имеете иммунитет от автоматических санкций
- Однако ваши действия видны другим администраторам
- Просим соблюдать правила чата, подавая пример участникам

<b>Сообщение с нарушением</b>:<blockquote>{msg_text}</blockquote>"""