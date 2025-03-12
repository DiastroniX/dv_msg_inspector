TEXTS = {
    "no_reply": (
        "⚠️ {name}, вы отправили второе подряд сообщение без реплая. "
        "Пожалуйста, если хотите продолжить разговор, используйте реплай на чужое сообщение или отредактируйте старое сообщение."
    ),
    "double_reply": (
        "⚠️ {name}, вы дважды подряд ответили на одно и то же сообщение. "
        "Если хотите продолжить обсуждение, объедините мысли и отредактируйте первое сообщение."
    ),
    "self_reply": (
        "⚠️ {name}, вы слишком быстро ответили на своё же предыдущее сообщение (менее {minutes} мин.). "
        "Вместо этого отредактируйте старое сообщение или сделайте паузу."
    ),
    "mute_applied": (
        "🔇 {name}, за нарушение правил в количестве <b>{violations_count}</b> вы замьючены (read-only) на <b>{minutes}</b> мин. "
        "и сможете снова писать {datetime}. "
        "Пожалуйста, не нарушайте правила."
    ),
    "kick_applied": (
        "🚫 {name}, из-за серии нарушений <b>{violations_count}</b> вы исключены из группы. "
        "Вы можете присоединиться обратно позднее, но просим соблюдать правила."
    ),
    "kick_ban_applied": (
        "⛔️ {name}, из-за серии нарушений <b>{violations_count}</b> вы исключены из группы на <b>{minutes}</b> мин. (до {date_str}). "
        "Пожалуйста, учтите это и соблюдайте правила после возвращения."
    ),
    "ban_applied": (
        "🚷 {name}, из-за многократных нарушений <b>{violations_count}</b> вы заблокированы в группе навсегда. "
        "Разблокировка возможна только после обсуждения с администрацией."
    ),
    "official_warning": (
        "❗️ {name}, это официальное предупреждение за нарушения.\n\n"
        "📊 У вас уже накоплено нарушений: <b>{current_violations}</b>\n"
        "⚠️ До следующего наказания (<b>{next_penalty_description}</b>) осталось нарушений: <b>{violations_until_next}</b>\n\n"
        "Пожалуйста, внимательно изучите правила и следуйте им, "
        "чтобы избежать более серьёзных санкций."
    ),
    "message_restored": (
        "🔄 <i>Восстановлено администратором</i>\n\n"
        "👤 <b>Пользователь</b>: {user_name}\n\n"
        "💬 <b>Текст сообщения</b>: <blockquote>{message_text}</blockquote>\n\n"
        "🕒 <b>Время публикации (МСК)</b>: {formatted_date}"
    )
}