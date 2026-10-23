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
    preenchimento = _preenchimento(a)
    a = cv2.GaussianBlur(a, (5, 5), 0)

    # Diferença de cada pixel para a cor do fundo (estimada pelas bordas da página). Feita em 8 bits,
    # no próprio array suavizado: evita cópias de 16 bits que triplicavam o pico de memória.
    fundo = _cor_fundo(a, preenchimento)
    if a.ndim == 3:
        cv2.absdiff(a, tuple(float(v) for v in fundo) + (0.0,), dst=a)
        r, g, b = cv2.split(a)  # maior diferença entre os canais (~6x mais rápido que a.max(axis=2))
        dif = cv2.max(cv2.max(r, g), b)
    else:
        dif = cv2.absdiff(a, float(fundo))
    # O preenchimento artificial conta como fundo, com ~20 px a mais para cobrir a transição suavizada
    # entre ele e a área digitalizada (que formaria uma linha "fantasma" ao longo da borda).
    if preenchimento.any():
        dif[cv2.dilate(preenchimento, np.ones((41, 41), np.uint8)) > 0] = 0
    limiar, _ = cv2.threshold(dif, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, mascara = cv2.threshold(dif, float(np.clip(limiar, 12, 60)), 255, cv2.THRESH_BINARY)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))  # remove poeira
    # ~1 mm: fecha pequenas falhas na borda da foto sem juntar fotos vizinhas.
    k = max(3, round((dpi or 300) / 25.4 * f))
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))

    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        if _uniforme(dif):  # página em branco: não há o que recortar
            return []
        return [(Recorte(larg / 2, alt / 2, larg, alt), "revisar", "nenhuma foto encontrada")]

    # Área (na escala da detecção) de uma foto do tamanho esperado; sem ela, usa 2% da página.
    esperado = (tamanho_cm[0] * tamanho_cm[1] * (dpi * f / 2.54) ** 2) if dpi and tamanho_cm else None
    minimo = 0.35 * esperado if esperado else 0.02 * mascara.size
    candidatos = [c for c in contornos if _area_retangulo(c) >= minimo]
    pequena = not candidatos
    if pequena:  # nada com tamanho de foto: fica com o maior objeto, para revisão
        candidatos = [max(contornos, key=cv2.contourArea)]

    # Faixa de ~3 mm junto ao preenchimento: uma foto incompleta que chega nela foi cortada pelo fim da
    # digitalização (o preenchimento é marcado em blocos, então pode começar alguns pixels depois).
    perto_preenchimento = cv2.dilate(preenchimento, np.ones((6 * k + 1, 6 * k + 1), np.uint8)) \
        if preenchimento.any() else None
    # Não divide sozinho: uma foto 15x21 tem o mesmo tamanho de duas 10x15, então só o usuário decide.
    resultados = []
    for c in candidatos:
        if _uniforme(dif, c):  # área de cor lisa (sem textura): não é uma foto
            continue
        r, motivos = _avaliar(c, mascara.shape, f, dpi, tamanho_cm, esperado, perto_preenchimento)
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


def _avaliar(contorno, forma, f, dpi, tamanho_cm, esperado, perto_preenchimento=None):
    """Retorna (Recorte sem margem, motivos para revisão)."""
    (cx, cy), (w, h), ang = cv2.minAreaRect(contorno)
    pontos = cv2.boxPoints(((cx, cy), (w, h), ang))
    # +0.5: passa de centros de pixel para coordenadas contínuas.
    r = _normalizar(pontos + 0.5).escalado(1 / f)

    motivos = []
    toca_preenchimento = False
    if perto_preenchimento is not None:
        caixa = np.zeros(forma, np.uint8)
        cv2.fillPoly(caixa, [pontos.astype(np.int32)], 255)
        toca_preenchimento = cv2.countNonZero(cv2.bitwise_and(caixa, perto_preenchimento)) > 0
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
    if toca_preenchimento and not tamanho_ok:
        motivos.insert(0, "a digitalização terminou antes do fim da foto (parte dela não foi escaneada); "
                          "digitalize esta foto de novo")
    # Partes da foto com a cor do fundo deixam o contorno "dentado"; se o tamanho confere, o retângulo
    # está certo e o aviso seria falso.
    if not tamanho_ok and cv2.contourArea(contorno) / (w * h) < 0.95:
        motivos.append("contorno irregular")
    # Scanners com alimentador começam na borda da foto, e no vidro a foto costuma ficar encostada
    # no canto; só é suspeito quando o tamanho não confirma que a foto está inteira.
    mh, mw = forma
    if not tamanho_ok and (pontos[:, 0].min() <= 1 or pontos[:, 1].min() <= 1
                           or pontos[:, 0].max() >= mw - 2 or pontos[:, 1].max() >= mh - 2):
        motivos.append("foto encostada na borda da digitalização")
    return r, motivos


def _cor_fundo(a, excluir=None):
    """Cor do fundo do scanner: mediana das bordas da página, sem o preenchimento artificial."""
    b = max(2, int(min(a.shape[:2]) * 0.01))
    borda = np.zeros(a.shape[:2], bool)
    borda[:b] = borda[-b:] = True
    borda[:, :b] = borda[:, -b:] = True
    if excluir is not None:
        validos = borda & (excluir == 0)
        if validos.sum() >= 1000:
            borda = validos
    fundo = np.median(a[borda].reshape(-1, 1 if a.ndim == 2 else a.shape[2]), axis=0).astype(np.int16)
    return fundo[0] if a.ndim == 2 else fundo


def _preenchimento(a, bloco=16):
    """Áreas de branco ou preto exatos, sem nenhum ruído, encostadas na borda da página.

    Quando a área digitalizada é menor que o tamanho de página escolhido, o driver do scanner completa
    o resto com cor pura. Papel e tampa de verdade sempre têm algum ruído, e pixels estourados dentro
    das fotos são isolados: por isso só contam blocos inteiros de cor pura, ligados à borda e grandes.
    """
    if a.ndim == 3:
        puro = cv2.inRange(a, (255, 255, 255), (255, 255, 255)) | cv2.inRange(a, (0, 0, 0), (0, 0, 0))
    else:
        puro = ((a == 255) | (a == 0)).astype(np.uint8) * 255
    alt, larg = puro.shape
    blocos = (cv2.resize(puro, (max(1, larg // bloco), max(1, alt // bloco)),
                         interpolation=cv2.INTER_AREA) == 255).astype(np.uint8)
    n, rotulos, stats, _ = cv2.connectedComponentsWithStats(blocos, connectivity=4)
    hb, wb = blocos.shape
    manter = np.zeros(n, np.uint8)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if (x == 0 or y == 0 or x + w >= wb or y + h >= hb) and area >= 0.01 * hb * wb:
            manter[i] = 255
    return cv2.resize(manter[rotulos], (larg, alt), interpolation=cv2.INTER_NEAREST)


def _uniforme(dif, contorno=None, limite=2.5):
    """Se a área (ou a página inteira) é de cor lisa: uma foto de verdade sempre tem variação."""
    mascara = None
    if contorno is not None:
        mascara = np.zeros(dif.shape, np.uint8)
        cv2.drawContours(mascara, [contorno], -1, 255, cv2.FILLED)
    _, desvio = cv2.meanStdDev(dif, mask=mascara)
    return float(desvio[0][0]) < limite


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
