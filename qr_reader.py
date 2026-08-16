"""
qr_reader.py

Módulo para receber uma imagem (arquivo, bytes ou array) e extrair o(s)
conteúdo(s) de QR code(s) presentes nela — tipicamente um link/URL.

Estratégia:
1. Tenta primeiro com o detector nativo do OpenCV (rápido, sem dependências
   de sistema).
2. Se não encontrar nada, tenta com o pyzbar (usa a libzbar, geralmente
   mais robusto em fotos tiradas de ângulo, com pouca luz, etc.).

Uso básico:
    from qr_reader import read_qr_code

    resultado = read_qr_code("foto.jpg")
    if resultado:
        print(resultado[0])  # primeiro link encontrado
    else:
        print("Nenhum QR code encontrado.")
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import List, Union

import cv2
import numpy as np

try:
    from pyzbar import pyzbar
    _PYZBAR_DISPONIVEL = True
except Exception:
    _PYZBAR_DISPONIVEL = False

try:
    from PIL import Image
    _PIL_DISPONIVEL = True
except Exception:
    _PIL_DISPONIVEL = False


ImagemEntrada = Union[str, Path, bytes, bytearray, np.ndarray]


class QRCodeNaoEncontrado(Exception):
    """Levantada quando nenhuma QR code é encontrado na imagem (uso opcional)."""


def _carregar_como_array(imagem: ImagemEntrada) -> np.ndarray:
    """Converte a entrada (path, bytes ou array) em um array BGR do OpenCV."""
    if isinstance(imagem, np.ndarray):
        return imagem

    if isinstance(imagem, (str, Path)):
        caminho = str(imagem)
        array = cv2.imread(caminho)
        if array is None:
            raise ValueError(f"Não foi possível abrir a imagem em: {caminho}")
        return array

    if isinstance(imagem, (bytes, bytearray)):
        buffer = np.frombuffer(imagem, dtype=np.uint8)
        array = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if array is None:
            raise ValueError("Não foi possível decodificar os bytes da imagem.")
        return array

    raise TypeError(
        f"Tipo de imagem não suportado: {type(imagem)}. "
        "Use um caminho (str/Path), bytes ou um array numpy."
    )


def _pre_processar(array_bgr: np.ndarray) -> np.ndarray:
    """Aplica um pré-processamento leve (escala de cinza) para ajudar a detecção."""
    return cv2.cvtColor(array_bgr, cv2.COLOR_BGR2GRAY)


def _tentar_opencv(array_bgr: np.ndarray) -> List[str]:
    """Tenta detectar/decodificar usando o QRCodeDetector do OpenCV."""
    detector = cv2.QRCodeDetector()
    resultados: List[str] = []

    # detectAndDecodeMulti cobre o caso de mais de um QR code na imagem
    ok, textos, pontos, _ = detector.detectAndDecodeMulti(array_bgr)
    if ok:
        resultados.extend([t for t in textos if t])

    # fallback single-QR caso o multi não tenha encontrado nada
    if not resultados:
        texto, pontos, _ = detector.detectAndDecode(array_bgr)
        if texto:
            resultados.append(texto)

    return resultados


def _tentar_pyzbar(array_bgr: np.ndarray) -> List[str]:
    """Tenta detectar/decodificar usando pyzbar (mais robusto em fotos ruins)."""
    if not _PYZBAR_DISPONIVEL:
        return []

    cinza = _pre_processar(array_bgr)
    decodificados = pyzbar.decode(cinza)
    return [
        obj.data.decode("utf-8", errors="replace")
        for obj in decodificados
        if obj.type == "QRCODE"
    ]


def read_qr_code(
    imagem: ImagemEntrada,
    levantar_se_vazio: bool = False,
) -> List[str]:
    """
    Recebe uma imagem e retorna uma lista com os conteúdos (ex.: links)
    de todos os QR codes encontrados.

    Parâmetros
    ----------
    imagem : str | Path | bytes | numpy.ndarray
        Caminho do arquivo, bytes brutos da imagem (ex.: vindos de um
        upload) ou array já carregado (formato OpenCV/BGR).
    levantar_se_vazio : bool
        Se True, levanta QRCodeNaoEncontrado quando nada for encontrado.
        Se False (padrão), retorna lista vazia.

    Retorna
    -------
    List[str]
        Lista com o texto/link decodificado de cada QR code encontrado.
        Vazia se nenhum for encontrado (e levantar_se_vazio=False).
    """
    logger.info("Loading image as array")
    array_bgr = _carregar_como_array(imagem)

    resultados = _tentar_opencv(array_bgr)

    if not resultados:
        resultados = _tentar_pyzbar(array_bgr)

    # remove duplicados mantendo a ordem
    vistos = set()
    resultados_unicos = []
    for r in resultados:
        if r not in vistos:
            vistos.add(r)
            resultados_unicos.append(r)

    if not resultados_unicos and levantar_se_vazio:
        raise QRCodeNaoEncontrado("Nenhum QR code foi encontrado na imagem.")

    return resultados_unicos


def read_first_qr_code(imagem: ImagemEntrada) -> str | None:
    """
    Atalho para quando você só quer o primeiro link/conteúdo encontrado.
    Retorna None se nada for encontrado.
    """
    logger.info("Reading QR Code from image.")
    resultados = read_qr_code(imagem)
    return resultados[0] if resultados else None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python qr_reader.py <caminho_da_imagem>")
        sys.exit(1)

    caminho_imagem = sys.argv[1]
    links = read_qr_code(caminho_imagem)

    if links:
        print(f"{len(links)} QR code(s) encontrado(s):")
        for link in links:
            print(f" - {link}")
    else:
        print("Nenhum QR code encontrado na imagem.")