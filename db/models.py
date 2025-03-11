from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

@dataclass
class Violation:
    """Модель нарушения правил"""
    id: int
    user_id: int
    chat_id: int
    violation_type: str
    message_text: str
    context: Optional[str]  # хранится как строка в БД
    timestamp: int  # хранится как UNIX timestamp

@dataclass
class DeletedMessage:
    """Модель удаленного сообщения"""
    id: int
    user_id: int
    user_name: str
    group_id: int
    message_text: str
    timestamp: int  # хранится как UNIX timestamp

@dataclass
class ActivePenalty:
    """Модель активного наказания"""
    user_id: int  # PRIMARY KEY
    user_name: str
    penalty_type: str
    until_date: Optional[int]  # может быть NULL, хранится как UNIX timestamp

@dataclass
class ViolationCounter:
    """Модель счетчика нарушений"""
    user_id: int  # часть составного PRIMARY KEY
    violation_type: str  # часть составного PRIMARY KEY
    count: int  # NOT NULL DEFAULT 0

@dataclass
class UserIncidents:
    """Модель счетчика инцидентов пользователя"""
    user_id: int  # PRIMARY KEY
    incident_count: int  # NOT NULL DEFAULT 0
    last_incident_ts: int  # NOT NULL, хранится как UNIX timestamp 