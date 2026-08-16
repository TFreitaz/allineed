import os
import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import httpx
import psycopg2
import psycopg2.pool
from fastapi import FastAPI, Request

from msg_reader import MsgReader
from db.repository import save_message
from db.connection import init_pool, close_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telegram-echo-bot")

app = FastAPI()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
DATABASE_URL = os.environ.get("DATABASE_URL")

db_pool: Optional[psycopg2.pool.SimpleConnectionPool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    logger.info("Pool de conexão com o banco iniciado.")

    yield

    close_pool()
    logger.info("Pool de conexão com o banco encerrado.")


app = FastAPI(lifespan=lifespan)


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
    if not message:
        # Ignora updates que não são mensagens de texto (fotos, stickers, etc.)
        return {"ok": True}

    chat_id = message["chat"]["id"]
    if "text" in message:
        input_text = message["text"]
    else:
        input_text = ""
    from_user = message.get("from", {})

    user_id, message_id = await asyncio.to_thread(save_message, from_user, message, chat_id, input_text)
    logger.info("Mensagem salva. user_id=%s, message_id=%s", user_id, message_id)

    msg_reader = MsgReader(message, user_id=user_id, message_id=message_id)
    response_text = await asyncio.to_thread(msg_reader.get_answer)

    await send_message(chat_id, response_text)

    return {"ok": True}

async def send_message(chat_id: int, text: str) -> None:
    """Envia uma mensagem de texto para um chat específico via API do Telegram."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )
        if response.status_code != 200:
            logger.error("Falha ao enviar mensagem: %s", response.text)
