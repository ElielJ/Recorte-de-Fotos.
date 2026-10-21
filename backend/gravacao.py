"""Gravação das fotos em PNG sem perdas (e cópia JPEG opcional), com DPI, perfil de cor e metadados."""
import io
import os
import struct
import zlib
from datetime import datetime
from pathlib import Path

import cv2
import piexif


def salvar_png(caminho, img, dpi=None, icc=None, exif=None, xmp=None, data=None):
    bgr = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    # Nível 6: o 9 leva ~7x mais tempo para arquivos só ~3% menores (a qualidade é idêntica).
    ok, buf = cv2.imencode(".png", bgr, [cv2.IMWRITE_PNG_COMPRESSION, 6,
                                         cv2.IMWRITE_PNG_STRATEGY, cv2.IMWRITE_PNG_STRATEGY_FILTERED])
    if not ok:
        raise IOError(f"Falha ao codificar {caminho}")
    dados = buf.tobytes()
    extra = b""
    if icc and _icc_compativel(icc, img):
        extra += _chunk(b"iCCP", b"ICC Profile\x00\x00" + zlib.compress(icc))
    if dpi:
        ppm = round(dpi / 0.0254)  # pixels por metro
        extra += _chunk(b"pHYs", struct.pack(">IIB", ppm, ppm, 1))
    if exif:
        extra += _chunk(b"eXIf", exif)
    if xmp:
        extra += _chunk(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + xmp.encode("utf-8"))
    # Os blocos extras entram logo após o cabeçalho IHDR (assinatura 8 + IHDR 25 bytes).
    _gravar(caminho, dados[:33] + extra + dados[33:], data)


def salvar_jpeg(caminho, img, exif=None, data=None, qualidade=95):
    """Cópia JPEG de alta qualidade (8 bits, cores sem subamostragem) para compartilhar/enviar."""
    img = (img >> 8).astype("uint8") if img.dtype == "uint16" else img
    bgr = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, qualidade,
                                         cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444])
    if not ok:
        raise IOError(f"Falha ao codificar {caminho}")
    dados = buf.tobytes()
    if exif:
        saida = io.BytesIO()
        piexif.insert(b"Exif\x00\x00" + exif, dados, saida)
        dados = saida.getvalue()
    _gravar(caminho, dados, data)


def _gravar(caminho, dados, data):
    caminho = Path(caminho)
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_bytes(dados)
    os.replace(tmp, caminho)
    if data:  # data do arquivo = data estimada da foto (usada por alguns serviços quando não leem o EXIF)
        try:
            # Cálculo manual: datetime.timestamp() falha no Windows para datas anteriores a 1970.
            fuso = datetime.now().astimezone().utcoffset().total_seconds()
            ts = (data - datetime(1970, 1, 1)).total_seconds() - fuso
            os.utime(caminho, (ts, ts))
        except (OverflowError, OSError, ValueError):
            pass  # datas muito antigas não são aceitas pelo sistema de arquivos


def _icc_compativel(icc, img):
    espaco = icc[16:20]
    return espaco == (b"GRAY" if img.ndim == 2 else b"RGB ")


def _chunk(tipo, dados):
    return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados))
