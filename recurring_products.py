"""
Analisa um histórico de compras (db.purchase_history.PurchaseItemRecord) e
identifica produtos comprados mais de uma vez, calculando:

- o intervalo médio (em tempo) entre as compras;
- a média ponderada de quantidade real (peso/volume/contagem) consumida
  por dia, usando o interpretador de quantidades sobre o base_name.

Não faz nenhum acesso a banco — recebe os registros já carregados.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from db.purchase_history import PurchaseItemRecord, get_purchase_history
from quantity_interpreter import MeasureType, interpret_item

logger = logging.getLogger("telegram-echo-bot.analytics.recurring_products")


@dataclass(frozen=True)
class RecurringProduct:
    """Um produto comprado mais de uma vez, com estatísticas de recorrência."""

    product_name: str
    times_purchased: int
    first_purchase: datetime
    last_purchase: datetime
    average_interval: timedelta

    # Quantidade real (peso/volume/contagem) comprada por dia, em média
    # ponderada pelo número de dias de cada intervalo. None quando não foi
    # possível calcular (unidade/tipo inconsistente entre as compras, ou
    # todas as compras no mesmo dia).
    average_daily_quantity: Optional[float]
    quantity_unit: Optional[str]  # "g", "ml" ou "un"
    measure_type: Optional[MeasureType]

    # Quantidade real interpretada da ÚLTIMA compra — é o "estoque inicial"
    # a partir do qual dá pra estimar quanto ainda resta, junto com
    # average_daily_quantity. Tem sua própria unidade/tipo (independente da
    # consistência do restante do grupo, que só afeta average_daily_quantity).
    last_purchase_quantity: float
    last_purchase_unit: str
    last_purchase_measure_type: MeasureType

    @property
    def average_interval_days(self) -> float:
        return self.average_interval.total_seconds() / 86400


def _average_interval(dates: List[datetime]) -> timedelta:
    """Recebe datas já ordenadas e retorna o intervalo médio entre compras
    consecutivas.
    """
    diffs = [b - a for a, b in zip(dates, dates[1:])]
    total_seconds = sum(d.total_seconds() for d in diffs)
    return timedelta(seconds=total_seconds / len(diffs))


def _average_daily_quantity(purchases: List[Dict]):
    """Calcula a média ponderada de quantidade real por dia.

    A ponderação é pelo número de dias de cada intervalo: cada compra
    (exceto a última) "abasteceu" o cliente até a compra seguinte, então
    seu peso no cálculo é justamente esse intervalo. Isso equivale a
        soma(quantidade das compras, exceto a última) / soma(dias de cada intervalo)
    que, como os intervalos são consecutivos, é o mesmo que dividir pelo
    total de dias entre a primeira e a última compra.

    Ex.: 10L em 13/08 e 10L em 18/08 -> 10L / 5 dias = 2L/dia (a compra de
    18/08 não entra no numerador: ainda não sabemos por quantos dias ela
    vai durar).

    Retorna (valor, unidade, tipo) ou (None, None, None) se não for
    possível calcular (unidade/tipo inconsistentes entre as compras, ou
    intervalo total igual a zero).
    """
    units = {p["unit"] for p in purchases}
    types = {p["measure_type"] for p in purchases}
    all_consistent = all(p["consistent"] for p in purchases)

    if not all_consistent or len(units) != 1 or len(types) != 1:
        logger.warning(
            "Quantidade não pôde ser padronizada entre as compras do grupo "
            "(unidades=%s, tipos=%s, consistente=%s) — média diária não calculada.",
            units,
            types,
            all_consistent,
        )
        return None, None, None

    total_days = (purchases[-1]["date"] - purchases[0]["date"]).total_seconds() / 86400
    if total_days <= 0:
        return None, None, None

    quantity_excluding_last = sum(p["quantity"] for p in purchases[:-1])
    average = quantity_excluding_last / total_days
    return average, units.pop(), types.pop()


def find_recurring_products(
    records: List[PurchaseItemRecord],
) -> List[RecurringProduct]:
    """Agrupa os itens por produto e retorna apenas os comprados mais de uma
    vez (considerando purchase_id distintas — várias unidades na mesma nota
    não contam como "recompra"), ordenados do intervalo médio mais curto
    para o mais longo.
    """
    # agrupa: chave do produto -> nome + compras (purchase_id -> dados agregados)
    groups: Dict[object, Dict] = {}

    for item in records:
        key = item.grouping_key
        group = groups.setdefault(key, {"product_name": item.product_name, "purchases": {}})

        interpreted = interpret_item(item.base_name, item.quantity, item.unit)

        purchase = group["purchases"].get(item.purchase_id)
        if purchase is None:
            group["purchases"][item.purchase_id] = {
                "date": item.purchase_date,
                "quantity": interpreted.value,
                "unit": interpreted.unit,
                "measure_type": interpreted.measure_type,
                "consistent": True,
            }
        elif purchase["unit"] == interpreted.unit and purchase["measure_type"] == interpreted.measure_type:
            # mesmo produto apareceu mais de uma vez na mesma nota (raro,
            # mas possível) — soma a quantidade interpretada
            purchase["quantity"] += interpreted.value
        else:
            # a mesma nota trouxe o mesmo produto interpretado em unidades
            # diferentes (ex.: uma linha em KG e outra em UN) — não dá pra
            # somar com segurança, então marca o grupo como inconsistente
            logger.warning(
                "Unidade inconsistente para purchase_id=%s, produto=%r: "
                "%s%s já registrado, item novo em %s%s.",
                item.purchase_id,
                group["product_name"],
                purchase["quantity"],
                purchase["unit"],
                interpreted.value,
                interpreted.unit,
            )
            purchase["consistent"] = False

    recurring: List[RecurringProduct] = []
    for group in groups.values():
        purchases = sorted(group["purchases"].values(), key=lambda p: p["date"])
        if len(purchases) < 2:
            continue  # só interessa quem foi comprado mais de uma vez

        dates = [p["date"] for p in purchases]
        avg_quantity, quantity_unit, measure_type = _average_daily_quantity(purchases)

        recurring.append(
            RecurringProduct(
                product_name=group["product_name"],
                times_purchased=len(purchases),
                first_purchase=dates[0],
                last_purchase=dates[-1],
                average_interval=_average_interval(dates),
                average_daily_quantity=avg_quantity,
                quantity_unit=quantity_unit,
                measure_type=measure_type,
                last_purchase_quantity=purchases[-1]["quantity"],
                last_purchase_unit=purchases[-1]["unit"],
                last_purchase_measure_type=purchases[-1]["measure_type"],
            )
        )

    recurring.sort(key=lambda r: r.average_interval)
    return recurring


def get_recurring_products_for_user(user_id: int) -> List[RecurringProduct]:
    """Atalho: carrega o histórico do usuário e já retorna os produtos
    recorrentes calculados.
    """
    records = get_purchase_history(user_id)
    return find_recurring_products(records)
