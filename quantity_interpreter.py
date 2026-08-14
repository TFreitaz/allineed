"""
Interpreta itens de compra para estimar a quantidade real (peso ou volume)
que o cliente levou para casa.

Não acessa banco de dados nem depende de nenhum outro módulo do projeto —
recebe três valores simples (nome do produto, quantidade, unidade) e
devolve a interpretação. Pensado para ser chamado pelo módulo de análise
de recorrência, item a item.

Estratégia:
1. Se a unidade da nota já é uma unidade de peso/volume (KG, G, L, ML...),
   a conversão é direta: não precisa olhar o nome.
2. Se a unidade é uma unidade de contagem (UN, PC, CX...), tenta extrair
   do nome do produto uma especificação de tamanho (ex.: "2L", "900G",
   "12X350ML") e multiplica pela quantidade comprada.
3. Se nada for encontrado, cai para contagem simples (não dá para saber
   peso/volume) e sinaliza isso no campo `confidence`.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MeasureType(str, Enum):
    MASS = "mass"       # resultado em gramas
    VOLUME = "volume"    # resultado em mililitros
    COUNT = "count"      # não foi possível determinar peso/volume


class Confidence(str, Enum):
    EXPLICIT_UNIT = "explicit_unit"     # a própria unidade da nota já é peso/volume
    PARSED_FROM_NAME = "parsed_from_name"  # tamanho extraído do nome do produto
    UNKNOWN = "unknown"                  # nenhuma informação de peso/volume disponível


@dataclass(frozen=True)
class InterpretedQuantity:
    """Resultado da interpretação de um item."""

    measure_type: MeasureType
    value: float          # quantidade total já convertida
    unit: str              # "g", "ml" ou "un"
    confidence: Confidence
    matched_text: Optional[str] = None  # trecho do nome usado no parsing, útil para depuração

    def __repr__(self) -> str:
        return f"{self.value:g}{self.unit} ({self.confidence.value})"


# ---------------------------------------------------------------------------
# Tabelas de conversão
# ---------------------------------------------------------------------------

# unidade da NOTA FISCAL (purchase_items.unit) -> (tipo, unidade base, fator para a base)
_EXPLICIT_UNITS = {
    "KG": (MeasureType.MASS, "g", 1000.0),
    "G": (MeasureType.MASS, "g", 1.0),
    "GR": (MeasureType.MASS, "g", 1.0),
    "MG": (MeasureType.MASS, "g", 0.001),
    "L": (MeasureType.VOLUME, "ml", 1000.0),
    "LT": (MeasureType.VOLUME, "ml", 1000.0),
    "ML": (MeasureType.VOLUME, "ml", 1.0),
}

# unidade encontrada NO NOME do produto -> mesmo esquema acima
_NAME_UNITS = _EXPLICIT_UNITS

# unidades de contagem conhecidas (não carregam peso/volume por si só)
_COUNT_UNITS = {"UN", "PC", "CX", "PCT", "FD", "DZ"}

_UNIT_ALTERNATION = "|".join(sorted(_NAME_UNITS.keys(), key=len, reverse=True))

# "12X350ML", "6 X 1L", "PACK C/12 350ML"
_PACK_PATTERN = re.compile(
    rf"(\d+)\s*[xX]\s*(\d+[.,]?\d*)\s*({_UNIT_ALTERNATION})\b"
)

# "2L", "1,5L", "500G", "900ML", "1KG" — captura todas as ocorrências;
# o parsing usa a ÚLTIMA, pois especificações de tamanho normalmente
# aparecem no fim do nome do produto.
_SIMPLE_PATTERN = re.compile(
    rf"(\d+[.,]?\d*)\s*({_UNIT_ALTERNATION})\b"
)


def _to_float(raw: str) -> float:
    """Converte string numérica no formato PT-BR (vírgula decimal) para float."""
    return float(raw.replace(",", "."))


def _normalize(value: float, unit_token: str) -> tuple:
    """Aplica o fator de conversão da tabela e devolve (tipo, valor_na_base, unidade_base)."""
    measure_type, base_unit, factor = _NAME_UNITS[unit_token.upper()]
    return measure_type, value * factor, base_unit


def _parse_size_from_name(name: str):
    """Tenta extrair do nome do produto o tamanho de UMA unidade (ex.: "2L"
    de "REFRIGERANTE 2L", ou 350ml de "12X350ML" já multiplicado pelo
    tamanho do pack).

    Retorna (measure_type, valor_por_unidade_na_base, unidade_base, texto_usado)
    ou None se nada for encontrado.
    """
    name_upper = name.upper()

    pack_match = _PACK_PATTERN.search(name_upper)
    if pack_match:
        pack_count = int(pack_match.group(1))
        size_value = _to_float(pack_match.group(2))
        unit_token = pack_match.group(3)
        measure_type, base_value, base_unit = _normalize(size_value, unit_token)
        return measure_type, base_value * pack_count, base_unit, pack_match.group(0)

    simple_matches = list(_SIMPLE_PATTERN.finditer(name_upper))
    if simple_matches:
        last = simple_matches[-1]
        size_value = _to_float(last.group(1))
        unit_token = last.group(2)
        measure_type, base_value, base_unit = _normalize(size_value, unit_token)
        return measure_type, base_value, base_unit, last.group(0)

    return None


def interpret_item(base_name: str, quantity: float, unit: str) -> InterpretedQuantity:
    """Interpreta um item de compra e retorna a quantidade real (peso ou
    volume) levada pelo cliente.

    Args:
        base_name: nome do produto como a loja escreve na nota
                    (store_products.base_name).
        quantity: quantidade da linha da nota (purchase_items.quantity).
        unit: unidade da linha da nota (purchase_items.unit), ex.: "KG", "UN".
    """
    unit_normalized = (unit or "").strip().upper()

    # Caso 1: a própria unidade da nota já é peso/volume — conversão direta,
    # não precisa olhar o nome.
    if unit_normalized in _EXPLICIT_UNITS:
        measure_type, base_unit, factor = _EXPLICIT_UNITS[unit_normalized]
        return InterpretedQuantity(
            measure_type=measure_type,
            value=quantity * factor,
            unit=base_unit,
            confidence=Confidence.EXPLICIT_UNIT,
        )

    # Caso 2: unidade de contagem (ou desconhecida) — tenta extrair o
    # tamanho de uma unidade a partir do nome do produto.
    parsed = _parse_size_from_name(base_name or "")
    if parsed is not None:
        measure_type, value_per_unit, base_unit, matched_text = parsed
        return InterpretedQuantity(
            measure_type=measure_type,
            value=quantity * value_per_unit,
            unit=base_unit,
            confidence=Confidence.PARSED_FROM_NAME,
            matched_text=matched_text,
        )

    # Caso 3: não há como saber peso/volume — cai para contagem simples.
    return InterpretedQuantity(
        measure_type=MeasureType.COUNT,
        value=quantity,
        unit="un",
        confidence=Confidence.UNKNOWN,
    )
