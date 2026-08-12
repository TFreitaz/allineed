"""
Gerencia o pool de conexões com o banco (Neon/Postgres) usado pela aplicação.
Nenhuma query fica aqui — só a infraestrutura de conexão.
"""

import os
import logging
from contextlib import contextmanager
from typing import Optional

import psycopg2
import psycopg2.pool

logger = logging.getLogger("telegram-echo-bot.db")

DATABASE_URL = os.environ.get("DATABASE_URL")

_pool: Optional[psycopg2.pool.SimpleConnectionPool] = None


def init_pool() -> None:
    """Abre o pool de conexões. Chamar uma vez, no startup da aplicação."""
    global _pool
    if not DATABASE_URL:
        logger.warning("DATABASE_URL não definida — funcionalidades de banco ficarão desativadas.")
        return
    _pool = psycopg2.pool.SimpleConnectionPool(1, 5, DATABASE_URL)
    logger.info("Pool de conexão com o banco iniciado.")


def close_pool() -> None:
    """Fecha o pool de conexões. Chamar no shutdown da aplicação."""
    if _pool:
        _pool.closeall()


def is_available() -> bool:
    """Indica se o banco está configurado e o pool foi iniciado."""
    return _pool is not None


@contextmanager
def get_connection():
    """Empresta uma conexão do pool e devolve automaticamente ao final."""
    if not _pool:
        raise RuntimeError("Pool de conexão com o banco não inicializado (DATABASE_URL ausente).")
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)