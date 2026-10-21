"""Recorte de uma foto a partir da página original.

Coordenadas contínuas: o pixel i ocupa o intervalo [i, i+1]. O retângulo é
definido pelo centro, largura, altura e ângulo em graus (sentido horário na
tela, como no Qt).
"""
from dataclasses import asdict, dataclass
from math import cos, radians, sin

import cv2
import numpy as np

# Abaixo deste ângulo o recorte é feito sem rotação, preservando os pixels originais.
LIMIAR_ROTACAO = 0.2


@dataclass
class Recorte:
    cx: float
    cy: float
    w: float
    h: float
    angulo: float = 0.0

    def escalado(self, f):
        return Recorte(self.cx * f, self.cy * f, self.w * f, self.h * f, self.angulo)

    def como_dict(self):
        return {k: round(v, 3) for k, v in asdict(self).items()}


def dividir(r):
    """Divide o recorte ao meio ao longo do lado maior (ex.: duas fotos encostadas)."""
    c, s = cos(radians(r.angulo)), sin(radians(r.angulo))
    if r.w >= r.h:
        dx, dy, w, h = c * r.w / 4, s * r.w / 4, r.w / 2, r.h
    else:
        dx, dy, w, h = -s * r.h / 4, c * r.h / 4, r.w, r.h / 2
    return (Recorte(r.cx - dx, r.cy - dy, w, h, r.angulo),
            Recorte(r.cx + dx, r.cy + dy, w, h, r.angulo))


def cortar(img, r, rot90=0, interpolacao=cv2.INTER_LANCZOS4):
    """Recorta a foto. rot90 = número de giros de 90° no sentido horário."""
    W, H = max(1, round(r.w)), max(1, round(r.h))
    if abs(r.angulo) < LIMIAR_ROTACAO:
        x0, y0 = round(r.cx - r.w / 2), round(r.cy - r.h / 2)
        out = img[max(0, y0):max(0, y0 + H), max(0, x0):max(0, x0 + W)].copy()
    else:
        c, s = cos(radians(r.angulo)), sin(radians(r.angulo))
        # Mapeia cada pixel de saída para a posição correspondente na página.
        m = np.float64([[c, -s, r.cx - 0.5 + c * (0.5 - W / 2) - s * (0.5 - H / 2)],
                        [s, c, r.cy - 0.5 + s * (0.5 - W / 2) + c * (0.5 - H / 2)]])
        out = cv2.warpAffine(img, m, (W, H), flags=interpolacao | cv2.WARP_INVERSE_MAP,
                             borderMode=cv2.BORDER_REPLICATE)
    return np.ascontiguousarray(np.rot90(out, -rot90)) if rot90 % 4 else out


def previa(img, r, lado=1200):
    """Versão reduzida (8 bits, sem o giro de 90°) do recorte, para exibição."""
    f = min(1.0, lado / max(r.w, r.h, 1))
    if f < 1:
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    out = cortar(img, r.escalado(f), interpolacao=cv2.INTER_LINEAR)
    return para_8bits(out)


def para_8bits(img):
    return (img >> 8).astype(np.uint8) if img.dtype == np.uint16 else img
