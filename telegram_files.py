"""
telegram_files.py

Funções auxiliares para baixar arquivos (fotos, documentos etc.) enviados
por um usuário do Telegram, a partir do `file_id` presente no update.
"""

import os
import httpx
import logging

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
TELEGRAM_FILE_BASE = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telegram-echo-bot")

def extract_document_file_id(message: dict) -> str | None:
    """
    Extracts the file_id from a Telegram document message.

    Returns None if the message does not contain a document.
    """
    logger.info("Finding document file ID.")

    document = message.get("document")

    if not document:
        logger.info("There is no value for 'document' field in message.")
        return None

    file_id = document.get("file_id")

    if not file_id:
        logger.info("Document does not contain a file_id.")
        return None

    logger.info("Found document.")
    return file_id


async def download_document(message: dict) -> bytes | None:
    """
    Downloads a document sent by the user and returns its raw bytes.

    Returns None if the message does not contain a valid document.
    """
    logger.info("Downloading document.")

    file_id = extract_document_file_id(message)

    if file_id is None:
        return None

    return await baixar_arquivo_por_file_id(file_id)


def download_document_sync(message: dict) -> bytes | None:
    """
    Synchronous version of download_document.

    Used by MsgReader, which is synchronous by design and runs outside
    the main event loop.
    """
    logger.info("Downloading document synchronously.")

    file_id = extract_document_file_id(message)

    if file_id is None:
        return None

    return baixar_arquivo_por_file_id_sync(file_id)

async def baixar_arquivo_por_file_id(file_id: str) -> bytes:
    """
    Recebe um file_id do Telegram e retorna os bytes brutos do arquivo.

    Faz duas chamadas:
    1. getFile -> descobre o file_path real no servidor do Telegram.
    2. GET no endpoint de arquivos -> baixa o conteúdo binário.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{TELEGRAM_API_BASE}/getFile", params={"file_id": file_id})
        resp.raise_for_status()
        file_path = resp.json()["result"]["file_path"]

        resp_arquivo = await client.get(f"{TELEGRAM_FILE_BASE}/{file_path}")
        resp_arquivo.raise_for_status()
        return resp_arquivo.content


def baixar_arquivo_por_file_id_sync(file_id: str) -> bytes:
    """
    Versão síncrona de baixar_arquivo_por_file_id.

    Usada pelo MsgReader, que é síncrono por design (facilita os testes) e
    roda fora do event loop principal via asyncio.to_thread — chamado pelo
    webhook.
    """
    with httpx.Client() as client:
        resp = client.get(f"{TELEGRAM_API_BASE}/getFile", params={"file_id": file_id})
        resp.raise_for_status()
        file_path = resp.json()["result"]["file_path"]

        resp_arquivo = client.get(f"{TELEGRAM_FILE_BASE}/{file_path}")
        resp_arquivo.raise_for_status()
        return resp_arquivo.content


def extrair_file_id_da_maior_foto(message: dict) -> str | None:
    """
    Uma mensagem de foto do Telegram traz `message["photo"]` como uma lista
    de tamanhos (do menor pro maior). Pegamos o último (maior resolução).
    Retorna None se a mensagem não tiver foto.
    """
    logger.info("Finding the largest image's ID.")
    fotos = message.get("photo")
    if not fotos:
        logger.info("There are no value for 'photo' field in message.")
        return None
    logger.info("Found picture.")
    return fotos[-1]["file_id"]


async def baixar_maior_foto(message: dict) -> bytes | None:
    """Atalho assíncrono: extrai o file_id da maior foto e já baixa os bytes."""
    logger.info("Downloading the largest image.")
    file_id = extrair_file_id_da_maior_foto(message)
    if file_id is None:
        return None
    return await baixar_arquivo_por_file_id(file_id)


def baixar_maior_foto_sync(message: dict) -> bytes | None:
    """Atalho síncrono: extrai o file_id da maior foto e já baixa os bytes."""
    file_id = extrair_file_id_da_maior_foto(message)
    if file_id is None:
        return None
    return baixar_arquivo_por_file_id_sync(file_id)
