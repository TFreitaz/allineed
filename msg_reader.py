import logging
from urllib.parse import parse_qs, urlparse

import symbols
from db.purchases import save_purchase
from nf_extractor.nf_html_extractor import NFCeHtmlParser
from nf_extractor.nf_pdf_extractor import NFCePdfParser
from qr_reader import read_first_qr_code
from stock_estimator import estimate_remaining_for_user
from telegram_files import baixar_maior_foto_sync
from telegram_files import (
    baixar_maior_foto_sync,
    download_document_sync,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telegram-echo-bot")


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
        logger.info(
            "Processing message: user_id=%s, message_id=%s, keys=%s",
            self.user_id,
            self.message_id,
            list(self.msg.keys()),
        )

        # ------------------------------------------------------------------
        # Photo
        # ------------------------------------------------------------------

        has_photo = "photo" in self.msg

        logger.info(
            "Photo check: present=%s",
            has_photo,
        )

        if has_photo:
            logger.info(
                "Message identified as photo. "
                "Routing to QR code reader."
            )

            return self.answer_qrcode_photo()

        # ------------------------------------------------------------------
        # Document
        # ------------------------------------------------------------------

        document = self.msg.get("document")

        logger.info(
            "Document check: present=%s",
            document is not None,
        )

        if document is not None:
            mime_type = document.get("mime_type")

            logger.info(
                "Document detected: mime_type=%s",
                mime_type,
            )

            is_pdf = mime_type == "application/pdf"

            logger.info(
                "PDF check: is_pdf=%s",
                is_pdf,
            )

            if is_pdf:
                logger.info(
                    "Message identified as PDF. "
                    "Routing to PDF parser."
                )

                return self.answer_pdf()

            logger.info(
                "Document is not a PDF. "
                "Continuing message checks."
            )

        # ------------------------------------------------------------------
        # Text
        # ------------------------------------------------------------------

        logger.info(
            "Text check: present=%s",
            self.text is not None,
        )

        if self.text is None:
            logger.info(
                "Message has no text and was not recognized "
                "as a supported photo or PDF."
            )

            return (
                "Não entendi essa mensagem. "
                "Me envie um link de NFC-e ou uma foto "
                "do QR code da nota."
            )

        logger.info(
            "Text message received: length=%d",
            len(self.text),
        )

        # ------------------------------------------------------------------
        # Commands
        # ------------------------------------------------------------------

        is_start = self.text.startswith("/start")

        logger.info(
            "Start command check: matched=%s",
            is_start,
        )

        if is_start:
            return (
                "Olá! Eu sou o Allineed. "
                "Me envie um link de NFC-e."
            )

        is_report = self.text.startswith("/report")

        logger.info(
            "Report command check: matched=%s",
            is_report,
        )

        if is_report:
            return self.answer_stock_estimator()

        if self.text.startswith("/update_catalog"):
            logger.info(
                "Report command check: matched=%s",
                is_report,
            )
            return self.answer_catalog_report()

        # ------------------------------------------------------------------
        # NFC-e URL
        # ------------------------------------------------------------------

        is_nfe_url = self._is_nfe_url(self.text)

        logger.info(
            "NFC-e URL check: matched=%s",
            is_nfe_url,
        )

        if is_nfe_url:
            logger.info(
                "Message identified as NFC-e URL. "
                "Routing to HTML parser."
            )

            return self.answer_nfe_link()

        # ------------------------------------------------------------------
        # Unknown message
        # ------------------------------------------------------------------

        logger.info(
            "Message type not recognized."
        )

        return self.construct_answer(
            "Não entendi essa mensagem. "
            "Me envie um link de NFC-e ou uma foto "
            "do QR code da nota."
        )

    def construct_answer(self, text=None):
        return {
            "text": text
        }

    def answer_catalog_report(self):
        ...

    def _is_nfe_url(self, text: str) -> bool:
        try:
            url = urlparse(text.strip())

            if url.scheme not in ("http", "https"):
                return False

            if url.netloc.lower() not in {
                "www.nfce.fazenda.sp.gov.br",
                "nfce.fazenda.sp.gov.br",
            }:
                return False

            path = url.path.lower()

            if path not in {
                "/qrcode",
                "/nfce/qrcode",
                "/nfceconsultapublica/paginas/consultaqrcode.aspx",
            }:
                return False

            params = parse_qs(url.query)

            qr_code = params.get("p")

            if not qr_code or len(qr_code) != 1:
                return False

            parts = qr_code[0].split("|")

            if len(parts) < 3:
                return False

            access_key = parts[0]

            # A chave de acesso da NFC-e possui 44 dígitos.
            if not access_key.isdigit() or len(access_key) != 44:
                return False

            # Versão do QR Code
            if parts[1] not in {"2", "3"}:
                return False

            # Ambiente:
            # 1 = produção
            # 2 = homologação
            if parts[2] not in {"1", "2"}:
                return False

            return True

        except (ValueError, AttributeError):
            return False

    def answer_pdf(self):
        pdf_bytes = download_document_sync(self.msg)

        if pdf_bytes is None:
            logger.warning("Could not download PDF document.")
            return (
                "Não consegui baixar esse PDF. "
                "Pode tentar enviá-lo novamente?"
            )

        logger.info(
            "PDF downloaded successfully: %d bytes",
            len(pdf_bytes),
        )

        extractor = NFCePdfParser(pdf_bytes)
        data = extractor.get_data()

        save_purchase(
            user_id=self.user_id,
            data=data,
            source_message_id=self.message_id,
        )

        return self.format_nfe_link_response(data)

    def answer_qrcode_photo(self) -> str:
        """
        Caminho de resposta para fotos: baixa a imagem enviada pelo usuário
        (câmera ou galeria), procura um QR code nela e, se encontrar, segue
        o mesmo fluxo de extração/registro usado para links de NFC-e
        recebidos por texto.
        """
        logger.info("Reading the message photo")
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

            unit = product.quantity_unit
            quantity = product.last_purchase_quantity
            days = product.days_since_last_purchase

            if unit == "g" and quantity >= 1000:
                unit = "kg"
                quantity /= 1000

            if unit == "ml" and quantity >= 1000:
                unit = "L"
                quantity /= 1000

            name_line = f"<b>{product.product_name}</b> - {status}"

            DAY_PROPORTION = (24 - 7) / 24  # The earlier one can buy and later one can ask in one day

            days_text = None
            if days < DAY_PROPORTION:
                days_text = "hoje"
            elif days < DAY_PROPORTION + 1:
                days_text = "ontem"
            else:
                days_text = f"há {product.days_since_last_purchase:.0f} dias"

            last_purchase_line = f"Última compra: {quantity:g}{unit} {days_text}" 

            products_lines = [
                name_line,
                last_purchase_line,
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
        extractor = NFCeHtmlParser(link)
        data = extractor.get_data()

        if not data:
            return (
                "Parece que o extrato não está acessível.\n\n"
                "Talvez você tenha cadastrado seu CPF/CNPJ. "
                "Isso me impede de encontrá-lo.\n\n"
                "Acesse o link que você me enviou, digite a "
                "chave de segurança que está na Nota Fiscal, "
                "baixe o PDF da compra e me envie."
            )

        if "error" in data:
            return (
                "A URL enviada retornou um documento inválido.\n"
                "Se conseguir acessar a NFC-e, baixe seu PDF e me envie."
            )


        save_purchase(user_id=self.user_id, data=data, source_message_id=self.message_id)

        return self.format_nfe_link_response(data)

    def format_nfe_link_response(self, data: dict) -> str:
        """
        Formata os dados extraídos da NFC-e em uma resposta legível.
        """
        if error in data:
            if data["error"] == "Document not found":
                return "Documento Fiscal (NFC-e) Inexistente na Base de Dados da Sefaz."

        metadata = data.get("metadata", {})
        products = data.get("products", [])

        if not metadata and not products:
            return "Não foi possível extrair informações da página solicitada."

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