"""Detecção automática da foto dentro da página digitalizada."""
from math import atan2, degrees, hypot

import cv2
import numpy as np

from .recorte import Recorte, para_8bits

# Acima disso a imagem é reduzida para a detecção (o recorte final usa a original).
MAX_PIXELS = 40_000_000
TOLERANCIA_TAMANHO = 0.06


def detectar(img, dpi, tamanho_cm=None, margem_mm=0.0):
    """Retorna (Recorte, estado, motivo); estado é "ok" ou "revisar"."""
    a = para_8bits(img)
    alt, larg = a.shape[:2]
    f = min(1.0, (MAX_PIXELS / (alt * larg)) ** 0.5)
    if f < 1:
        a = cv2.resize(a, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    a = cv2.GaussianBlur(a, (5, 5), 0)

    # Diferença de cada pixel para a cor do fundo (estimada pelas bordas da página).
    dif = np.abs(a.astype(np.int16) - _cor_fundo(a)).astype(np.uint8)
    if dif.ndim == 3:
        dif = dif.max(axis=2)
    limiar, _ = cv2.threshold(dif, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, mascara = cv2.threshold(dif, float(np.clip(limiar, 12, 60)), 255, cv2.THRESH_BINARY)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))  # remove poeira
    k = max(3, int(min(mascara.shape) * 0.01))
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))

    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return Recorte(larg / 2, alt / 2, larg, alt), "revisar", "nenhuma foto encontrada"
    contorno = max(contornos, key=cv2.contourArea)
    (cx, cy), (w, h), ang = cv2.minAreaRect(contorno)
    pontos = cv2.boxPoints(((cx, cy), (w, h), ang))
    # +0.5: passa de centros de pixel para coordenadas contínuas.
    r = _normalizar(pontos + 0.5).escalado(1 / f)

    motivos = []
    if w * h < 0.05 * mascara.size:
        motivos.append("área detectada muito pequena")
    elif cv2.contourArea(contorno) / (w * h) < 0.95:
        motivos.append("contorno irregular")
    tamanho_ok = False
    if dpi and tamanho_cm:
        medido = sorted((r.w / dpi * 2.54, r.h / dpi * 2.54))
        esperado = sorted(tamanho_cm)
        tamanho_ok = all(abs(m - e) / e <= TOLERANCIA_TAMANHO for m, e in zip(medido, esperado))
        if not tamanho_ok:
            motivos.append(f"tamanho {medido[0]:.1f} x {medido[1]:.1f} cm difere do esperado "
                           f"{esperado[0]:g} x {esperado[1]:g} cm")
    # Scanners com alimentador começam na borda da foto, então encostar na borda é normal;
    # só é suspeito quando o tamanho não confirma que a foto está inteira.
    mh, mw = mascara.shape
    if not tamanho_ok and (pontos[:, 0].min() <= 1 or pontos[:, 1].min() <= 1
                           or pontos[:, 0].max() >= mw - 2 or pontos[:, 1].max() >= mh - 2):
        motivos.append("foto encostada na borda da digitalização")

    m = margem_mm / 25.4 * (dpi or 300)
    r.w, r.h = max(1.0, r.w - 2 * m), max(1.0, r.h - 2 * m)
    return r, ("revisar" if motivos else "ok"), "; ".join(motivos)


def _cor_fundo(a):
    b = max(2, int(min(a.shape[:2]) * 0.01))
    canais = 1 if a.ndim == 2 else a.shape[2]
    borda = np.concatenate([x.reshape(-1, canais) for x in (a[:b], a[-b:], a[:, :b], a[:, -b:])])
    fundo = np.median(borda, axis=0).astype(np.int16)
    return fundo[0] if a.ndim == 2 else fundo


def _normalizar(p):
    """Converte os 4 cantos em Recorte com ângulo entre -45° e 45°."""
    e1, e2 = p[1] - p[0], p[2] - p[1]
    a1 = (degrees(atan2(e1[1], e1[0])) + 90) % 180 - 90
    a2 = (degrees(atan2(e2[1], e2[0])) + 90) % 180 - 90
    l1, l2 = hypot(*e1), hypot(*e2)
    cx, cy = p.mean(axis=0)
    if abs(a1) <= 45:
        return Recorte(float(cx), float(cy), l1, l2, a1)
    return Recorte(float(cx), float(cy), l2, l1, a2)
