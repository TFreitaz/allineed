"""
Estima, para cada produto recorrente, quanto o usuário provavelmente ainda
tem em casa — a partir da quantidade da última compra e do consumo médio
diário calculados em analytics.recurring_products.

Não acessa banco de dados: recebe a lista de RecurringProduct já pronta.
A única entrada "externa" é o instante de referência (`as_of`), que por
padrão é agora — é justamente por depender do momento da execução que essa
estimativa fica separada do módulo de recorrência (que é só sobre o
histórico, e não muda a cada chamada).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from recurring_products import RecurringProduct, get_recurring_products_for_user
from quantity_interpreter import MeasureType


@dataclass(frozen=True)
class EstimatedStock:
    """Estimativa de quanto resta de um produto, a partir da última compra."""

    product_name: str
    last_purchase_date: datetime
    last_purchase_quantity: float
    average_daily_quantity: float
    quantity_unit: str
    measure_type: MeasureType
    days_since_last_purchase: float

    # Pode ser negativo — nesse caso, o consumo médio projetado já
    # ultrapassou o que foi comprado, ou seja, o produto provavelmente
    # já acabou.
    estimated_remaining: float

    @property
    def likely_depleted(self) -> bool:
        return self.estimated_remaining <= 0


def estimate_remaining(produto: RecurringProduct, as_of: Optional[datetime] = None) -> Optional[EstimatedStock]:
    """Estima o estoque restante de um produto recorrente.

    Retorna None quando não há como calcular: produto sem
    average_daily_quantity (unidades inconsistentes no histórico) ou cuja
    última compra não pôde ser interpretada no mesmo tipo de medida usado
    na média diária.
    """
    if produto.average_daily_quantity is None:
        return None

    if (
        produto.last_purchase_unit != produto.quantity_unit
        or produto.last_purchase_measure_type != produto.measure_type
    ):
        # a última compra foi interpretada num tipo/unidade diferente do
        # resto do histórico (ex.: uma linha em UN sem tamanho no nome) —
        # não dá pra combinar com segurança
        return None

    reference = as_of or datetime.now(timezone.utc)
    last_purchase = produto.last_purchase
    if last_purchase.tzinfo is None and reference.tzinfo is not None:
        reference = reference.replace(tzinfo=None)
    elif last_purchase.tzinfo is not None and reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)

    days_since = (reference - last_purchase).total_seconds() / 86400
    consumed_since = produto.average_daily_quantity * days_since
    remaining = produto.last_purchase_quantity - consumed_since

    return EstimatedStock(
        product_name=produto.product_name,
        last_purchase_date=last_purchase,
        last_purchase_quantity=produto.last_purchase_quantity,
        average_daily_quantity=produto.average_daily_quantity,
        quantity_unit=produto.quantity_unit,
        measure_type=produto.measure_type,
        days_since_last_purchase=days_since,
        estimated_remaining=remaining,
    )


def estimate_remaining_for_products(
    produtos: List[RecurringProduct], as_of: Optional[datetime] = None
) -> List[EstimatedStock]:
    """Aplica estimate_remaining a uma lista de produtos recorrentes,
    descartando os que não puderam ser estimados.
    """
    estimativas = [estimate_remaining(p, as_of=as_of) for p in produtos]
    estimativas = [e for e in estimativas if e is not None]

    return sorted(estimativas, key=lambda x: x.estimated_remaining)


def estimate_remaining_for_user(user_id: int, as_of: Optional[datetime] = None) -> List[EstimatedStock]:
    """Atalho: calcula os produtos recorrentes do usuário e já estima o
    estoque restante de cada um.
    """
    produtos = get_recurring_products_for_user(user_id)
    return estimate_remaining_for_products(produtos, as_of=as_of)


if __name__ == "__main__":
    import sys

    from db.connection import init_pool

    init_pool()

    uid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if uid is None:
        print("Uso: python -m analytics.stock_estimator <user_id>")
        raise SystemExit(1)

    for estimativa in estimate_remaining_for_user(uid):
        status = "provavelmente acabou" if estimativa.likely_depleted else "ainda deve ter"
        print(
            f"{estimativa.product_name}: {status} "
            f"~{estimativa.estimated_remaining:.0f}{estimativa.quantity_unit} "
            f"(última compra: {estimativa.last_purchase_quantity:.0f}{estimativa.quantity_unit} "
            f"há {estimativa.days_since_last_purchase:.1f} dias, "
            f"consumo médio de {estimativa.average_daily_quantity:.2f}{estimativa.quantity_unit}/dia)"
        )