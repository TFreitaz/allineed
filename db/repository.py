"""
Funções de acesso a dados para usuários e mensagens (schema criado em
db/migrations/0001_create_users_and_messages.sql).
"""

import logging
from datetime import datetime, timezone
from typing import Tuple

from db.connection import get_connection

logger = logging.getLogger("telegram-echo-bot.db.repository")


def save_message(from_user: dict, message: dict, chat_id: int, text: str) -> Tuple[int, int]:
    """
    Garante o usuário na tabela `users` (cria se não existir, atualiza dados
    básicos se já existir) e insere a mensagem em `messages`, relacionada a ele.

    Retorna (user_id, message_id) — os dois ids internos (não os do Telegram),
    gerados pelo próprio banco. São esses valores que devem ser repassados
    para qualquer processamento posterior da mensagem (ex: MsgReader/NFC-e).
    """
    telegram_id = from_user.get("id")
    username = from_user.get("username")
    first_name = from_user.get("first_name")
    last_name = from_user.get("last_name")
    language_code = from_user.get("language_code")
    is_bot = from_user.get("is_bot", False)

    telegram_message_id = message.get("message_id")
    sent_at = None
    if "date" in message:
        sent_at = datetime.fromtimestamp(message["date"], tz=timezone.utc)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (telegram_id, username, first_name, last_name, language_code, is_bot)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (telegram_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    language_code = EXCLUDED.language_code,
                    is_bot = EXCLUDED.is_bot,
                    updated_at = now()
                RETURNING user_id
                """,
                (telegram_id, username, first_name, last_name, language_code, is_bot),
            )
            user_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO messages (user_id, telegram_message_id, chat_id, text, sent_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING message_id
                """,
                (user_id, telegram_message_id, chat_id, text, sent_at),
            )
            message_id = cur.fetchone()[0]

        conn.commit()

    return user_id, message_id