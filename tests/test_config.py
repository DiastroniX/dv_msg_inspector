import pytest
from config import Config
import json

def test_config_from_dict(test_config):
    """Тест создания конфигурации из словаря"""
    assert test_config.bot_token == "test_token"
    assert test_config.allowed_groups == [-1001234567890]
    assert test_config.admin_ids == [123456789]
    assert test_config.admin_chat_id == "-1001234567890_1"
    assert test_config.message_length_limit == 500
    assert test_config.check_reply_cooldown is True
    assert test_config.reply_cooldown_seconds == 3600

def test_config_validation():
    """Тест валидации конфигурации"""
    invalid_config = {
        "bot_token": "",  # Пустой токен
        "allowed_groups": [],  # Пустой список групп
        "admin_ids": [],  # Пустой список админов
        "admin_chat_id": "",  # Пустой ID админ чата
    }
    
    with pytest.raises(ValueError):
        Config.from_dict(invalid_config)

def test_config_penalties_order(test_config):
    """Тест правильности порядка наказаний"""
    penalties = test_config.penalties
    thresholds = sorted([int(k) for k in penalties.keys()])
    
    # Проверяем, что пороги идут по возрастанию
    assert thresholds == [1, 3, 5, 7, 10]
    
    # Проверяем последовательность наказаний
    expected_sequence = ["warning", "read-only", "kick", "kick+ban", "ban"]
    actual_sequence = [penalties[str(t)] for t in thresholds]
    assert actual_sequence == expected_sequence

def test_config_violation_rules(test_config):
    """Тест правил нарушений"""
    rules = test_config.violation_rules
    
    # Проверяем наличие всех типов правил
    assert "no_reply" in rules
    assert "double_reply" in rules
    assert "self_reply" in rules
    
    # Проверяем структуру правил
    for rule_type in ["no_reply", "double_reply", "self_reply"]:
        rule = rules[rule_type]
        assert hasattr(rule, "enabled")
        assert hasattr(rule, "count_as_violation")
        assert hasattr(rule, "violations_before_penalty") 