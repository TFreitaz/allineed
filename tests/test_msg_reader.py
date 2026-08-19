"""
Testes para MsgReader.

Dependências mockadas:
- db.purchases.save_purchase
- nf_extractor.nf_html_extractor.NFCeHtmlParser
- nf_extractor.nf_pdf_extractor.NFCePdfParser
- stock_estimator.estimate_remaining_for_user
- telegram_files.baixar_maior_foto_sync
- qr_reader.read_first_qr_code
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from msg_reader import MsgReader

VALID_NFCE_LINK = (
    "https://www.nfce.fazenda.sp.gov.br/qrcode"
    "?p=35260809418668000985651100001419741598860218|3|1"
)


def make_reader(
    msg: dict,
    user_id="user-1",
    message_id="msg-1",
) -> MsgReader:
    return MsgReader(
        msg=msg,
        user_id=user_id,
        message_id=message_id,
    )


def make_text_reader(
    text: str,
    user_id="user-1",
    message_id="msg-1",
) -> MsgReader:
    return make_reader(
        msg={"text": text},
        user_id=user_id,
        message_id=message_id,
    )


# ======================================================================
# Generic messages
# ======================================================================


class TestGenericMessages:
    def test_unknown_text_returns_default_message(self):
        reader = make_text_reader("Olá")

        answer = reader.get_answer()

        assert "Não entendi essa mensagem" in answer

    def test_message_without_text_returns_default_message(self):
        reader = make_reader({})

        answer = reader.get_answer()

        assert "Não entendi essa mensagem" in answer

    def test_start_command_returns_welcome_message(self):
        reader = make_text_reader("/start")

        answer = reader.get_answer()

        assert "Allineed" in answer

    def test_start_command_with_additional_text_returns_welcome_message(self):
        reader = make_text_reader("/start qualquer coisa")

        answer = reader.get_answer()

        assert "Allineed" in answer


# ======================================================================
# Stock report
# ======================================================================


class TestReportCommand:
    @patch("msg_reader.estimate_remaining_for_user")
    def test_report_with_products(self, mock_estimate):
        mock_estimate.return_value = [
            SimpleNamespace(
                product_name="Arroz",
                likely_depleted=True,
                last_purchase_quantity=5.0,
                quantity_unit="kg",
                days_since_last_purchase=30.0,
            ),
            SimpleNamespace(
                product_name="Feijão",
                likely_depleted=False,
                last_purchase_quantity=1.0,
                quantity_unit="kg",
                days_since_last_purchase=3.0,
            ),
        ]

        reader = make_text_reader("/report")

        answer = reader.get_answer()

        mock_estimate.assert_called_once_with("user-1")

        assert "Arroz" in answer
        assert "Feijão" in answer
        assert "baixo" in answer
        assert "suficiente" in answer

    @patch("msg_reader.estimate_remaining_for_user")
    def test_report_with_no_products(self, mock_estimate):
        mock_estimate.return_value = []

        reader = make_text_reader("/report")

        answer = reader.get_answer()

        mock_estimate.assert_called_once_with("user-1")

        assert "Produtos recorrentes:" in answer

    @patch("msg_reader.estimate_remaining_for_user")
    def test_report_converts_grams_to_kg(self, mock_estimate):
        mock_estimate.return_value = [
            SimpleNamespace(
                product_name="Arroz",
                likely_depleted=True,
                last_purchase_quantity=5000,
                quantity_unit="g",
                days_since_last_purchase=30.0,
            ),
            SimpleNamespace(
                product_name="Batata",
                likely_depleted=True,
                last_purchase_quantity=1000,
                quantity_unit="g",
                days_since_last_purchase=30.0,
            ),
            SimpleNamespace(
                product_name="Feijão",
                likely_depleted=True,
                last_purchase_quantity=800,
                quantity_unit="g",
                days_since_last_purchase=30.0,
            ),
        ]

        reader = make_text_reader("/report")

        answer = reader.get_answer()

        assert "5kg" in answer
        assert "1kg" in answer
        assert "800g" in answer

    @patch("msg_reader.estimate_remaining_for_user")
    def test_report_converts_ml_to_liters(self, mock_estimate):
        mock_estimate.return_value = [
            SimpleNamespace(
                product_name="Leite Integral",
                likely_depleted=False,
                last_purchase_quantity=2000,
                quantity_unit="ml",
                days_since_last_purchase=3.0,
            ),
            SimpleNamespace(
                product_name="Leite Zero Lactose",
                likely_depleted=False,
                last_purchase_quantity=1000,
                quantity_unit="ml",
                days_since_last_purchase=3.0,
            ),
            SimpleNamespace(
                product_name="Leite Desnatado",
                likely_depleted=False,
                last_purchase_quantity=800,
                quantity_unit="ml",
                days_since_last_purchase=3.0,
            ),
        ]

        reader = make_text_reader("/report")

        answer = reader.get_answer()

        assert "2L" in answer
        assert "1L" in answer
        assert "800ml" in answer

    @patch("msg_reader.estimate_remaining_for_user")
    def test_report_day_labels(self, mock_estimate):
        mock_estimate.return_value = [
            SimpleNamespace(
                product_name="Hoje",
                likely_depleted=True,
                last_purchase_quantity=1,
                quantity_unit="un",
                days_since_last_purchase=(24 - 7 - 0.01) / 24,
            ),
            SimpleNamespace(
                product_name="Ontem",
                likely_depleted=False,
                last_purchase_quantity=2,
                quantity_unit="un",
                days_since_last_purchase=(24 - 7) / 24,
            ),
            SimpleNamespace(
                product_name="Ontem2",
                likely_depleted=True,
                last_purchase_quantity=3,
                quantity_unit="un",
                days_since_last_purchase=(48 - 7 - 0.01) / 24,
            ),
            SimpleNamespace(
                product_name="DoisDias",
                likely_depleted=True,
                last_purchase_quantity=4,
                quantity_unit="un",
                days_since_last_purchase=(49 - 7) / 24,
            ),
            SimpleNamespace(
                product_name="TresDias",
                likely_depleted=False,
                last_purchase_quantity=5,
                quantity_unit="un",
                days_since_last_purchase=72 / 24,
            ),
        ]

        reader = make_text_reader("/report")

        answer = reader.get_answer()

        assert "1un hoje" in answer
        assert "2un ontem" in answer
        assert "3un ontem" in answer
        assert "4un há 2 dias" in answer
        assert "5un há 3 dias" in answer


# ======================================================================
# QR Code / Photo
# ======================================================================


class TestPhotoFlow:
    @patch("msg_reader.read_first_qr_code")
    @patch("msg_reader.baixar_maior_foto_sync")
    @patch("msg_reader.MsgReader.process_nfe_link")
    def test_photo_with_qr_code_processes_link(
        self,
        mock_process,
        mock_download,
        mock_qr,
    ):
        mock_download.return_value = b"image-content"
        mock_qr.return_value = "https://nfce.example.com/123"
        mock_process.return_value = "Compra registrada!"

        reader = make_reader(
            {
                "photo": [
                    {"file_id": "small"},
                    {"file_id": "large"},
                ]
            }
        )

        answer = reader.get_answer()

        mock_download.assert_called_once_with(reader.msg)
        mock_qr.assert_called_once_with(b"image-content")
        mock_process.assert_called_once_with(
            "https://nfce.example.com/123"
        )

        assert answer == "Compra registrada!"

    @patch("msg_reader.baixar_maior_foto_sync")
    def test_photo_download_failure_returns_error(
        self,
        mock_download,
    ):
        mock_download.return_value = None

        reader = make_reader(
            {
                "photo": [
                    {"file_id": "large"},
                ]
            }
        )

        answer = reader.get_answer()

        assert "Não consegui baixar essa foto" in answer

    @patch("msg_reader.read_first_qr_code")
    @patch("msg_reader.baixar_maior_foto_sync")
    def test_photo_without_qr_code_returns_warning(
        self,
        mock_download,
        mock_qr,
    ):
        mock_download.return_value = b"image-content"
        mock_qr.return_value = None

        reader = make_reader(
            {
                "photo": [
                    {"file_id": "large"},
                ]
            }
        )

        answer = reader.get_answer()

        mock_download.assert_called_once_with(reader.msg)
        mock_qr.assert_called_once_with(b"image-content")

        assert "QR code" in answer


# ======================================================================
# PDF
# ======================================================================


class TestPdfFlow:
    def make_pdf_document(self):
        return SimpleNamespace(
            mime_type="application/pdf",
        )

    @patch("msg_reader.MsgReader.answer_pdf")
    def test_pdf_document_is_routed_to_pdf_handler(
        self,
        mock_answer_pdf,
    ):
        document = self.make_pdf_document()

        mock_answer_pdf.return_value = "PDF processado!"

        reader = make_reader(
            {
                "document": document,
            }
        )

        answer = reader.get_answer()

        mock_answer_pdf.assert_called_once_with(document)

        assert answer == "PDF processado!"

    @patch("msg_reader.MsgReader.answer_pdf")
    def test_non_pdf_document_is_not_sent_to_pdf_handler(
        self,
        mock_answer_pdf,
    ):
        document = SimpleNamespace(
            mime_type="application/zip",
        )

        reader = make_reader(
            {
                "document": document,
            }
        )

        answer = reader.get_answer()

        mock_answer_pdf.assert_not_called()

        assert "Não entendi essa mensagem" in answer

    @patch("msg_reader.MsgReader.answer_pdf")
    def test_photo_has_priority_over_pdf(
        self,
        mock_answer_pdf,
    ):
        document = self.make_pdf_document()

        reader = make_reader(
            {
                "photo": [{"file_id": "photo"}],
                "document": document,
            }
        )

        with patch.object(
            reader,
            "answer_qrcode_photo",
            return_value="Foto processada!",
        ) as mock_photo:
            answer = reader.get_answer()

        mock_photo.assert_called_once()
        mock_answer_pdf.assert_not_called()

        assert answer == "Foto processada!"

    @patch("msg_reader.save_purchase")
    @patch("msg_reader.NFCePdfParser")
    def test_pdf_is_parsed_saved_and_formatted(
        self,
        mock_parser_cls,
        mock_save_purchase,
    ):
        fake_data = {
            "metadata": {
                "store": {
                    "name": "Mercado PDF",
                },
                "totals": {
                    "amount_to_pay": "55,90",
                },
            },
            "products": [
                {
                    "name": "Leite",
                    "quantity": 2,
                    "unit": "un",
                },
            ],
        }

        mock_parser = MagicMock()
        mock_parser.get_data.return_value = fake_data
        mock_parser_cls.return_value = mock_parser

        pdf_bytes = bytearray(b"fake-pdf")

        telegram_file = MagicMock()
        telegram_file.download_as_bytearray.return_value = pdf_bytes

        document = MagicMock()
        document.mime_type = "application/pdf"
        document.get_file.return_value = telegram_file

        reader = make_reader(
            {
                "document": document,
            }
        )

        answer = reader.get_answer()

        mock_parser_cls.assert_called_once_with(pdf_bytes)

        mock_parser.get_data.assert_called_once()

        mock_save_purchase.assert_called_once_with(
            user_id="user-1",
            data=fake_data,
            source_message_id="msg-1",
        )

        assert "Compras registradas!" in answer
        assert "Mercado PDF" in answer
        assert "55,90" in answer
        assert "Leite" in answer

    @patch("msg_reader.NFCePdfParser")
    def test_pdf_downloads_document_content(
        self,
        mock_parser_cls,
    ):
        fake_data = {
            "metadata": {
                "store": {"name": "Mercado"},
                "totals": {"amount_to_pay": "10,00"},
            },
            "products": [],
        }

        mock_parser = MagicMock()
        mock_parser.get_data.return_value = fake_data
        mock_parser_cls.return_value = mock_parser

        pdf_bytes = bytearray(b"pdf-content")

        telegram_file = MagicMock()
        telegram_file.download_as_bytearray.return_value = pdf_bytes

        document = MagicMock()
        document.get_file.return_value = telegram_file

        reader = make_text_reader("qualquer texto")

        with patch("msg_reader.save_purchase"):
            reader.answer_pdf(document)

        document.get_file.assert_called_once()

        telegram_file.download_as_bytearray.assert_called_once()

        mock_parser_cls.assert_called_once_with(
            pdf_bytes
        )

    @patch("msg_reader.save_purchase")
    @patch("msg_reader.NFCePdfParser")
    def test_pdf_uses_same_source_message_id(
        self,
        mock_parser_cls,
        mock_save_purchase,
    ):
        fake_data = {
            "metadata": {
                "store": {"name": "Mercado"},
                "totals": {"amount_to_pay": "10,00"},
            },
            "products": [],
        }

        mock_parser = MagicMock()
        mock_parser.get_data.return_value = fake_data
        mock_parser_cls.return_value = mock_parser

        pdf_bytes = bytearray(b"pdf")

        telegram_file = MagicMock()
        telegram_file.download_as_bytearray.return_value = pdf_bytes

        document = MagicMock()
        document.get_file.return_value = telegram_file

        reader = make_reader(
            {"document": document},
            user_id="user-99",
            message_id="message-123",
        )

        reader.answer_pdf(document)

        mock_save_purchase.assert_called_once_with(
            user_id="user-99",
            data=fake_data,
            source_message_id="message-123",
        )


# ======================================================================
# NFC-e link
# ======================================================================


class TestNfeLinkFlow:
    @patch("msg_reader.save_purchase")
    @patch("msg_reader.NFCeHtmlParser")
    def test_nfe_link_saves_purchase_and_formats_response(
        self,
        mock_parser_cls,
        mock_save_purchase,
    ):
        fake_data = {
            "metadata": {
                "store": {
                    "name": "Mercado Teste",
                },
                "totals": {
                    "amount_to_pay": "42,50",
                },
            },
            "products": [
                {
                    "name": "Leite",
                    "quantity": 2,
                    "unit": "un",
                },
                {
                    "name": "Pão",
                    "quantity": 1,
                    "unit": "kg",
                },
            ],
        }

        mock_parser = MagicMock()
        mock_parser.get_data.return_value = fake_data
        mock_parser_cls.return_value = mock_parser

        reader = make_text_reader(VALID_NFCE_LINK)

        answer = reader.get_answer()

        mock_parser_cls.assert_called_once_with(VALID_NFCE_LINK)

        mock_parser.get_data.assert_called_once()

        mock_save_purchase.assert_called_once_with(
            user_id="user-1",
            data=fake_data,
            source_message_id="msg-1",
        )

        assert "Compras registradas!" in answer
        assert "Mercado Teste" in answer
        assert "42,50" in answer
        assert "Leite" in answer
        assert "Pão" in answer

    @patch("msg_reader.NFCeHtmlParser")
    def test_nfe_link_returns_error_when_data_is_empty(
        self,
        mock_parser_cls,
    ):
        fake_data = {"products": []}

        mock_parser_instance = MagicMock()
        mock_parser_instance.get_data.return_value = None
        mock_parser_cls.return_value = mock_parser_instance

        reader = make_text_reader(VALID_NFCE_LINK)

        answer = reader.get_answer()

        mock_parser_cls.assert_called_once_with(VALID_NFCE_LINK)
        mock_parser_instance.get_data.assert_called_once()

        assert "não está acessível" in answer
        assert "CPF/CNPJ" in answer
        assert "baixe o PDF" in answer

    @patch("msg_reader.save_purchase")
    @patch("msg_reader.NFCeHtmlParser")
    def test_qrcode_link_uses_same_nfe_flow(
        self,
        mock_parser_cls,
        mock_save_purchase,
    ):
        fake_data = {
            "metadata": {
                "store": {
                    "name": "Mercado QR",
                },
                "totals": {
                    "amount_to_pay": "30,00",
                },
            },
            "products": [],
        }

        mock_parser = MagicMock()
        mock_parser.get_data.return_value = fake_data
        mock_parser_cls.return_value = mock_parser

        reader = make_text_reader("texto")

        answer = reader.process_nfe_link(VALID_NFCE_LINK)

        mock_parser_cls.assert_called_once_with(VALID_NFCE_LINK)

        mock_save_purchase.assert_called_once_with(
            user_id="user-1",
            data=fake_data,
            source_message_id="msg-1",
        )

        assert "Compras registradas!" in answer


# ======================================================================
# Response formatting
# ======================================================================


class TestResponseFormatting:
    def test_format_nfe_response_with_complete_data(self):
        reader = make_text_reader("texto")

        data = {
            "metadata": {
                "store": {
                    "name": "Mercado Teste",
                },
                "totals": {
                    "amount_to_pay": "42,50",
                },
            },
            "products": [
                {
                    "name": "Arroz",
                    "quantity": 5,
                    "unit": "kg",
                },
                {
                    "name": "Leite",
                    "quantity": 2,
                    "unit": "un",
                },
            ],
        }

        answer = reader.format_nfe_link_response(data)

        assert "Compras registradas!" in answer
        assert "Mercado Teste" in answer
        assert "42,50" in answer
        assert "Arroz" in answer
        assert "5 kg" in answer
        assert "Leite" in answer
        assert "2 un" in answer

    def test_format_nfe_response_missing_metadata_uses_defaults(self):
        reader = make_text_reader("texto")

        data = {
            "products": [],
        }

        answer = reader.format_nfe_link_response(data)

        assert "Não informada" in answer
        assert "Não informado" in answer

    def test_format_nfe_response_without_products(self):
        reader = make_text_reader("texto")

        data = {
            "metadata": {
                "store": {
                    "name": "Mercado Teste",
                },
                "totals": {
                    "amount_to_pay": "10,00",
                },
            },
            "products": [],
        }

        answer = reader.format_nfe_link_response(data)

        assert "Produtos comprados:" in answer
        assert "Mercado Teste" in answer


# ======================================================================
# URL detection
# ======================================================================


class TestNfeUrlDetection:
    @pytest.mark.parametrize(
        "text",
        [
            (
                "https://www.nfce.fazenda.sp.gov.br/qrcode"
                "?p=35260809418668000985651100001419741598860218|3|1"
            ),
            (
                "https://www.nfce.fazenda.sp.gov.br/"
                "NFCeConsultaPublica/Paginas/ConsultaQRCode.aspx"
                "?p=35260850306190000148653040000648501001101421|2|1|1|"
                "6523a61645fde27c8247f7b65484b17b6e7abfee"
            ),
            (
                "https://www.nfce.fazenda.sp.gov.br/"
                "NFCeConsultaPublica/Paginas/ConsultaQRCode.aspx"
                "?p=35260850306190000571653010000472851000865534|2|1|1|"
                "eac3173be9cdec68eefe111d82d70b4a120712f2"
            ),
        ],
    )
    def test_nfe_url_detection_accepts_expected_text(
        self,
        text,
    ):
        reader = make_text_reader(text)

        assert reader._is_nfe_url(text)

    @pytest.mark.parametrize(
        "text",
        [
            "https://nfce.fazenda.sp.gov.br/consulta",
            "https://www.nfce.fazenda.sp.gov.br/teste",
            "https://google.com/qrcode?p=35260809418668000985651100001419741598860218|3|1",
            "https://www.nfce.fazenda.sp.gov.br/qrcode",
            "https://www.nfce.fazenda.sp.gov.br/qrcode?p=123|3|1",
            "https://www.nfce.fazenda.sp.gov.br/qrcode?p=abc|3|1",
            "nota nfce",
            "texto qualquer",
        ],
    )
    def test_nfe_url_detection_rejects_invalid_urls(
        self,
        text,
    ):
        reader = make_text_reader(text)

        assert not reader._is_nfe_url(text)