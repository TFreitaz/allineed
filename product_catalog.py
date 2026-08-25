"""
Estrutura os dados de catálogo para consumo pela interface.
"""

from dataclasses import dataclass
from typing import List

from db.product_catalog import (
    get_uncatalogued_products,
    get_product_catalog,
)


@dataclass(frozen=True)
class UncataloguedProduct:
    store_product_id: int
    name: str


@dataclass(frozen=True)
class CatalogProduct:
    product_id: int
    name: str


@dataclass(frozen=True)
class ProductCatalogData:
    uncatalogued_products: List[UncataloguedProduct]
    catalog_products: List[CatalogProduct]


def get_product_catalog_data() -> ProductCatalogData:
    """
    Retorna todos os dados necessários para a interface
    de classificação de produtos.
    """

    uncatalogued = get_uncatalogued_products()
    catalog = get_product_catalog()

    return ProductCatalogData(
        uncatalogued_products=[
            UncataloguedProduct(
                store_product_id=item["store_product_id"],
                name=item["name"],
            )
            for item in uncatalogued
        ],
        catalog_products=[
            CatalogProduct(
                product_id=item["product_id"],
                name=item["name"],
            )
            for item in catalog
        ],
    )