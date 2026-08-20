import re
from decimal import Decimal
from datetime import datetime

import fitz


class NFCePdfParser:
    def __init__(self, pdf_content: bytes | bytearray):
        self.pdf_content = pdf_content

    def _open_document(self):
        return fitz.open(
            stream=self.pdf_content,
            filetype="pdf",
        )

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------

    def _get_page(self) -> fitz.Page:
        document = self._open_document()

        if not document.page_count:
            document.close()
            raise ValueError("O PDF não possui páginas.")

        page = document[0]

        # Mantém o documento aberto enquanto a página é utilizada.
        # O documento será fechado pelo caller através de _extract_text.
        return page

    def _extract_text(self) -> str:
        document = self._open_document()

        try:
            if not document.page_count:
                raise ValueError("O PDF não possui páginas.")

            return document[0].get_text("text")

        finally:
            document.close()

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    @staticmethod
    def extract_products(text: str) -> list[dict]:
        pattern = re.compile(
            r"""
            (?P<name>.+?)
            \s*\(Código:\s*(?P<code>\d+)\s*\)
            \s*
            Qtde\.(?P<quantity>[\d.,]+)
            \s*
            UN:\s*(?P<unit>\S+)
            \s*
            Vl\.\s*Unit\.:\s*(?P<unit_price>[\d.,]+)
            \s*
            Vl\.\s*Total
            \s*
            (?P<total_price>[\d.,]+)
            """,
            re.VERBOSE,
        )

        products = []

        for match in pattern.finditer(text):
            products.append(
                {
                    "name": match.group("name").strip(),
                    "code": match.group("code"),
                    "quantity": NFCePdfParser._parse_decimal(
                        match.group("quantity")
                    ),
                    "unit": match.group("unit"),
                    "unit_price": NFCePdfParser._parse_decimal(
                        match.group("unit_price")
                    ),
                    "total_price": NFCePdfParser._parse_decimal(
                        match.group("total_price")
                    ),
                }
            )

        return products

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @staticmethod
    def extract_store(text: str) -> dict:
        match = re.search(
            r"""
            (?P<name>.+?)
            \s*
            CNPJ:\s*(?P<cnpj>[\d./-]+)
            \s*
            (?P<address>.+?)
            \s*
            (?P<city>[A-ZÀ-Ú\s]+)\s*,\s*(?P<state>[A-Z]{2})
            \s*
            BOLO
            """,
            text,
            re.VERBOSE | re.DOTALL,
        )

        if not match:
            raise ValueError(
                "Não foi possível identificar os dados da loja."
            )

        address = match.group("address").strip()

        return {
            "name": match.group("name").strip(),
            "cnpj": match.group("cnpj"),
            "address": NFCePdfParser._extract_address(
                address,
                match.group("city"),
                match.group("state"),
            ),
        }

    @staticmethod
    def _extract_address(
        address: str,
        city: str,
        state: str,
    ) -> dict:
        address = re.sub(r"\s+", " ", address).strip()

        parts = [
            part.strip()
            for part in address.split(",")
        ]

        parts = [
            part
            for part in parts
            if part
        ]

        street = parts[0] if parts else None
        number = parts[1] if len(parts) > 1 else None
        neighborhood = (
            parts[-1]
            if len(parts) > 2
            else None
        )

        return {
            "street": street,
            "number": number,
            "neighborhood": neighborhood,
            "city": city.strip(),
            "state": state.strip(),
        }

    @staticmethod
    def extract_document_data(text: str) -> dict:
        number_match = re.search(
            r"Número:\s*(\d+)",
            text,
        )

        series_match = re.search(
            r"Série:\s*(\d+)",
            text,
        )

        issue_date_match = re.search(
            r"Emissão:\s*"
            r"(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})",
            text,
        )

        protocol_match = re.search(
            r"Protocolo de Autorização:\s*"
            r"(\d+)",
            text,
        )

        access_key_match = re.search(
            r"Chave de acesso:\s*"
            r"([\d\s]{44,})",
            text,
        )

        if not number_match:
            raise ValueError(
                "Número da NFC-e não encontrado."
            )

        if not series_match:
            raise ValueError(
                "Série da NFC-e não encontrada."
            )

        if not issue_date_match:
            raise ValueError(
                "Data de emissão não encontrada."
            )

        if not protocol_match:
            raise ValueError(
                "Protocolo de autorização não encontrado."
            )

        if not access_key_match:
            raise ValueError(
                "Chave de acesso não encontrada."
            )

        access_key = re.sub(
            r"\D",
            "",
            access_key_match.group(1),
        )

        return {
            "number": number_match.group(1),
            "series": series_match.group(1),
            "issued_at": datetime.strptime(
                issue_date_match.group(1),
                "%d/%m/%Y %H:%M:%S",
            ),
            "authorization_protocol": (
                protocol_match.group(1)
            ),
            "access_key": access_key,
        }

    # ------------------------------------------------------------------
    # Totals
    # ------------------------------------------------------------------

    @staticmethod
    def extract_totals(page: fitz.Page) -> dict:
        words = page.get_text("words")

        values = {}

        for word in words:
            x0, y0, x1, y1, text, *_ = word

            # Os valores ficam na coluna direita da tabela
            # de totais.
            if x0 < 400:
                continue

            if 345 <= y0 < 360:
                values["total_items"] = text

            elif 360 <= y0 < 374:
                values["total_amount"] = text

            elif 374 <= y0 < 386:
                values["discount"] = text

            elif 386 <= y0 < 403:
                values["amount_to_pay"] = text

        return {
            "total_items": int(
                values["total_items"]
            ),
            "total_amount": NFCePdfParser._parse_decimal(
                values["total_amount"]
            ),
            "discount": NFCePdfParser._parse_decimal(
                values["discount"]
            ),
            "amount_to_pay": NFCePdfParser._parse_decimal(
                values["amount_to_pay"]
            ),
        }

    # ------------------------------------------------------------------
    # Payment
    # ------------------------------------------------------------------

    @staticmethod
    def extract_payment(page: fitz.Page) -> dict:
        words = page.get_text("words")

        method = None
        amount_paid = None

        for word in words:
            x0, y0, x1, y1, text, *_ = word

            if 415 <= y0 < 427:
                if text not in ("Dinheiro",):
                    continue

                method = text

                break

        for word in words:
            x0, y0, x1, y1, text, *_ = word

            if (
                x0 > 400
                and 415 <= y0 < 427
                and NFCePdfParser._is_decimal(text)
            ):
                amount_paid = NFCePdfParser._parse_decimal(
                    text
                )

                break

        return {
            "method": method,
            "amount_paid": amount_paid,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_products(self) -> list[dict]:
        text = self._extract_text()

        return self.extract_products(text)

    def get_metadata(self) -> dict:
        document = self._open_document()

        try:
            if not document.page_count:
                raise ValueError(
                    "O PDF não possui páginas."
                )

            page = document[0]
            text = page.get_text("text")

            return {
                "store": self.extract_store(text),
                "document": self.extract_document_data(text),
                "totals": self.extract_totals(page),
                "payment": self.extract_payment(page),
            }

        finally:
            document.close()

    def get_data(self) -> dict:
        document = self._open_document()

        try:
            if not document.page_count:
                raise ValueError(
                    "O PDF não possui páginas."
                )

            page = document[0]
            text = page.get_text("text")

            return {
                "metadata": {
                    "store": self.extract_store(text),
                    "document": self.extract_document_data(text),
                    "totals": self.extract_totals(page),
                    "payment": self.extract_payment(page),
                },
                "products": self.extract_products(text),
            }

        finally:
            document.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_decimal(value: str) -> Decimal:
        return Decimal(
            value.replace(".", "").replace(",", ".")
        )

    @staticmethod
    def _is_decimal(value: str) -> bool:
        try:
            NFCePdfParser._parse_decimal(value)
            return True
        except Exception:
            return False
