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

        extractor = NFCeParser(self.msg)
        data = extractor.get_data()
        return self.format_response(data)

    def format_response(self, data: dict) -> str:
        """
        Formata os dados extraídos da NFC-e em uma resposta legível.
        """
        metadata = data.get("metadata", {})
        products = data.get("products", [])

        response_lines = [
            f"Estabelecimento: {metadata.get('store', {}).get('name', 'N/A')}",
            f"CNPJ: {metadata.get('store', {}).get('cnpj', 'N/A')}",
            f"Chave de Acesso: {metadata.get('access_key', 'N/A')}",
            f"Data de Emissão: {metadata.get('issue_date', 'N/A')}",
            f"Valor Total: {metadata.get('total_value', 'N/A')}",
            f"Valor a Pagar: {metadata.get('amount_to_pay', 'N/A')}",
            f"Forma de Pagamento: {metadata.get('payment_method', 'N/A')}",
            f"Valor Pago: {metadata.get('amount_paid', 'N/A')}",
            "",
            "Produtos:",
        ]

        for product in products:
            response_lines.append(
                f"- {product['name']} | Quantidade: {product['quantity']} | Valor Unitário: {product['unit_price']} | Valor Total: {product['total_price']}"
            )

        return "\n".join(response_lines)

        