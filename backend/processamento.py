"""Fluxo completo: extrair as fotos de um arquivo, salvar e reabrir recortes."""
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from . import leitura
from .deteccao import detectar, ordem_leitura
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
    indice: int = 0  # posição da foto na página (ordem de leitura), quando há mais de uma
    previa: bytes = field(default=b"", repr=False)  # JPEG do recorte, sem o giro de 90°

    def nome(self, formato="png", varias_na_pagina=False):
        sufixo = f"_{self.indice + 1}" if varias_na_pagina else ""
        return f"{self.arquivo.stem}_{self.pagina + 1:03d}{sufixo}{EXTENSOES_SAIDA[formato]}"

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
    """Gera (foto, página atual, total de páginas) para cada foto encontrada no arquivo."""
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
            entradas = salvos["fotos"].get(i) if salvos else None
            if entradas and all((d["largura"], d["altura"]) == (larg, alt) for d in entradas):
                fotos = [Foto(arquivo, i, larg, alt, pg.dpi, Recorte(**d["auto"]), Recorte(**d["recorte"]),
                              estado=d["estado"], motivo=d.get("motivo", ""), rot90=d.get("rot90", 0),
                              excluida=d.get("excluida", False), indice=d.get("indice", 0))
                         for d in sorted(entradas, key=lambda d: d.get("indice", 0))]
            else:
                fotos = []
                for k, (r, estado, motivo) in enumerate(detectar(pg.imagem, pg.dpi, cfg.tamanho_cm,
                                                                 cfg.margem_mm)):
                    if pg.aviso:
                        estado, motivo = "revisar", "; ".join(filter(None, [pg.aviso, motivo]))
                    fotos.append(Foto(arquivo, i, larg, alt, pg.dpi, r, Recorte(**r.como_dict()),
                                      estado=estado, motivo=motivo, indice=k))
            for foto in fotos:
                atualizar_previa(foto, pg.imagem)
                yield foto, i + 1, total


def nova_foto(modelo, recorte):
    """Foto acrescentada manualmente na mesma página de 'modelo'."""
    return Foto(modelo.arquivo, modelo.pagina, modelo.largura, modelo.altura, modelo.dpi,
                Recorte(**recorte.como_dict()), recorte, estado="editado")


def renumerar(fotos_da_pagina):
    """Numera as fotos de uma página em ordem de leitura (cima→baixo, esquerda→direita)."""
    for k, i in enumerate(ordem_leitura([f.recorte for f in fotos_da_pagina])):
        fotos_da_pagina[i].indice = k


def carregar_pagina(foto):
    with leitura.abrir(foto.arquivo) as leitor:
        return leitor.pagina(foto.pagina)


def atualizar_previa(foto, imagem):
    p = previa(imagem, foto.recorte)
    ok, buf = cv2.imencode(".jpg", p if p.ndim == 2 else cv2.cvtColor(p, cv2.COLOR_RGB2BGR),
                           [cv2.IMWRITE_JPEG_QUALITY, 90])
    foto.previa = buf.tobytes()


def destinos(fotos, cfg):
    """Caminho de saída de cada foto (mesma ordem da lista).

    Página com uma foto: Album_003.png; com várias: Album_003_1.png, Album_003_2.png...
    """
    por_pagina = Counter((f.arquivo, f.pagina) for f in fotos)
    return [pasta_saida(f.arquivo, cfg) / f.nome(cfg.formato, por_pagina[f.arquivo, f.pagina] > 1)
            for f in fotos]


def arquivos_existentes(fotos, cfg):
    return [c for f, c in zip(fotos, destinos(fotos, cfg)) if not f.excluida and c.exists()]


def carregar_metadados(arquivo, cfg):
    """Metadados do lote salvos anteriormente no recortes.json (ou vazios)."""
    arquivo = Path(arquivo)
    salvos = _carregar_recortes(pasta_saida(arquivo, cfg), arquivo)
    return Metadados.de_dict(salvos["metadados"]) if salvos else Metadados()


def salvar(fotos, cfg, ao_progresso=lambda feitas, total: None, cancelado=lambda: False, metadados=None):
    """Grava as fotos (PNG ou JPEG), com os metadados de cada lote, e o recortes.json. Retorna as pastas usadas.

    metadados: {arquivo: Metadados}; se omitido, usa os que já estavam salvos no recortes.json.
    """
    caminhos = dict(zip(map(id, fotos), destinos(fotos, cfg)))
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
            pg, pagina_lida = None, None
            for f in sorted(lista, key=lambda f: (f.pagina, f.indice)):
                if f.excluida:
                    continue
                if cancelado():
                    return pastas
                if f.pagina != pagina_lida:  # várias fotos da mesma página: lê a página uma vez só
                    pg, pagina_lida = leitor.pagina(f.pagina), f.pagina
                img = cortar(pg.imagem, f.recorte, f.rot90)
                exif = montar_exif(meta, pg.dpi)
                if cfg.formato == "jpeg":
                    salvar_jpeg(caminhos[id(f)], img, exif, data)
                else:
                    salvar_png(caminhos[id(f)], img, pg.dpi, pg.icc, exif, xmp, data)
                feitas += 1
                ao_progresso(feitas, total)
            _salvar_recortes(pasta, arquivo, len(leitor), lista, meta)
    return pastas


def _salvar_recortes(pasta, arquivo, paginas, fotos, meta):
    dados = {
        "versao": 2,
        "arquivo": arquivo.name,
        "paginas": paginas,
        "metadados": meta.como_dict(),
        "fotos": [{
            "pagina": f.pagina + 1, "indice": f.indice, "largura": f.largura, "altura": f.altura, "dpi": f.dpi,
            "estado": f.estado, "motivo": f.motivo, "rot90": f.rot90, "excluida": f.excluida,
            "auto": f.auto.como_dict(), "recorte": f.recorte.como_dict(),
        } for f in sorted(fotos, key=lambda f: (f.pagina, f.indice))],
    }
    (pasta / ARQUIVO_RECORTES).write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")


def _carregar_recortes(pasta, arquivo):
    """Lê o recortes.json (versão 1: uma foto por página; versão 2: várias)."""
    try:
        dados = json.loads((pasta / ARQUIVO_RECORTES).read_text(encoding="utf-8"))
        if dados.get("arquivo") != arquivo.name:
            return None
        fotos = {}
        for d in dados["fotos"]:
            fotos.setdefault(d["pagina"] - 1, []).append(d)
        return {"paginas": dados["paginas"], "fotos": fotos, "metadados": dados.get("metadados")}
    except (OSError, ValueError, KeyError, TypeError):
        return None
