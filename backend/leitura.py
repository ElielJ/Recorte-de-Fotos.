"""Leitura das páginas de arquivos TIFF e PDF sem perda de qualidade."""
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import tifffile

EXTENSOES = {".pdf", ".tif", ".tiff"}


@dataclass
class Pagina:
    imagem: np.ndarray  # RGB (A, L, 3) ou cinza (A, L); uint8 ou uint16
    dpi: float | None
    icc: bytes | None = None
    aviso: str = ""


def abrir(caminho):
    ext = Path(caminho).suffix.lower()
    if ext == ".pdf":
        return LeitorPdf(caminho)
    if ext in (".tif", ".tiff"):
        return LeitorTiff(caminho)
    raise ValueError(f"Formato não suportado: {ext}")


class _Leitor:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class LeitorTiff(_Leitor):
    def __init__(self, caminho):
        self._tif = tifffile.TiffFile(caminho)
        # Ignora miniaturas (páginas reduzidas) que alguns programas gravam junto.
        self._paginas = [p for p in self._tif.pages if not p.is_reduced]

    def __len__(self):
        return len(self._paginas)

    def pagina(self, i):
        p = self._paginas[i]
        icc = p.tags.get(34675)
        return Pagina(_normalizar_tiff(p.asarray(), p), _dpi_tiff(p), bytes(icc.value) if icc else None)

    def close(self):
        self._tif.close()


def _normalizar_tiff(img, p):
    if p.planarconfig == 2 and img.ndim == 3:  # canais separados: (C, A, L) -> (A, L, C)
        img = np.moveaxis(img, 0, -1)
    fot = int(p.photometric)
    if img.dtype == bool:
        img = img.astype(np.uint8) * 255
    if fot == 0:  # MINISWHITE: 0 = branco
        img = np.iinfo(img.dtype).max - img
    elif fot == 3:  # paleta
        img = np.moveaxis(p.colormap[:, img], 0, -1)
        img = (img >> 8).astype(np.uint8) if img.max() > 255 else img.astype(np.uint8)
    elif fot == 5 and img.ndim == 3:  # CMYK
        cmyk = img.astype(np.float32) / np.iinfo(img.dtype).max
        rgb = (1 - cmyk[..., :3]) * (1 - cmyk[..., 3:4])
        img = (rgb * np.iinfo(img.dtype).max).round().astype(img.dtype)
    if img.ndim == 3 and img.shape[2] == 1:
        img = img[..., 0]
    elif img.ndim == 3 and img.shape[2] > 3:  # descarta transparência
        img = img[..., :3]
    if img.dtype not in (np.uint8, np.uint16):
        raise ValueError(f"Profundidade de cor não suportada: {img.dtype}")
    return np.ascontiguousarray(img)


def _dpi_tiff(p):
    x = p.tags.get("XResolution")
    if not x or not x.value[1]:
        return None
    dpi = x.value[0] / x.value[1]
    unidade = p.tags.get("ResolutionUnit")
    unidade = int(unidade.value) if unidade else 2
    if unidade == 1:  # sem unidade definida
        return None
    return round(dpi * 2.54 if unidade == 3 else dpi, 2) or None


class LeitorPdf(_Leitor):
    def __init__(self, caminho):
        self._doc = pymupdf.open(caminho)

    def __len__(self):
        return self._doc.page_count

    def pagina(self, i):
        try:
            pg = self._doc[i]
            img = self._imagem_embutida(pg)
            if img is None:
                # Página sem uma imagem única do scanner: renderiza em alta resolução.
                pix = pg.get_pixmap(dpi=600, colorspace=pymupdf.csRGB, alpha=False)
                return Pagina(_array(pix), 600.0, aviso="página renderizada a 600 dpi (sem imagem original única)")
            return Pagina(img, float(round(img.shape[1] / (pg.rect.width / 72))))
        finally:
            # O MuPDF guarda as imagens decodificadas num cache (até ~256 MB); como a página já foi
            # copiada para o NumPy, o cache só ocuparia memória.
            pymupdf.TOOLS.store_shrink(100)

    def close(self):
        self._doc.close()

    def _imagem_embutida(self, pg):
        """Extrai os pixels originais gravados pelo scanner, sem reamostragem."""
        area_pagina = pg.rect.width * pg.rect.height

        def posicoes(info):
            # get_image_bbox é instantâneo; get_image_rects (reserva) calcula um hash da imagem inteira (~0,5 s).
            r = pg.get_image_bbox(info)
            return [r] if r.is_valid and not r.is_infinite and not r.is_empty else pg.get_image_rects(info[0])

        grandes = {info[0] for info in pg.get_images(full=True)
                   if any(r.width * r.height >= 0.8 * area_pagina for r in posicoes(info))}
        if len(grandes) != 1:
            return None
        pix = pymupdf.Pixmap(self._doc, grandes.pop())
        if pix.colorspace is None:
            return None
        if pix.alpha:
            pix = pymupdf.Pixmap(pix, 0)
        if pix.n not in (1, 3):
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        return self._orientar(_array(pix), pg)

    @staticmethod
    def _orientar(img, pg):
        """Gira/espelha a imagem extraída para ficar como aparece na página.

        Compara com uma renderização pequena da página, o que cobre qualquer
        rotação da página ou da imagem sem depender das matrizes do PDF.
        """
        ref = _array(pg.get_pixmap(dpi=30, colorspace=pymupdf.csGRAY, alpha=False)).astype(np.float32)
        cinza = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        cinza = cv2.resize(cinza, None, fx=0.1, fy=0.1, interpolation=cv2.INTER_AREA)

        def erro(k, espelho):
            c = np.rot90(cinza, k)
            c = c[:, ::-1] if espelho else c
            c = cv2.resize(np.ascontiguousarray(c), (ref.shape[1], ref.shape[0]), interpolation=cv2.INTER_AREA)
            return float(np.abs(c.astype(np.float32) - ref).mean())

        k, espelho = min(((k, e) for k in range(4) for e in (False, True)), key=lambda o: erro(*o))
        if (k, espelho) == (0, False):
            return img
        img = np.rot90(img, k)
        return np.ascontiguousarray(img[:, ::-1] if espelho else img)


def _array(pix):
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    return (img[..., 0] if pix.n == 1 else img).copy()
