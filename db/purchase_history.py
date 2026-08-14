"""
Consulta o histórico de compras de um usuário, já com o mapeamento
store_products -> products aplicado.

Usa o pool de conexões definido em db/connection.py. Nenhuma lógica de
análise fica aqui — só a leitura dos dados.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import psycopg2.extras

from db.connection import get_connection

logger = logging.getLogger("telegram-echo-bot.db.purchase_history")


@dataclass(frozen=True)
class PurchaseItemRecord:
    """Um item comprado, já com a data efetiva da compra e o produto mapeado."""

    purchase_id: int
    purchase_date: datetime
    store_product_id: int
    product_id: Optional[int]
    product_name: str  # nome canônico (products.name) ou base_name da loja, se não mapeado
    quantity: float
    unit: str
    unit_price: float
    total_price: float
    base_name: Optional[str] = None  # base_name da loja, mesmo que mapeado para um product_id

    @property
    def grouping_key(self):
        """Chave para agrupar itens do 'mesmo produto'.

        Usa product_id quando o item está mapeado para o catálogo canônico
        (products). Quando não está mapeado (store_products.product_id NULL),
        cai para o store_product_id — evita misturar produtos diferentes de
        lojas diferentes que ainda não foram associados a um product_id.
        """
        if self.product_id is not None:
            return ("product", self.product_id)
        return ("store_product", self.store_product_id)


_QUERY = """
    SELECT
        p.purchase_id,
        COALESCE(p.issued_at, p.created_at) AS purchase_date,
        pi.store_product_id,
        sp.product_id,
        sp.base_name,
        COALESCE(pr.name, sp.base_name) AS product_name,
        pi.quantity,
        pi.unit,
        pi.unit_price,
        pi.total_price
    FROM purchases p
    JOIN purchase_items pi ON pi.purchase_id = p.purchase_id
    JOIN store_products sp ON sp.store_product_id = pi.store_product_id
    LEFT JOIN products pr ON pr.product_id = sp.product_id
    WHERE p.user_id = %(user_id)s
    ORDER BY purchase_date ASC;
"""


def get_purchase_history(user_id: int) -> List[PurchaseItemRecord]:
    """Retorna todos os itens comprados pelo usuário, ordenados por data.

    Cada linha do retorno é um item de compra (purchase_items), não uma
    compra inteira — uma mesma purchase_id pode aparecer várias vezes se
    a nota tiver múltiplos itens.
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_QUERY, {"user_id": user_id})
            rows = cur.fetchall()

    records = [
        PurchaseItemRecord(
            purchase_id=row["purchase_id"],
            purchase_date=row["purchase_date"],
            store_product_id=row["store_product_id"],
            product_id=row["product_id"],
            product_name=row["product_name"],
            quantity=float(row["quantity"]),
            unit=row["unit"],
            unit_price=float(row["unit_price"]),
            total_price=float(row["total_price"]),
            base_name=row["base_name"]
        )
        for row in rows
    ]

    logger.info("Histórico carregado para user_id=%s: %d itens.", user_id, len(records))
    return records