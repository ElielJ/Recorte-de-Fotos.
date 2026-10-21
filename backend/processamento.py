"""Fluxo completo de um álbum: extrair as fotos dos arquivos, salvar e reabrir o trabalho.

Um álbum é uma sessão de extração: um ou mais arquivos PDF/TIFF cujas fotos vão para uma pasta
com o nome do álbum, numeradas em sequência (Album_001.png, Album_002.png...).
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from . import leitura
from .deteccao import detectar, ordem_leitura
from .gravacao import salvar_jpeg, salvar_png
from .metadados import Metadados, montar_exif, montar_xmp
from .recorte import Recorte, cortar, previa

ARQUIVO_ALBUM = "album.json"
EXTENSOES_SAIDA = {"png": ".png", "jpeg": ".jpg"}
_RESERVADOS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


@dataclass
class Config:
    album: str | None = None  # nome do álbum (na interface, definido ao salvar)
    pasta_album: Path | None = None  # pasta do álbum (criada ao salvar)
    tamanho_cm: tuple[float, float] | None = (10.0, 15.0)  # None = não validar
    margem_mm: float = 0.3
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

    def tamanho_cm(self):
        if not self.dpi:
            return None
        w, h = self.recorte.w / self.dpi * 2.54, self.recorte.h / self.dpi * 2.54
        return (h, w) if self.rot90 % 2 else (w, h)


def nome_seguro(nome):
    """Nome do álbum válido como nome de pasta/arquivo no Windows."""
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", nome)
    nome = re.sub(r"\s+", " ", nome).strip().rstrip(". ")
    return f"_{nome}" if nome.upper() in _RESERVADOS else nome


def pasta_album(base, album):
    return Path(base) / nome_seguro(album)


def listar_arquivos(caminhos):
    """Expande pastas (sem subpastas) e mantém só PDF/TIFF."""
    arquivos = []
    for c in map(Path, caminhos):
        itens = sorted(c.iterdir()) if c.is_dir() else [c]
        arquivos += [a for a in itens if a.is_file() and a.suffix.lower() in leitura.EXTENSOES]
    return arquivos


def carregar_album(pasta):
    """Lê o album.json de um álbum já salvo (ou None)."""
    try:
        dados = json.loads((Path(pasta) / ARQUIVO_ALBUM).read_text(encoding="utf-8"))
        fontes = {f["arquivo"]: {"paginas": f["paginas"], "fotos": {}} for f in dados["fontes"]}
        for d in dados["fotos"]:
            fontes[d["arquivo"]]["fotos"].setdefault(d["pagina"] - 1, []).append(d)
        return {"album": dados["album"], "metadados": Metadados.de_dict(dados.get("metadados")),
                "salvos": dados.get("salvos", []), "fontes": fontes}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def extrair(arquivo, cfg, album_salvo=None, cancelado=lambda: False):
    """Gera (foto, página atual, total de páginas) para cada foto encontrada no arquivo.

    Se o álbum já foi salvo antes com este arquivo, reaproveita os recortes dele.
    """
    arquivo = Path(arquivo)
    fonte = (album_salvo or {}).get("fontes", {}).get(arquivo.name)
    with leitura.abrir(arquivo) as leitor:
        total = len(leitor)
        if fonte and fonte["paginas"] != total:
            fonte = None
        for i in range(total):
            if cancelado():
                return
            pg = leitor.pagina(i)
            alt, larg = pg.imagem.shape[:2]
            entradas = fonte["fotos"].get(i) if fonte else None
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


def _ordenadas(fotos):
    """Índices das fotos na ordem do álbum: arquivo (na ordem em que foi adicionado), página, posição."""
    ordem_arquivo = {}
    for f in fotos:
        ordem_arquivo.setdefault(f.arquivo, len(ordem_arquivo))
    return sorted(range(len(fotos)), key=lambda i: (ordem_arquivo[fotos[i].arquivo], fotos[i].pagina,
                                                    fotos[i].indice))


def destinos(fotos, cfg):
    """Caminho de saída de cada foto (mesma ordem da lista); None para as excluídas.

    As fotos são numeradas em sequência no álbum: Album_001.png, Album_002.png...
    """
    validas = [i for i in _ordenadas(fotos) if not fotos[i].excluida]
    digitos = max(3, len(str(len(validas))))
    prefixo, ext = nome_seguro(cfg.album), EXTENSOES_SAIDA[cfg.formato]
    caminhos = [None] * len(fotos)
    for n, i in enumerate(validas, 1):
        caminhos[i] = cfg.pasta_album / f"{prefixo}_{n:0{digitos}d}{ext}"
    return caminhos


def conflitos(fotos, cfg):
    """(fotos que serão substituídas, fotos antigas do álbum que deixam de existir na nova numeração)."""
    novos = {c for c in destinos(fotos, cfg) if c}
    salvo = carregar_album(cfg.pasta_album)
    ext = EXTENSOES_SAIDA[cfg.formato]
    antigas = [cfg.pasta_album / n for n in (salvo["salvos"] if salvo else [])
               if Path(n).suffix == ext and cfg.pasta_album / n not in novos and (cfg.pasta_album / n).exists()]
    return sorted(c for c in novos if c.exists()), antigas


def carregar_metadados(cfg):
    """Metadados salvos anteriormente no album.json (ou vazios)."""
    salvo = carregar_album(cfg.pasta_album) if cfg.pasta_album else None
    return salvo["metadados"] if salvo else Metadados()


def salvar(fotos, cfg, ao_progresso=lambda feitas, total: None, cancelado=lambda: False, metadados=None):
    """Grava as fotos do álbum (PNG ou JPEG) com os metadados e o album.json. Retorna a pasta do álbum.

    Fotos antigas deste álbum (mesmo formato) que saíram da numeração, por exclusão ou divisão de
    recortes, são apagadas para não sobrarem arquivos desatualizados.
    """
    meta = metadados or carregar_metadados(cfg)
    data = meta.data()
    xmp = None if meta.vazio() else montar_xmp(meta)
    _, antigas = conflitos(fotos, cfg)
    cfg.pasta_album.mkdir(parents=True, exist_ok=True)
    caminhos = destinos(fotos, cfg)
    total = sum(c is not None for c in caminhos)
    feitas = 0
    paginas = {}
    ordem = _ordenadas(fotos)
    for arquivo in dict.fromkeys(fotos[i].arquivo for i in ordem):
        with leitura.abrir(arquivo) as leitor:
            paginas[arquivo] = len(leitor)
            pg, pagina_lida = None, None
            for i in ordem:
                f = fotos[i]
                if f.arquivo != arquivo or caminhos[i] is None:
                    continue
                if cancelado():
                    return cfg.pasta_album
                if f.pagina != pagina_lida:  # várias fotos da mesma página: lê a página uma vez só
                    pg, pagina_lida = leitor.pagina(f.pagina), f.pagina
                img = cortar(pg.imagem, f.recorte, f.rot90)
                exif = montar_exif(meta, pg.dpi)
                if cfg.formato == "jpeg":
                    salvar_jpeg(caminhos[i], img, exif, data)
                else:
                    salvar_png(caminhos[i], img, pg.dpi, pg.icc, exif, xmp, data)
                feitas += 1
                ao_progresso(feitas, total)
    for c in antigas:
        c.unlink(missing_ok=True)
    _salvar_album(cfg, fotos, ordem, paginas, meta, [c.name for c in caminhos if c])
    return cfg.pasta_album


def _salvar_album(cfg, fotos, ordem, paginas, meta, salvos):
    dados = {
        "versao": 3,
        "album": cfg.album,
        "formato": cfg.formato,
        "metadados": meta.como_dict(),
        "fontes": [{"arquivo": a.name, "caminho": str(a), "paginas": n} for a, n in paginas.items()],
        "salvos": salvos,
        "fotos": [{
            "arquivo": f.arquivo.name, "pagina": f.pagina + 1, "indice": f.indice,
            "largura": f.largura, "altura": f.altura, "dpi": f.dpi,
            "estado": f.estado, "motivo": f.motivo, "rot90": f.rot90, "excluida": f.excluida,
            "auto": f.auto.como_dict(), "recorte": f.recorte.como_dict(),
        } for f in (fotos[i] for i in ordem)],
    }
    (cfg.pasta_album / ARQUIVO_ALBUM).write_text(json.dumps(dados, indent=2, ensure_ascii=False),
                                                 encoding="utf-8")
