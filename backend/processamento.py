"""Fluxo completo: extrair as fotos de um arquivo, salvar e reabrir recortes."""
import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from . import leitura
from .deteccao import detectar
from .gravacao import salvar_jpeg, salvar_png
from .metadados import Metadados, montar_exif, montar_xmp
from .recorte import Recorte, cortar, previa

ARQUIVO_RECORTES = "recortes.json"
EXTENSOES_SAIDA = {"png": ".png", "jpeg": ".jpg"}


@dataclass
class Config:
    tamanho_cm: tuple[float, float] | None = (15.0, 21.0)  # None = não validar
    margem_mm: float = 0.3
    pasta_saida: Path | None = None  # None = ao lado de cada arquivo
    formato: str = "png"  # "png" (sem perdas) ou "jpeg" (qualidade 95, arquivos menores)


@dataclass
class Foto:
    arquivo: Path
    pagina: int  # 0 = primeira
    largura: int
    altura: int
    dpi: float | None
    auto: Recorte
    recorte: Recorte
    estado: str = "ok"  # ok | revisar | editado
    motivo: str = ""
    rot90: int = 0  # giros de 90° no sentido horário
    excluida: bool = False
    previa: bytes = field(default=b"", repr=False)  # JPEG do recorte, sem o giro de 90°

    def nome(self, formato="png"):
        return f"{self.arquivo.stem}_{self.pagina + 1:03d}{EXTENSOES_SAIDA[formato]}"

    def tamanho_cm(self):
        if not self.dpi:
            return None
        w, h = self.recorte.w / self.dpi * 2.54, self.recorte.h / self.dpi * 2.54
        return (h, w) if self.rot90 % 2 else (w, h)


def listar_arquivos(caminhos):
    """Expande pastas (sem subpastas) e mantém só PDF/TIFF."""
    arquivos = []
    for c in map(Path, caminhos):
        itens = sorted(c.iterdir()) if c.is_dir() else [c]
        arquivos += [a for a in itens if a.is_file() and a.suffix.lower() in leitura.EXTENSOES]
    return arquivos


def pasta_saida(arquivo, cfg):
    return (cfg.pasta_saida or arquivo.parent) / arquivo.stem


def extrair(arquivo, cfg, cancelado=lambda: False):
    """Gera (foto, página atual, total de páginas) para cada página do arquivo."""
    arquivo = Path(arquivo)
    salvos = _carregar_recortes(pasta_saida(arquivo, cfg), arquivo)
    with leitura.abrir(arquivo) as leitor:
        total = len(leitor)
        if salvos and salvos["paginas"] != total:
            salvos = None
        for i in range(total):
            if cancelado():
                return
            pg = leitor.pagina(i)
            alt, larg = pg.imagem.shape[:2]
            d = salvos and salvos["fotos"].get(i)
            if d and (d["largura"], d["altura"]) == (larg, alt):
                foto = Foto(arquivo, i, larg, alt, pg.dpi, Recorte(**d["auto"]), Recorte(**d["recorte"]),
                            d["estado"], d.get("motivo", ""), d.get("rot90", 0), d.get("excluida", False))
            else:
                r, estado, motivo = detectar(pg.imagem, pg.dpi, cfg.tamanho_cm, cfg.margem_mm)
                if pg.aviso:
                    estado, motivo = "revisar", "; ".join(filter(None, [pg.aviso, motivo]))
                foto = Foto(arquivo, i, larg, alt, pg.dpi, r, Recorte(**r.como_dict()), estado, motivo)
            atualizar_previa(foto, pg.imagem)
            yield foto, i + 1, total


def carregar_pagina(foto):
    with leitura.abrir(foto.arquivo) as leitor:
        return leitor.pagina(foto.pagina)


def atualizar_previa(foto, imagem):
    p = previa(imagem, foto.recorte)
    ok, buf = cv2.imencode(".jpg", p if p.ndim == 2 else cv2.cvtColor(p, cv2.COLOR_RGB2BGR),
                           [cv2.IMWRITE_JPEG_QUALITY, 90])
    foto.previa = buf.tobytes()


def destino(foto, cfg):
    return pasta_saida(foto.arquivo, cfg) / foto.nome(cfg.formato)


def arquivos_existentes(fotos, cfg):
    return [c for f in fotos if not f.excluida for c in [destino(f, cfg)] if c.exists()]


def carregar_metadados(arquivo, cfg):
    """Metadados do lote salvos anteriormente no recortes.json (ou vazios)."""
    arquivo = Path(arquivo)
    salvos = _carregar_recortes(pasta_saida(arquivo, cfg), arquivo)
    return Metadados.de_dict(salvos["metadados"]) if salvos else Metadados()


def salvar(fotos, cfg, ao_progresso=lambda feitas, total: None, cancelado=lambda: False, metadados=None):
    """Grava as fotos (PNG ou JPEG), com os metadados de cada lote, e o recortes.json. Retorna as pastas usadas.

    metadados: {arquivo: Metadados}; se omitido, usa os que já estavam salvos no recortes.json.
    """
    por_arquivo = {}
    for f in fotos:
        por_arquivo.setdefault(f.arquivo, []).append(f)
    total = sum(not f.excluida for f in fotos)
    feitas, pastas = 0, []
    for arquivo, lista in por_arquivo.items():
        meta = (metadados or {}).get(arquivo) or carregar_metadados(arquivo, cfg)
        data = meta.data()
        xmp = None if meta.vazio() else montar_xmp(meta)
        pasta = pasta_saida(arquivo, cfg)
        pasta.mkdir(parents=True, exist_ok=True)
        pastas.append(pasta)
        with leitura.abrir(arquivo) as leitor:
            for f in sorted(lista, key=lambda f: f.pagina):
                if f.excluida:
                    continue
                if cancelado():
                    return pastas
                pg = leitor.pagina(f.pagina)
                img = cortar(pg.imagem, f.recorte, f.rot90)
                exif = montar_exif(meta, pg.dpi)
                if cfg.formato == "jpeg":
                    salvar_jpeg(destino(f, cfg), img, exif, data)
                else:
                    salvar_png(destino(f, cfg), img, pg.dpi, pg.icc, exif, xmp, data)
                feitas += 1
                ao_progresso(feitas, total)
            _salvar_recortes(pasta, arquivo, len(leitor), lista, meta)
    return pastas


def _salvar_recortes(pasta, arquivo, paginas, fotos, meta):
    dados = {
        "versao": 1,
        "arquivo": arquivo.name,
        "paginas": paginas,
        "metadados": meta.como_dict(),
        "fotos": [{
            "pagina": f.pagina + 1, "largura": f.largura, "altura": f.altura, "dpi": f.dpi,
            "estado": f.estado, "motivo": f.motivo, "rot90": f.rot90, "excluida": f.excluida,
            "auto": f.auto.como_dict(), "recorte": f.recorte.como_dict(),
        } for f in sorted(fotos, key=lambda f: f.pagina)],
    }
    (pasta / ARQUIVO_RECORTES).write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")


def _carregar_recortes(pasta, arquivo):
    try:
        dados = json.loads((pasta / ARQUIVO_RECORTES).read_text(encoding="utf-8"))
        if dados.get("arquivo") != arquivo.name:
            return None
        return {"paginas": dados["paginas"], "fotos": {d["pagina"] - 1: d for d in dados["fotos"]},
                "metadados": dados.get("metadados")}
    except (OSError, ValueError, KeyError, TypeError):
        return None
