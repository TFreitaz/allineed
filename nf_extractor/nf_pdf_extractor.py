import re
from datetime import datetime
from decimal import Decimal

import fitz


class NFCePdfParser:
    def __init__(self, pdf_content: bytes | bytearray):
        self.pdf_content = pdf_content

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------

    def _open_document(self) -> fitz.Document:
        return fitz.open(
            stream=self.pdf_content,
            filetype="pdf",
        )

    def _extract_text(self) -> str:
        document = self._open_document()

        try:
            if not document.page_count:
                raise ValueError(
                    "O PDF não possui páginas."
                )

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
            Qtde\.\s*:\s*(?P<quantity>[\d.,]+)
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
    # Metadata - Store
    # ------------------------------------------------------------------

    @staticmethod
    def extract_store(text: str) -> dict:
        """
        Extracts store information from the block:

        STORE NAME
        CNPJ: XX.XXX.XXX/XXXX-XX
        STREET, NUMBER, ..., NEIGHBORHOOD,
        CITY, STATE
        """

        match = re.search(
            r"""
            ^(?P<name>[^\n]+)
            \n
            CNPJ:\s*(?P<cnpj>[\d./-]+)
            \n
            (?P<address>[^\n]+)
            \n
            (?P<city>[^\n]+)
            """,
            text,
            re.MULTILINE | re.VERBOSE,
        )

        if not match:
            raise ValueError(
                "Não foi possível identificar os dados da loja."
            )

        name = match.group("name").strip()
        cnpj = match.group("cnpj").strip()
        address = match.group("address").strip()

        city_line = match.group("city").strip()

        city_match = re.match(
            r"(?P<city>.+?)\s*,\s*(?P<state>[A-Z]{2})$",
            city_line,
        )

        if not city_match:
            raise ValueError(
                "Não foi possível identificar cidade e estado."
            )

        city = city_match.group("city")
        state = city_match.group("state")

        return {
            "name": name,
            "cnpj": cnpj,
            "address": NFCePdfParser._extract_address(
                address,
                city,
                state,
            ),
        }

    @staticmethod
    def _extract_address(
        address: str,
        city: str,
        state: str,
    ) -> dict:
        """
        Parses an address such as:

        AVENIDA GOVERNADOR ORESTES QUERCIA , 155 , ,
        JD MARAJOARA ,
        """

        parts = [
            part.strip()
            for part in address.split(",")
            if part.strip()
        ]

        street = parts[0] if parts else None
        number = parts[1] if len(parts) > 1 else None
        neighborhood = parts[-1] if len(parts) > 2 else None

        return {
            "street": street,
            "number": number,
            "neighborhood": neighborhood,
            "city": city.strip(),
            "state": state.strip(),
        }

    # ------------------------------------------------------------------
    # Metadata - Document
    # ------------------------------------------------------------------

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
            r"Protocolo de Autorização:\s*(\d+)",
            text,
        )

        access_key_match = re.search(
            r"Chave de acesso:\s*\n?"
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

        if len(access_key) != 44:
            raise ValueError(
                "Chave de acesso inválida."
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
    # Metadata - Totals
    # ------------------------------------------------------------------

    @staticmethod
    def extract_totals(page: fitz.Page) -> dict:
        """
        Extracts invoice totals from the PDF text.

        The labels and their values are located on the same visual line,
        for example:

            Qtd. total de itens: 10
            Valor total R$: 129,29
            Descontos R$: 16,57
            Valor a pagar R$: 112,72
        """

        words = page.get_text("words")
        lines = NFCePdfParser._group_words_by_line(words)

        patterns = {
            "total_items": re.compile(
                r"^Qtd\.\s*total\s*de\s*itens:\s*"
                r"(?P<value>\d+)\s*$",
                re.IGNORECASE,
            ),
            "total_amount": re.compile(
                r"^Valor\s*total\s*R\$:\s*"
                r"(?P<value>[\d.,]+)\s*$",
                re.IGNORECASE,
            ),
            "discount": re.compile(
                r"^Descontos\s*R\$:\s*"
                r"(?P<value>[\d.,]+)\s*$",
                re.IGNORECASE,
            ),
            "amount_to_pay": re.compile(
                r"^Valor\s*a\s*pagar\s*R\$:\s*"
                r"(?P<value>[\d.,]+)\s*$",
                re.IGNORECASE,
            ),
        }

        values = {}

        for line in lines:
            line_text = " ".join(
                word["text"]
                for word in line
            )

            line_text = re.sub(
                r"\s+",
                " ",
                line_text,
            ).strip()

            for key, pattern in patterns.items():
                match = pattern.match(line_text)

                if match:
                    values[key] = match.group("value")
                    break

        required = {
            "total_items",
            "total_amount",
            "discount",
            "amount_to_pay",
        }

        missing = required - values.keys()

        if missing:
            raise ValueError(
                "Não foi possível extrair os totais: "
                + ", ".join(sorted(missing))
            )

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
    # Metadata - Payment
    # ------------------------------------------------------------------

    @staticmethod
    def extract_payment(page: fitz.Page) -> dict:
        """
        Extracts payment method and paid amount.

        The PDF contains two columns:

            Forma de pagamento:        Valor pago R$:
            Dinheiro                   112,72
            Troco                      NaN

        The payment amount is positioned before the final "R$:"
        label word, so the complete label position must be considered.
        """

        words = page.get_text("words")

        payment_label_words = []
        amount_label_words = []

        # --------------------------------------------------------------
        # Find labels
        # --------------------------------------------------------------

        for word in words:
            x0, y0, x1, y1, text, *_ = word

            if text == "Forma":
                candidates = [
                    candidate
                    for candidate in words
                    if (
                        abs(candidate[1] - y0) <= 2
                        and candidate[0] >= x0
                        and candidate[0] < x1 + 100
                    )
                ]

                candidates.sort(
                    key=lambda candidate: candidate[0]
                )

                candidate_text = " ".join(
                    candidate[4]
                    for candidate in candidates
                )

                if candidate_text.startswith(
                    "Forma de pagamento:"
                ):
                    payment_label_words = candidates[:3]
                    break

        for word in words:
            x0, y0, x1, y1, text, *_ = word

            if text != "Valor":
                continue

            candidates = [
                candidate
                for candidate in words
                if (
                    abs(candidate[1] - y0) <= 2
                    and candidate[0] >= x0
                    and candidate[0] < x0 + 100
                )
            ]

            candidates.sort(
                key=lambda candidate: candidate[0]
            )

            candidate_text = " ".join(
                candidate[4]
                for candidate in candidates
            )

            if candidate_text.startswith("Valor pago R$:"):
                amount_label_words = candidates[:3]
                break

        if not payment_label_words:
            raise ValueError(
                "Forma de pagamento não encontrada."
            )

        if not amount_label_words:
            raise ValueError(
                "Valor pago não encontrado."
            )

        # --------------------------------------------------------------
        # Payment method
        # --------------------------------------------------------------

        payment_label_x0 = min(
            word[0]
            for word in payment_label_words
        )

        payment_label_x1 = max(
            word[2]
            for word in payment_label_words
        )

        payment_label_y1 = max(
            word[3]
            for word in payment_label_words
        )

        method_candidates = []

        for word in words:
            x0, y0, x1, y1, text, *_ = word

            if y0 <= payment_label_y1:
                continue

            if y0 - payment_label_y1 > 15:
                continue

            if x0 < payment_label_x0:
                continue

            if x1 > payment_label_x1 + 5:
                continue

            if NFCePdfParser._is_decimal(text):
                continue

            if text == "Troco":
                continue

            method_candidates.append(word)

        if not method_candidates:
            raise ValueError(
                "Método de pagamento não encontrado."
            )

        method_candidates.sort(
            key=lambda word: (
                word[1],
                word[0],
            )
        )

        method = method_candidates[0][4]

        # --------------------------------------------------------------
        # Amount paid
        # --------------------------------------------------------------

        amount_label_x0 = min(
            word[0]
            for word in amount_label_words
        )

        amount_label_y1 = max(
            word[3]
            for word in amount_label_words
        )

        amount_candidates = []

        for word in words:
            x0, y0, x1, y1, text, *_ = word

            if y0 <= amount_label_y1:
                continue

            if y0 - amount_label_y1 > 15:
                continue

            # The value must be below the complete
            # "Valor pago R$:" label.
            if x0 < amount_label_x0:
                continue

            if not NFCePdfParser._is_decimal(text):
                continue

            amount_candidates.append(word)

        if not amount_candidates:
            raise ValueError(
                "Valor pago não encontrado."
            )

        amount_candidates.sort(
            key=lambda word: (
                word[1],
                word[0],
            )
        )

        amount_paid = NFCePdfParser._parse_decimal(
            amount_candidates[0][4]
        )

        return {
            "method": method,
            "amount_paid": amount_paid,
        }

    # ------------------------------------------------------------------
    # Helpers - PDF lines
    # ------------------------------------------------------------------

    @staticmethod
    def _group_words_by_line(
        words: list[tuple],
        tolerance: float = 2.0,
    ) -> list[list[dict]]:
        """
        Groups PyMuPDF words into visual lines based on their y
        coordinates.
        """

        sorted_words = sorted(
            words,
            key=lambda word: (
                word[1],
                word[0],
            ),
        )

        lines = []

        for word in sorted_words:
            x0, y0, x1, y1, text, *_ = word

            if not lines:
                lines.append([])

            current_line = lines[-1]

            if not current_line:
                current_line.append(
                    {
                        "x0": x0,
                        "y0": y0,
                        "x1": x1,
                        "y1": y1,
                        "text": text,
                    }
                )
                continue

            reference_y = current_line[0]["y0"]

            if abs(y0 - reference_y) <= tolerance:
                current_line.append(
                    {
                        "x0": x0,
                        "y0": y0,
                        "x1": x1,
                        "y1": y1,
                        "text": text,
                    }
                )
            else:
                lines.append(
                    [
                        {
                            "x0": x0,
                            "y0": y0,
                            "x1": x1,
                            "y1": y1,
                            "text": text,
                        }
                    ]
                )

        for line in lines:
            line.sort(key=lambda word: word["x0"])

        return lines

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
    # Helpers - Values
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
