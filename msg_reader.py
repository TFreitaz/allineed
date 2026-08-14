import symbols
from db.purchases import save_purchase
from nf_extractor import NFCeParser
from qr_reader import read_first_qr_code
from stock_estimator import estimate_remaining_for_user
from telegram_files import baixar_maior_foto_sync


class MsgReader:
    def __init__(self, msg: dict, user_id, message_id):
        self.msg = msg
        self.text = msg.get("text")  # pode não existir (ex.: mensagem de foto)
        self.user_id = user_id
        self.message_id = message_id

    def get_answer(self) -> str:
        """
        Retorna a resposta apropriada para a mensagem recebida.

        Permanece síncrono de propósito (facilita os testes). Quando chamado
        a partir do webhook, deve ser rodado em thread separada
        (asyncio.to_thread), já que o caminho de fotos faz I/O de rede e
        decodificação de imagem, que bloqueariam o event loop.
        """
        if "photo" in self.msg:
            return self.answer_qrcode_photo()

        if self.text is None:
            return "Não entendi essa mensagem. Me envie um link de NFC-e ou uma foto do QR code da nota."

        if self.text.startswith("/start"):
            return "Olá! Eu sou o Allineed. Me envie um link de NFC-e."

        if self.text.startswith("/report"):
            return self.answer_stock_estimator()

        return self.answer_nfe_link()

    def answer_qrcode_photo(self) -> str:
        """
        Caminho de resposta para fotos: baixa a imagem enviada pelo usuário
        (câmera ou galeria), procura um QR code nela e, se encontrar, segue
        o mesmo fluxo de extração/registro usado para links de NFC-e
        recebidos por texto.
        """
        foto_bytes = baixar_maior_foto_sync(self.msg)
        if foto_bytes is None:
            return "Não consegui baixar essa foto, pode tentar enviar de novo?"

        link = read_first_qr_code(foto_bytes)
        if link is None:
            return (
                f"{symbols.WARNING} Não encontrei nenhum QR code nessa foto. "
                "Tenta tirar de novo, mais de perto e com boa luz."
            )

        return self.process_nfe_link(link)

    def answer_stock_estimator(self):
        purchase_info = estimate_remaining_for_user(self.user_id)

        return self.format_stock_answer(purchase_info)

    def format_stock_answer(self, purchase_info):
        response_lines = [
            f"{symbols.SHOPPING_CART} <b>Produtos recorrentes:</b>",
            "",
        ]

        for product in purchase_info:
            status = f"{symbols.WARNING} baixo" if product.likely_depleted else "suficiente"

            products_lines = [
                f"<b>{product.product_name}</b> - {status}",
                f"Última compra: {product.last_purchase_quantity:.0f}{product.quantity_unit} "
                f"há {product.days_since_last_purchase:.1f} dias",
                ""
            ]

            response_lines.extend(products_lines)

        return "\n".join(response_lines)

    def answer_nfe_link(self):
        return self.process_nfe_link(self.text)

    def process_nfe_link(self, link: str) -> str:
        """
        Fluxo comum a texto e foto: recebe o link da NFC-e (já extraído,
        seja diretamente do texto ou decodificado do QR code), faz o parse,
        salva a compra e formata a resposta.
        """
        extractor = NFCeParser(link)
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