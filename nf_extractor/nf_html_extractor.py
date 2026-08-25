import re
import logging
from decimal import Decimal
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telegram-echo-bot")


class NFCeHtmlParser:
    def __init__(self, url: str):
        self.url = url

    def fetch_page(self) -> tuple[str, str]:
        response = requests.get(
            self.url,
            headers=self._get_headers(),
            timeout=30,
        )
        response.raise_for_status()

        return response.text, response.url

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

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    @staticmethod
    def find_products_start(lines: list[str]) -> int:
        marker = (
            "DOCUMENTO AUXILIAR DA NOTA FISCAL "
            "DE CONSUMIDOR ELETRÔNICA"
        )

        return lines.index(marker) + 1

    @staticmethod
    def find_products_end(lines: list[str]) -> int:
        return lines.index("Qtd. total de itens:")

    @staticmethod
    def extract_products(
        lines: list[str],
        start: int,
        end: int,
    ) -> list[dict]:
        products = []

        index = start

        while index < end:
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

            details_start = index + 4

            if not NFCeHtmlParser._is_product_details(
                lines,
                details_start,
                end,
            ):
                index += 1
                continue

            product.update(
                {
                    "quantity": NFCeHtmlParser._parse_decimal(
                        lines[details_start + 1]
                    ),
                    "unit": lines[details_start + 3],
                    "unit_price": NFCeHtmlParser._parse_decimal(
                        lines[details_start + 5]
                    ),
                    "total_price": NFCeHtmlParser._parse_decimal(
                        lines[details_start + 7]
                    ),
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

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @staticmethod
    def extract_metadata(lines: list[str]) -> dict:
        metadata = {
            "store": NFCeHtmlParser._extract_store(lines),
            "document": NFCeHtmlParser._extract_document_data(lines),
            "totals": NFCeHtmlParser._extract_totals(lines),
            "payment": NFCeHtmlParser._extract_payment(lines),
        }

        return metadata

    @staticmethod
    def _extract_store(lines: list[str]) -> dict:
        cnpj_index = lines.index("CNPJ:")

        return {
            "name": lines[cnpj_index - 1],
            "cnpj": lines[cnpj_index + 1],
            "address": NFCeHtmlParser._extract_address(
                lines,
                cnpj_index,
            ),
        }

    @staticmethod
    def _extract_address(
        lines: list[str],
        cnpj_index: int,
    ) -> dict:
        address_lines = lines[cnpj_index + 2:]

        city_index = None

        for index, line in enumerate(address_lines):
            if line == "ITUVERAVA":
                city_index = index
                break

        if city_index is None:
            return {}

        return {
            "street": address_lines[0],
            "number": address_lines[2],
            "neighborhood": address_lines[4],
            "city": address_lines[city_index],
            "state": address_lines[city_index + 2],
        }

    @staticmethod
    def _extract_document_data(lines: list[str]) -> dict:
        number_index = lines.index("Número:")
        series_index = lines.index("Série:")
        issue_date_index = lines.index("Emissão:")
        protocol_index = lines.index(
            "Protocolo de Autorização:"
        )
        access_key_index = lines.index(
            "Chave de acesso:"
        )

        access_key = lines[access_key_index + 1]
        access_key = access_key.replace(" ", "")

        return {
            "number": lines[number_index + 1],
            "series": lines[series_index + 1],
            "issued_at": datetime.strptime(
                lines[issue_date_index + 1],
                "%d/%m/%Y %H:%M:%S",
            ),
            "authorization_protocol": (
                lines[protocol_index + 1].split()[0]
            ),
            "access_key": access_key,
        }

    @staticmethod
    def _extract_totals(lines: list[str]) -> dict:
        total_items_index = lines.index(
            "Qtd. total de itens:"
        )
        total_amount_index = None
        if any(element == "Valor total R$:" for element in lines):
            total_amount_index = lines.index(
                "Valor total R$:"
            )
        discount_index=None
        if any(element == "Descontos R$:" for element in lines):
            discount_index = lines.index(
                "Descontos R$:"
            )
        amount_to_pay_index = lines.index(
            "Valor a pagar R$:"
        )

        return {
            "total_items": int(
                lines[total_items_index + 1]
            ),
            "total_amount": NFCeHtmlParser._parse_decimal(
                lines[total_amount_index + 1]
            ) if total_amount_index else None,
            "discount": NFCeHtmlParser._parse_decimal(
                lines[discount_index + 1]
            ) if discount_index else None,
            "amount_to_pay": NFCeHtmlParser._parse_decimal(
                lines[amount_to_pay_index + 1]
            ),
        }

    @staticmethod
    def _extract_payment(lines: list[str]) -> dict:
        payment_index = lines.index(
            "Forma de pagamento:"
        )

        return {
            "method": lines[payment_index + 2],
            "amount_paid": NFCeHtmlParser._parse_decimal(
                lines[payment_index + 3]
            ),
        }

    @staticmethod
    def is_document_not_found(soup: BeautifulSoup) -> bool:
        text = soup.get_text(" ", strip=True).lower()

        not_found = "documento fiscal (nfc-e) inexistente" in text

        if not_found:
            logger.info("The NFC-e URL returned a broken document.")

        return not_found

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_products(self) -> list[dict]:
        html = self.fetch_page()
        soup = self.parse_html(html)

        if self.is_document_not_found(soup):
            return []

        lines = self.extract_lines(soup)

        start = self.find_products_start(lines)
        end = self.find_products_end(lines)

        return self.extract_products(
            lines,
            start,
            end,
        )

    def get_metadata(self) -> dict:
        html = self.fetch_page()
        soup = self.parse_html(html)

        if self.is_document_not_found(soup):
            return []

        lines = self.extract_lines(soup)

        return self.extract_metadata(lines)

    def get_data(self) -> dict:
        html, final_url = self.fetch_page()

        if (
            final_url.startswith(
                "https://www.nfce.fazenda.sp.gov.br/"
                "NFCeConsultaPublica/Paginas/ConsultaPublica.aspx"
            )
        ):
            return

        soup = self.parse_html(html)
        lines = self.extract_lines(soup)

        start = self.find_products_start(lines)
        end = self.find_products_end(lines)

        return {
            "metadata": self.extract_metadata(lines),
            "products": self.extract_products(
                lines,
                start,
                end,
            ),
        }

    @staticmethod
    def _parse_decimal(value: str) -> Decimal:
        return Decimal(
            value.replace(".", "").replace(",", ".")
        )
