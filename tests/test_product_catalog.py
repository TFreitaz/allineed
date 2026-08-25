from unittest.mock import patch

from product_catalog import (
    CatalogProduct,
    ProductCatalogData,
    UncataloguedProduct,
    get_product_catalog_data,
)


class TestGetProductCatalogData:

    @patch("product_catalog.get_product_catalog")
    @patch("product_catalog.get_uncatalogued_products")
    def test_returns_product_catalog_data(
        self,
        mock_get_uncatalogued_products,
        mock_get_product_catalog,
    ):
        mock_get_uncatalogued_products.return_value = [
            {
                "store_product_id": 123,
                "name": "COCA COLA 2L",
            },
            {
                "store_product_id": 456,
                "name": "ARROZ TIO JOAO 5KG",
            },
        ]

        mock_get_product_catalog.return_value = [
            {
                "product_id": 1,
                "name": "Coca-Cola",
            },
            {
                "product_id": 2,
                "name": "Arroz",
            },
        ]

        result = get_product_catalog_data()

        assert isinstance(result, ProductCatalogData)

        assert result.uncatalogued_products == [
            UncataloguedProduct(
                store_product_id=123,
                name="COCA COLA 2L",
            ),
            UncataloguedProduct(
                store_product_id=456,
                name="ARROZ TIO JOAO 5KG",
            ),
        ]

        assert result.catalog_products == [
            CatalogProduct(
                product_id=1,
                name="Coca-Cola",
            ),
            CatalogProduct(
                product_id=2,
                name="Arroz",
            ),
        ]

    @patch("product_catalog.get_product_catalog")
    @patch("product_catalog.get_uncatalogued_products")
    def test_calls_database_functions(
        self,
        mock_get_uncatalogued_products,
        mock_get_product_catalog,
    ):
        mock_get_uncatalogued_products.return_value = []
        mock_get_product_catalog.return_value = []

        get_product_catalog_data()

        mock_get_uncatalogued_products.assert_called_once_with()
        mock_get_product_catalog.assert_called_once_with()

    @patch("product_catalog.get_product_catalog")
    @patch("product_catalog.get_uncatalogued_products")
    def test_returns_empty_lists_when_database_returns_empty(
        self,
        mock_get_uncatalogued_products,
        mock_get_product_catalog,
    ):
        mock_get_uncatalogued_products.return_value = []
        mock_get_product_catalog.return_value = []

        result = get_product_catalog_data()

        assert result == ProductCatalogData(
            uncatalogued_products=[],
            catalog_products=[],
        )