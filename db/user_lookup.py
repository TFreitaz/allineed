"""
Consulta o user_id interno (users.user_id) a partir do telegram_id — é o
ID que os demais módulos (purchase_history, etc.) esperam receber.

Usa o pool de conexões definido em db/connection.py.
"""

import logging
from typing import Optional

import psycopg2.extras

from db.connection import get_connection

logger = logging.getLogger("telegram-echo-bot.db.user_lookup")

_QUERY = """
    SELECT user_id
    FROM users
    WHERE telegram_id = %(telegram_id)s;
"""


def get_user_id_by_telegram_id(telegram_id: int) -> Optional[int]:
    """Retorna o user_id correspondente ao telegram_id informado, ou None
    se o usuário ainda não estiver cadastrado em `users`.
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_QUERY, {"telegram_id": telegram_id})
            row = cur.fetchone()

    if row is None:
        logger.info("Nenhum usuário encontrado para telegram_id=%s.", telegram_id)
        return None

    return row["user_id"]
