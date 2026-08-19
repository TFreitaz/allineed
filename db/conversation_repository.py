from typing import Optional, Dict, Any

from db.connection import get_connection


def create_pending(
    user_id: int,
    state: str,
    reference_message_id: Optional[int] = None,
    data: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Cria uma nova conversa pendente.

    Retorna o conversation_id criado.
    """
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO conversations (
                    user_id,
                    state,
                    status,
                    reference_message_id,
                    data
                )
                VALUES (%s, %s, 'active', %s, %s)
                RETURNING conversation_id
                """,
                (
                    user_id,
                    state,
                    reference_message_id,
                    data or {},
                ),
            )

            conversation_id = cursor.fetchone()[0]
            conn.commit()

            return conversation_id

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def get_latest_pending(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Retorna a conversa pendente mais recente do usuário.

    Retorna None caso não exista uma conversa pendente.
    """
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    conversation_id,
                    user_id,
                    state,
                    reference_message_id,
                    data,
                    created_at,
                    updated_at
                FROM conversations
                WHERE user_id = %s
                  AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            )

            row = cursor.fetchone()

            if row is None:
                return None

            return {
                "conversation_id": row[0],
                "user_id": row[1],
                "state": row[2],
                "reference_message_id": row[3],
                "data": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }

    finally:
        conn.close()


def finish_latest_pending(user_id: int) -> Optional[int]:
    """
    Finaliza a conversa pendente mais recente do usuário.

    Retorna o conversation_id finalizado ou None caso
    não exista uma conversa pendente.
    """
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE conversations
                SET
                    status = 'finished',
                    finished_at = now(),
                    updated_at = now()
                WHERE conversation_id = (
                    SELECT conversation_id
                    FROM conversations
                    WHERE user_id = %s
                      AND status = 'active'
                    ORDER BY created_at DESC
                    LIMIT 1
                )
                RETURNING conversation_id
                """,
                (user_id,),
            )

            row = cursor.fetchone()
            conn.commit()

            return row[0] if row else None

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()