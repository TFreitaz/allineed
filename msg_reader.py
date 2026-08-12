from db.purchases import save_purchase
from nf_extractor import NFCeParser


class MsgReader:
    def __init__(self, msg: str):
        self.msg = msg

    def get_answer(self) -> str:
        """
        Retorna a resposta apropriada para a mensagem recebida.
        """
        if self.msg.startswith("/start"):
            return "Olá! Eu sou o Allineed. Me envie um link de NFC-e."

        return self.answer_nfe_link()

    def answer_nfe_link(self):
        extractor = NFCeParser(self.msg)
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
            f"Valor Total: R$ {metadata.get('total_value', 'Não informado')}",
            "",
            "Produtos comprados:",
            ""
        ]

        for product in products:
            response_lines.append(
                f"- {product['name']} ({product['quantity']} {product['unit']})"
            )

        return "\n".join(response_lines)

        