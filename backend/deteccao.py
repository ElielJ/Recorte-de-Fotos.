"""Detecção automática das fotos dentro da página digitalizada (uma ou várias por página)."""
from math import atan2, degrees, hypot

import cv2
import numpy as np

from .recorte import Recorte, para_8bits

# Acima disso a imagem é reduzida para a detecção (o recorte final usa a original).
MAX_PIXELS = 40_000_000
TOLERANCIA_TAMANHO = 0.06


def detectar(img, dpi, tamanho_cm=None, margem_mm=0.0):
    """Encontra todas as fotos da página.

    Retorna uma lista de (Recorte, estado, motivo) em ordem de leitura; estado é "ok" ou "revisar".
    """
    a = para_8bits(img)
    alt, larg = a.shape[:2]
    f = min(1.0, (MAX_PIXELS / (alt * larg)) ** 0.5)
    if f < 1:
        a = cv2.resize(a, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    a = cv2.GaussianBlur(a, (5, 5), 0)

    # Diferença de cada pixel para a cor do fundo (estimada pelas bordas da página). Feita em 8 bits,
    # no próprio array suavizado: evita cópias de 16 bits que triplicavam o pico de memória.
    fundo = _cor_fundo(a)
    if a.ndim == 3:
        cv2.absdiff(a, tuple(float(v) for v in fundo) + (0.0,), dst=a)
        r, g, b = cv2.split(a)  # maior diferença entre os canais (~6x mais rápido que a.max(axis=2))
        dif = cv2.max(cv2.max(r, g), b)
    else:
        dif = cv2.absdiff(a, float(fundo))
    limiar, _ = cv2.threshold(dif, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, mascara = cv2.threshold(dif, float(np.clip(limiar, 12, 60)), 255, cv2.THRESH_BINARY)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))  # remove poeira
    # ~1 mm: fecha pequenas falhas na borda da foto sem juntar fotos vizinhas.
    k = max(3, round((dpi or 300) / 25.4 * f))
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))

    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return [(Recorte(larg / 2, alt / 2, larg, alt), "revisar", "nenhuma foto encontrada")]

    # Área (na escala da detecção) de uma foto do tamanho esperado; sem ela, usa 2% da página.
    esperado = (tamanho_cm[0] * tamanho_cm[1] * (dpi * f / 2.54) ** 2) if dpi and tamanho_cm else None
    minimo = 0.35 * esperado if esperado else 0.02 * mascara.size
    candidatos = [c for c in contornos if _area_retangulo(c) >= minimo]
    pequena = not candidatos
    if pequena:  # nada com tamanho de foto: fica com o maior objeto, para revisão
        candidatos = [max(contornos, key=cv2.contourArea)]

    # Não divide sozinho: uma foto 15x21 tem o mesmo tamanho de duas 10x15, então só o usuário decide.
    resultados = []
    for c in candidatos:
        r, motivos = _avaliar(c, mascara.shape, f, dpi, tamanho_cm, esperado)
        if pequena:
            motivos.insert(0, "área detectada muito pequena")
        resultados.append((r, motivos))

    m = margem_mm / 25.4 * (dpi or 300)
    saida = []
    for r, motivos in resultados:
        r.w, r.h = max(1.0, r.w - 2 * m), max(1.0, r.h - 2 * m)
        saida.append((r, "revisar" if motivos else "ok", "; ".join(motivos)))
    return [saida[i] for i in ordem_leitura([r for r, _, _ in saida])]


def ordem_leitura(recortes):
    """Índices em ordem de leitura: linhas de cima para baixo e, em cada linha, da esquerda para a direita."""
    restantes = sorted(range(len(recortes)), key=lambda i: recortes[i].cy)
    ordem = []
    while restantes:
        topo = recortes[restantes[0]]
        linha = [i for i in restantes if recortes[i].cy - topo.cy < min(topo.h, recortes[i].h) / 2]
        ordem += sorted(linha, key=lambda i: recortes[i].cx)
        restantes = [i for i in restantes if i not in linha]
    return ordem


def _area_retangulo(contorno):
    _, (w, h), _ = cv2.minAreaRect(contorno)
    return w * h


def _confere(medido_cm, tamanho_cm):
    return all(abs(m - e) / e <= TOLERANCIA_TAMANHO for m, e in zip(sorted(medido_cm), sorted(tamanho_cm)))


def _avaliar(contorno, forma, f, dpi, tamanho_cm, esperado):
    """Retorna (Recorte sem margem, motivos para revisão)."""
    (cx, cy), (w, h), ang = cv2.minAreaRect(contorno)
    pontos = cv2.boxPoints(((cx, cy), (w, h), ang))
    # +0.5: passa de centros de pixel para coordenadas contínuas.
    r = _normalizar(pontos + 0.5).escalado(1 / f)

    motivos = []
    if cv2.contourArea(contorno) / (w * h) < 0.95:
        motivos.append("contorno irregular")
    tamanho_ok = False
    if esperado:
        medido = sorted((r.w / dpi * 2.54, r.h / dpi * 2.54))
        tamanho_ok = _confere(medido, tamanho_cm)
        # Duas fotos encostadas: o lado maior tem o dobro e a metade confere com o tamanho esperado.
        if not tamanho_ok and _confere((medido[1] / 2, medido[0]), tamanho_cm):
            motivos.append(f"tamanho {medido[0]:.1f} x {medido[1]:.1f} cm: parece conter duas fotos "
                           f"encostadas; se for o caso, use “Dividir em duas” no editor")
        elif not tamanho_ok and w * h >= 1.6 * esperado:
            motivos.append("pode conter mais de uma foto encostada; se for o caso, use “Dividir em duas” "
                           "no editor")
        elif not tamanho_ok:
            alvo = sorted(tamanho_cm)
            motivos.append(f"tamanho {medido[0]:.1f} x {medido[1]:.1f} cm difere do esperado "
                           f"{alvo[0]:g} x {alvo[1]:g} cm")
    # Scanners com alimentador começam na borda da foto, e no vidro a foto costuma ficar encostada
    # no canto; só é suspeito quando o tamanho não confirma que a foto está inteira.
    mh, mw = forma
    if not tamanho_ok and (pontos[:, 0].min() <= 1 or pontos[:, 1].min() <= 1
                           or pontos[:, 0].max() >= mw - 2 or pontos[:, 1].max() >= mh - 2):
        motivos.append("foto encostada na borda da digitalização")
    return r, motivos


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
