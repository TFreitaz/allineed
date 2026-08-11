"""
Script auxiliar para registrar (ou remover) o webhook do bot no Telegram.

Uso:
    python set_webhook.py set https://seu-bot.onrender.com/webhook
    python set_webhook.py delete
    python set_webhook.py info
"""

import os
import sys

import httpx

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def set_webhook(url: str) -> None:
    response = httpx.post(f"{TELEGRAM_API_URL}/setWebhook", json={"url": url})
    print(response.json())


def delete_webhook() -> None:
    response = httpx.post(f"{TELEGRAM_API_URL}/deleteWebhook")
    print(response.json())


def get_webhook_info() -> None:
    response = httpx.get(f"{TELEGRAM_API_URL}/getWebhookInfo")
    print(response.json())


if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        print("Erro: defina a variável de ambiente TELEGRAM_BOT_TOKEN antes de rodar.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Uso: python set_webhook.py [set <url> | delete | info]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "set":
        if len(sys.argv) < 3:
            print("Informe a URL do webhook. Ex: python set_webhook.py set https://seu-bot.onrender.com/webhook")
            sys.exit(1)
        set_webhook(sys.argv[2])
    elif command == "delete":
        delete_webhook()
    elif command == "info":
        get_webhook_info()
    else:
        print(f"Comando desconhecido: {command}")
