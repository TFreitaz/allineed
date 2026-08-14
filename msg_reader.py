from db.purchases import save_purchase
from nf_extractor import NFCeParser
from stock_estimator import estimate_remaining_for_user


class MsgReader:
    def __init__(self, msg: str, user_id, message_id):
        self.msg = msg
        self.text = msg["text"]
        self.user_id = user_id
        self.message_id = message_id

    def get_answer(self) -> str:
        """
        Retorna a resposta apropriada para a mensagem recebida.
        """
        if self.text.startswith("/start"):
            return "Olá! Eu sou o Allineed. Me envie um link de NFC-e."

        if self.text.startswith("/report"):
            return self.answer_stock_estimator()

        return self.answer_nfe_link()

    def answer_stock_estimator(self):
        purchase_info = estimate_remaining_for_user(self.user_id)

        response_lines = [
            "<b>Produtos recorrentes:</b> \U0001F6D2",
            "",
        ]

        for product in purchase_info:
            status = "baixo" if product.likely_depleted else "suficiente"

            products_lines = [
                f"<b>{product.product_name}</b> - {status}",
                f"Última compra: {product.last_purchase_quantity:.0f}{product.quantity_unit} "
                f"há {product.days_since_last_purchase:.1f} dias",
                ""
            ]

            response_lines.extend(products_lines)

        return "\n".join(response_lines)

    def answer_nfe_link(self):
        extractor = NFCeParser(self.text)
        data = extractor.get_data()

        save_purchase(user_id=self.user_id, data=data, source_message_id=self.message_id)

        return self.format_nfe_link_response(data)

    def format_nfe_link_response(self, data: dict) -> str:
        """
        Formata os dados extraídos da NFC-e em uma resposta legível.
        """
        metadata = data.get("metadata", {})
        products = data.get("products", [])

        response_lines = [
            "Compras registradas!",
            "",
            f"Loja: {metadata.get('store', {}).get('name', 'Não informada')}",
            f"Valor Total: R$ {metadata.get('totals', {}).get('amount_to_pay', 'Não informado')}",
            "",
            "Produtos comprados:",
            ""
        ]

        for product in products:
            response_lines.append(
                f"- {product['name']} ({product['quantity']} {product['unit']})"
            )

        return "\n".join(response_lines)

        