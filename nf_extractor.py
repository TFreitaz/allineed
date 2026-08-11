import re
from decimal import Decimal

import requests
from bs4 import BeautifulSoup


class NFCeParser:
    def __init__(self, url: str):
        self.url = url

    def fetch_page(self) -> str:
        response = requests.get(
            self.url,
            headers=self._get_headers(),
            timeout=30,
        )
        response.raise_for_status()

        return response.text

    @staticmethod
    def _get_headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            )
        }

    @staticmethod
    def parse_html(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    @staticmethod
    def extract_lines(soup: BeautifulSoup) -> list[str]:
        return [
            line.strip()
            for line in soup.get_text("\n").splitlines()
            if line.strip()
        ]

    @staticmethod
    def find_products_start(lines: list[str]) -> int:
        marker = "DOCUMENTO AUXILIAR DA NOTA FISCAL DE CONSUMIDOR ELETRÔNICA"

        return lines.index(marker) + 1

    @staticmethod
    def find_products_end(lines: list[str]) -> int:
        marker = "Qtd. total de itens:"

        return lines.index(marker)

    @staticmethod
    def extract_products(
        lines: list[str],
        start: int,
        end: int,
    ) -> list[dict]:
        products = []

        index = start

        while index < end:
            # A product starts with:
            #
            # PRODUCT NAME
            # (Código:
            # 123456
            # )

            if (
                index + 3 >= end
                or lines[index + 1] != "(Código:"
                or lines[index + 3] != ")"
            ):
                index += 1
                continue

            product = {
                "name": lines[index],
                "code": lines[index + 2],
            }

            # Product details:
            #
            # Qtde.:
            # 1
            # UN:
            # UN
            # Vl. Unit.:
            # 8,98
            # Vl. Total
            # 8,98

            details_start = index + 4

            if not NFCeParser._is_product_details(
                lines,
                details_start,
                end,
            ):
                index += 1
                continue

            product.update(
                {
                    "quantity": lines[details_start + 1],
                    "unit": lines[details_start + 3],
                    "unit_price": lines[details_start + 5],
                    "total_price": lines[details_start + 7],
                }
            )

            products.append(product)

            index = details_start + 8

        return products

    @staticmethod
    def _is_product_details(
        lines: list[str],
        start: int,
        end: int,
    ) -> bool:
        if start + 7 >= end:
            return False

        return (
            lines[start] == "Qtde.:"
            and lines[start + 2] == "UN:"
            and lines[start + 4] == "Vl. Unit.:"
            and lines[start + 6] == "Vl. Total"
        )

    @staticmethod
    def normalize_products(products: list[dict]) -> list[dict]:
        return [
            {
                **product,
                "quantity": NFCeParser._parse_decimal(
                    product["quantity"]
                ),
                "unit_price": NFCeParser._parse_decimal(
                    product["unit_price"]
                ),
                "total_price": NFCeParser._parse_decimal(
                    product["total_price"]
                ),
            }
            for product in products
        ]

    @staticmethod
    def _parse_decimal(value: str) -> Decimal:
        return Decimal(
            value.replace(".", "").replace(",", ".")
        )

    def get_products(self) -> list[dict]:
        html = self.fetch_page()
        soup = self.parse_html(html)
        lines = self.extract_lines(soup)

        start = self.find_products_start(lines)
        end = self.find_products_end(lines)

        products = self.extract_products(
            lines,
            start,
            end,
        )

        return self.normalize_products(products)


if __name__ == "__main__":
    url = (
        "https://www.nfce.fazenda.sp.gov.br/"
        "NFCeConsultaPublica/Paginas/ConsultaQRCode.aspx"
        "?p=35260709418668000985651080001318481382606359|3|1"
    )

    parser = NFCeParser(url)

    products = parser.get_products()

    for product in products:
        print(product)