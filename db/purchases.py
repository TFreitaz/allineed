"""
Acesso a dados para o fluxo de NFC-e: lojas, produtos por loja, compras e itens
de compra (schema criado em db/migrations/0002_create_stores_and_purchases.sql).

Formato esperado de `data` (retorno de NFCeParser.get_data()):

    {
        "metadata": {
            "document": {
                "access_key": str,
                "number": str,
                "series": str,
                "issued_at": datetime,
                "authorization_protocol": str,
            },
            "store": {
                "cnpj": str,           # ex: "09.418.668/0009-85"
                "name": str,
                "address": {
                    "street": str,
                    "number": str,
                    "neighborhood": str,
                    "city": str,
                    "state": str,
                },
            },
            "totals": {
                "total_amount": Decimal,
                "discount": Decimal,
                "amount_to_pay": Decimal,
                "total_items": int,
            },
            "payment": {
                "method": str,
                "amount_paid": Decimal,
            },
        },
        "products": [
            {
                "code": str,
                "name": str,
                "quantity": Decimal,
                "unit": str,
                "unit_price": Decimal,
                "total_price": Decimal,
            },
            ...
        ],
    }

Uso típico (a partir de onde você já tem o user_id e, se disponível, o
message_id da tabela `messages`):

    from db.purchases import save_purchase

    data = extractor.get_data()
    purchase_id = save_purchase(user_id=user_id, data=data, source_message_id=message_id)
"""

import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from db.connection import get_connection

logger = logging.getLogger("telegram-echo-bot.db.purchases")


def _only_digits(value: Optional[str]) -> Optional[str]:
    """Remove pontuação do CNPJ (ex: '09.418.668/0009-85' -> '09418668000985')."""
    if not value:
        return None
    return re.sub(r"\D", "", value) or None


def _as_decimal(value) -> Optional[Decimal]:
    """
    Os valores monetários já costumam vir como Decimal do extractor. Isso aqui
    é só uma rede de segurança para o caso de vir string ou None em algum campo.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text or text.upper() == "N/A":
        return None
    text = re.sub(r"[^\d,.\-]", "", text)
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        logger.warning("Não foi possível converter valor monetário: %r", value)
        return None


def _as_datetime(value) -> Optional[datetime]:
    """issued_at já costuma vir como datetime pronto; trata string como fallback."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    logger.warning("Não foi possível converter issued_at: %r", value)
    return None


def _upsert_store(cur, store_info: dict) -> int:
    """Cria a loja se não existir (pelo CNPJ normalizado) ou atualiza dados se já existir."""
    cnpj = _only_digits(store_info.get("cnpj"))
    name = store_info.get("name")
    address = store_info.get("address", {})

    cur.execute(
        """
        INSERT INTO stores (cnpj, name, street, address_number, neighborhood, city, state)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (cnpj) DO UPDATE SET
            name = EXCLUDED.name,
            street = EXCLUDED.street,
            address_number = EXCLUDED.address_number,
            neighborhood = EXCLUDED.neighborhood,
            city = EXCLUDED.city,
            state = EXCLUDED.state,
            updated_at = now()
        RETURNING store_id
        """,
        (
            cnpj,
            name,
            address.get("street"),
            address.get("number"),
            address.get("neighborhood"),
            address.get("city"),
            address.get("state"),
        ),
    )
    return cur.fetchone()[0]


def _upsert_store_product(cur, store_id: int, product: dict) -> int:
    """Cria o produto da loja se não existir (pelo par store_id + code) ou atualiza o nome. Retorna store_product_id."""
    code = product.get("code")
    name = product.get("name")

    cur.execute(
        """
        INSERT INTO store_products (store_id, code, base_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (store_id, code) DO UPDATE SET
            base_name = EXCLUDED.base_name,
            updated_at = now()
        RETURNING store_product_id
        """,
        (store_id, code, name),
    )
    return cur.fetchone()[0]


def save_purchase(user_id: int, data: dict, source_message_id: Optional[int] = None) -> int:
    """
    Salva a compra (NFC-e) completa: loja, produtos da loja, a compra em si e
    os itens da compra. Idempotente em relação à nota: se a mesma access_key
    já foi salva antes, não duplica a compra (retorna o purchase_id existente).
    """
    metadata = data.get("metadata", {})
    document = metadata.get("document", {})
    store_info = metadata.get("store", {})
    totals = metadata.get("totals", {})
    payment = metadata.get("payment", {})
    products = data.get("products", [])

    access_key = document.get("access_key")
    if not access_key or str(access_key).upper() == "N/A":
        raise ValueError("data['metadata']['document']['access_key'] é obrigatório para salvar a compra.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            store_id = _upsert_store(cur, store_info)

            # Se essa NFC-e já foi salva antes (mesma access_key), não duplica.
            cur.execute("SELECT purchase_id FROM purchases WHERE access_key = %s", (access_key,))
            existing = cur.fetchone()
            if existing:
                conn.commit()
                logger.info("Compra já existia para access_key=%s (purchase_id=%s)", access_key, existing[0])
                return existing[0]

            cur.execute(
                """
                INSERT INTO purchases (
                    user_id, store_id, source_message_id, access_key,
                    document_number, series, issued_at, authorization_protocol,
                    total_items, total_amount, discount, amount_to_pay,
                    payment_method, amount_paid
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING purchase_id
                """,
                (
                    user_id,
                    store_id,
                    source_message_id,
                    access_key,
                    document.get("number"),
                    document.get("series"),
                    _as_datetime(document.get("issued_at")),
                    document.get("authorization_protocol"),
                    totals.get("total_items"),
                    _as_decimal(totals.get("total_amount")),
                    _as_decimal(totals.get("discount")),
                    _as_decimal(totals.get("amount_to_pay")),
                    payment.get("method"),
                    _as_decimal(payment.get("amount_paid")),
                ),
            )
            purchase_id = cur.fetchone()[0]

            for product in products:
                store_product_id = _upsert_store_product(cur, store_id, product)

                cur.execute(
                    """
                    INSERT INTO purchase_items (
                        purchase_id, store_product_id, quantity, unit, unit_price, total_price
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        purchase_id,
                        store_product_id,
                        _as_decimal(product.get("quantity")),
                        product.get("unit"),
                        _as_decimal(product.get("unit_price")),
                        _as_decimal(product.get("total_price")),
                    ),
                )

        conn.commit()

    logger.info("Compra salva. purchase_id=%s store_id=%s itens=%s", purchase_id, store_id, len(products))
    return purchase_id