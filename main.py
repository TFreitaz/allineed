import os
import logging
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import httpx
import psycopg2
import psycopg2.pool
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telegram-echo-bot")

app = FastAPI()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
DATABASE_URL = os.environ.get("DATABASE_URL")

db_pool: Optional[psycopg2.pool.SimpleConnectionPool] = None


@app.on_event("startup")
def startup() -> None:
    global db_pool
    if DATABASE_URL:
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 5, DATABASE_URL)
        logger.info("Pool de conexão com o banco iniciado.")
    else:
        logger.warning("DATABASE_URL não definida — mensagens não serão salvas no banco.")


@app.on_event("shutdown")
def shutdown() -> None:
    if db_pool:
        db_pool.closeall()


@contextmanager
def get_db_connection():
    if not db_pool:
        raise RuntimeError("Pool de conexão com o banco não inicializado (DATABASE_URL ausente).")
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)


@app.get("/")
async def health():
    """Rota simples de health check (útil para o Render saber que o serviço subiu)."""
    return {"status": "ok"}


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """
    Recebe os updates enviados pelo Telegram via webhook.
    Salva o usuário e a mensagem no banco (se DATABASE_URL estiver configurada)
    e responde ecoando a mesma mensagem recebida.
    """
    update = await request.json()
    logger.info("Update recebido: %s", update)

    message = update.get("message")
    if not message or "text" not in message:
        # Ignora updates que não são mensagens de texto (fotos, stickers, etc.)
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message["text"]
    from_user = message.get("from", {})

    if db_pool:
        try:
            # save_message é bloqueante (psycopg2), então roda numa thread separada
            # pra não travar o event loop do FastAPI.
            user_id = await asyncio.to_thread(save_message, from_user, message, chat_id, text)
            logger.info("Mensagem salva. user_id=%s", user_id)
        except Exception:
            logger.exception("Falha ao salvar mensagem no banco.")

    await send_message(chat_id, text)

    return {"ok": True}


def save_message(from_user: dict, message: dict, chat_id: int, text: str) -> int:
    """
    Garante o usuário na tabela `users` (cria se não existir, atualiza dados
    básicos se já existir) e insere a mensagem em `messages`, relacionada a ele.
    Retorna o user_id interno (não o telegram_id).
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

    with get_db_connection() as conn:
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
                """,
                (user_id, telegram_message_id, chat_id, text, sent_at),
            )
        conn.commit()

    return user_id


async def send_message(chat_id: int, text: str) -> None:
    """Envia uma mensagem de texto para um chat específico via API do Telegram."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
        if response.status_code != 200:
            logger.error("Falha ao enviar mensagem: %s", response.text)