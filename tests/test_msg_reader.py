"""
Testes básicos para MsgReader.

Assumindo que a classe MsgReader está definida em `msg_reader.py`
(ajuste o import abaixo se o arquivo/módulo tiver outro nome/caminho).

Dependências mockadas:
- db.purchases.save_purchase  -> evita gravação real no banco
- nf_extractor.NFCeParser     -> evita parsing real de NFC-e
- stock_estimator.estimate_remaining_for_user -> evita cálculo real de estoque
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from msg_reader import MsgReader


def make_reader(text: str, user_id="user-1", message_id="msg-1") -> MsgReader:
    """Helper para instanciar MsgReader com uma mensagem simulada."""
    return MsgReader(msg={"text": text}, user_id=user_id, message_id=message_id)


class TestStartCommand:
    def test_start_returns_welcome_message(self):
        reader = make_reader("/start")
        answer = reader.get_answer()
        assert "Allineed" in answer


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

        reader = make_reader("/report")
        answer = reader.get_answer()

        mock_estimate.assert_called_once_with("user-1")
        assert "Arroz" in answer
        assert "Feijão" in answer
        assert "baixo" in answer
        assert "suficiente" in answer

    @patch("msg_reader.estimate_remaining_for_user")
    def test_report_with_no_products(self, mock_estimate):
        mock_estimate.return_value = []

        reader = make_reader("/report")
        answer = reader.get_answer()

        assert "Produtos recorrentes:" in answer

    @patch("msg_reader.estimate_remaining_for_user")
    def test_report_unit_aggregation(self, mock_estimate):
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

        reader = make_reader("/report")
        answer = reader.get_answer()

        mock_estimate.assert_called_once_with("user-1")
        assert "5kg" in answer
        assert "1kg" in answer
        assert "800g" in answer
        assert "2L" in answer
        assert "1L" in answer
        assert "800ml" in answer

    @patch("msg_reader.estimate_remaining_for_user")
    def test_report_unit_aggregation(self, mock_estimate):
            mock_estimate.return_value = [
                SimpleNamespace(
                    product_name="Feijão",
                    likely_depleted=True,
                    last_purchase_quantity=1,
                    quantity_unit="g",
                    days_since_last_purchase=(24 - 7 - 0.01) / 24,  # Bough at 7h, asked at 23h59
                ),
                SimpleNamespace(
                    product_name="Leite Integral",
                    likely_depleted=False,
                    last_purchase_quantity=2,
                    quantity_unit="g",
                    days_since_last_purchase=(24 - 7) / 24,  # Bough at 7h, asked at 0h next day
                ),
                SimpleNamespace(
                    product_name="Leite Desnatado",
                    likely_depleted=True,
                    last_purchase_quantity=3,
                    quantity_unit="g",
                    days_since_last_purchase=(48 - 7 - 0.01) / 24,  # Bough at 7h, asked at 23:59 next day
                ),
                SimpleNamespace(
                    product_name="Macarrão",
                    likely_depleted=True,
                    last_purchase_quantity=4,
                    quantity_unit="g",
                    days_since_last_purchase=(49 - 7) / 24,  # Bough at 7h, asked at 0h two days after
                ),
                SimpleNamespace(
                    product_name="Calabresa",
                    likely_depleted=False,
                    last_purchase_quantity=5,
                    quantity_unit="g",
                    days_since_last_purchase=72 / 24,  # Asked three days after buying
                ),
            ]
    
            reader = make_reader("/report")
            answer = reader.get_answer()
    
            mock_estimate.assert_called_once_with("user-1")
            assert "1g hoje" in answer
            assert "2g ontem" in answer
            assert "3g ontem" in answer
            assert "4g há 2 dias" in answer
            assert "5g há 3 dias" in answer


class TestNfeLinkFlow:
    @patch("msg_reader.save_purchase")
    @patch("msg_reader.NFCeParser")
    def test_nfe_link_saves_purchase_and_formats_response(
        self, mock_parser_cls, mock_save_purchase
    ):
        fake_data = {
            "metadata": {
                "store": {"name": "Mercado Teste"},
                "totals": {"amount_to_pay": "42,50"},
            },
            "products": [
                {"name": "Leite", "quantity": 2, "unit": "un"},
                {"name": "Pão", "quantity": 1, "unit": "kg"},
            ],
        }

        mock_parser_instance = MagicMock()
        mock_parser_instance.get_data.return_value = fake_data
        mock_parser_cls.return_value = mock_parser_instance

        reader = make_reader("https://fake-nfce-link.com/abc123")
        answer = reader.get_answer()

        # Parser foi instanciado com o texto da mensagem
        mock_parser_cls.assert_called_once_with("https://fake-nfce-link.com/abc123")

        # Compra foi salva com os dados extraídos
        mock_save_purchase.assert_called_once_with(
            user_id="user-1", data=fake_data, source_message_id="msg-1"
        )

        # Resposta formatada corretamente
        assert "Compras registradas!" in answer
        assert "Mercado Teste" in answer
        assert "42,50" in answer
        assert "Leite" in answer
        assert "Pão" in answer

    @patch("msg_reader.save_purchase")
    @patch("msg_reader.NFCeParser")
    def test_nfe_link_missing_metadata_uses_defaults(
        self, mock_parser_cls, mock_save_purchase
    ):
        fake_data = {"products": []}

        mock_parser_instance = MagicMock()
        mock_parser_instance.get_data.return_value = fake_data
        mock_parser_cls.return_value = mock_parser_instance

        reader = make_reader("https://fake-nfce-link.com/xyz")
        answer = reader.get_answer()

        assert "Não informada" in answer
        assert "Não informado" in answer