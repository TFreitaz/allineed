import os
import logging

import httpx
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telegram-echo-bot")

app = FastAPI()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


@app.get("/")
async def health():
    """Rota simples de health check (útil para o Render saber que o serviço subiu)."""
    return {"status": "ok"}


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """
    Recebe os updates enviados pelo Telegram via webhook.
    Regra atual: eco -> responde ao usuário com a mesma mensagem que ele enviou.
    """
    update = await request.json()
    logger.info("Update recebido: %s", update)

    message = update.get("message")
    if not message or "text" not in message:
        # Ignora updates que não são mensagens de texto (fotos, stickers, etc.)
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message["text"]

    await send_message(chat_id, text)

    return {"ok": True}


async def send_message(chat_id: int, text: str) -> None:
    """Envia uma mensagem de texto para um chat específico via API do Telegram."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
        if response.status_code != 200:
            logger.error("Falha ao enviar mensagem: %s", response.text)
