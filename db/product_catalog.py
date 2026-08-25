"""
Consultas relacionadas ao catálogo de produtos.

Este módulo contém somente operações de acesso ao banco.
A estrutura dos dados para consumo pela aplicação fica em
product_catalog.py.
"""

import logging
from typing import List, Dict, Any

from .connection import get_connection

logger = logging.getLogger("telegram-echo-bot.db.product_catalog")


def get_uncatalogued_products() -> List[Dict[str, Any]]:
    """
    Retorna os produtos de estabelecimentos que ainda não foram
    associados a um produto curado.

    Cada item contém:
        - store_product_id
        - name
    """

    query = """
        SELECT
            store_product_id,
            base_name AS name
        FROM store_products
        WHERE product_id IS NULL
        ORDER BY base_name;
    """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return [
        {
            "store_product_id": row[0],
            "name": row[1],
        }
        for row in rows
    ]


def get_product_catalog() -> List[Dict[str, Any]]:
    """
    Retorna todos os produtos existentes no catálogo curado.

    Cada item contém:
        - product_id
        - name
    """

    query = """
        SELECT
            product_id,
            name
        FROM products
        ORDER BY name;
    """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return [
        {
            "product_id": row[0],
            "name": row[1],
        }
        for row in rows
    ]