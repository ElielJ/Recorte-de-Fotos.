"""Fluxo completo de um álbum: extrair as fotos dos arquivos e salvá-las.

Um álbum é uma sessão de extração: um ou mais arquivos PDF/TIFF cujas fotos vão para uma pasta
com o nome do álbum, numeradas em sequência (Album_001.png, Album_002.png...). A pasta recebe só as
fotos; nenhum arquivo de controle é gravado.
"""
import os
import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from . import leitura
from .deteccao import detectar, ordem_leitura
from .gravacao import salvar_jpeg, salvar_png
from .metadados import Metadados, montar_exif, montar_xmp
from .recorte import Recorte, cortar, previa

MAX_GRAVACOES_SIMULTANEAS = 6
MB_POR_GRAVACAO = 250  # medido: ~150 MB por foto A4 600 dpi em andamento, com folga (48 bits usa o dobro)
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


def fotos_do_album(pasta, album):
    """Fotos já existentes na pasta com a numeração deste álbum (Album_001.png, Album_002.jpg...)."""
    padrao = re.compile(re.escape(nome_seguro(album)) + r"_\d{3,}\.(png|jpg)", re.IGNORECASE)
    pasta = Path(pasta)
    return sorted(c for c in pasta.iterdir() if padrao.fullmatch(c.name)) if pasta.is_dir() else []


def extrair(arquivo, cfg, cancelado=lambda: False):
    """Gera (foto, página atual, total de páginas) para cada foto encontrada no arquivo."""
    arquivo = Path(arquivo)
    with leitura.abrir(arquivo) as leitor:
        total = len(leitor)
        for i in range(total):
            if cancelado():
                return
            pg = leitor.pagina(i)
            alt, larg = pg.imagem.shape[:2]
            fotos = []
            for k, (r, estado, motivo) in enumerate(detectar(pg.imagem, pg.dpi, cfg.tamanho_cm, cfg.margem_mm)):
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


def conflitos(fotos, cfg, anteriores=()):
    """(fotos que serão substituídas, fotos antigas que deixam de existir na nova numeração).

    anteriores: fotos gravadas antes nesta mesma sessão. Só elas podem ser apagadas: fotos que já
    estavam na pasta (de outro álbum, por exemplo) no máximo são sobrescritas, nunca removidas.
    """
    novos = {c for c in destinos(fotos, cfg) if c}
    antigas = [c for c in anteriores if c not in novos and c.exists()]
    return sorted(c for c in novos if c.exists()), antigas


def _memoria_livre_mb():
    """RAM disponível no Windows (None em outros sistemas ou se não for possível consultar)."""
    try:
        import ctypes

        class Estado(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        estado = Estado(dwLength=ctypes.sizeof(Estado))
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado)):
            return estado.ullAvailPhys // 2 ** 20
    except (AttributeError, OSError):
        pass
    return None


def gravacoes_simultaneas():
    """Quantas fotos gravar em paralelo: limitado pelos núcleos e pela memória livre no momento."""
    n = min(MAX_GRAVACOES_SIMULTANEAS, max(1, (os.cpu_count() or 2) - 1))
    livre = _memoria_livre_mb()
    return max(1, min(n, livre // MB_POR_GRAVACAO)) if livre is not None else n


def salvar(fotos, cfg, ao_progresso=lambda feitas, total: None, cancelado=lambda: False, metadados=None,
           anteriores=()):
    """Grava as fotos do álbum (PNG ou JPEG) com os metadados. Retorna a lista de arquivos gravados.

    anteriores: fotos gravadas antes nesta sessão; as que saíram da numeração (por exclusão ou divisão
    de recortes) são apagadas para não sobrarem arquivos desatualizados.
    """
    meta = metadados or Metadados()
    data = meta.data()
    xmp = None if meta.vazio() else montar_xmp(meta)
    _, antigas = conflitos(fotos, cfg, anteriores)
    cfg.pasta_album.mkdir(parents=True, exist_ok=True)
    caminhos = destinos(fotos, cfg)
    total = sum(c is not None for c in caminhos)
    feitas = 0
    pendentes = set()
    gravados = []
    ordem = _ordenadas(fotos)

    def esperar(ate):
        """Espera até restarem no máximo 'ate' gravações em andamento (repassa erros delas)."""
        nonlocal feitas, pendentes
        while len(pendentes) > ate:
            prontas, pendentes = wait(pendentes, return_when=FIRST_COMPLETED)
            for p in prontas:
                p.result()
                feitas += 1
                ao_progresso(feitas, total)

    # Esta thread lê as páginas e recorta; a compressão (o gargalo, 1 núcleo por foto) roda em paralelo.
    simultaneas = gravacoes_simultaneas()
    with ThreadPoolExecutor(simultaneas) as gravador:
        for arquivo in dict.fromkeys(fotos[i].arquivo for i in ordem):
            with leitura.abrir(arquivo) as leitor:
                pg, pagina_lida = None, None
                for i in ordem:
                    f = fotos[i]
                    if f.arquivo != arquivo or caminhos[i] is None:
                        continue
                    if cancelado():
                        esperar(0)
                        return gravados
                    if f.pagina != pagina_lida:  # várias fotos da mesma página: lê a página uma vez só
                        pg, pagina_lida = leitor.pagina(f.pagina), f.pagina
                    esperar(simultaneas - 1)  # limita as fotos na memória ao mesmo tempo
                    img = cortar(pg.imagem, f.recorte, f.rot90)
                    exif = montar_exif(meta, pg.dpi)
                    if cfg.formato == "jpeg":
                        tarefa = gravador.submit(salvar_jpeg, caminhos[i], img, exif, data)
                    else:
                        tarefa = gravador.submit(salvar_png, caminhos[i], img, pg.dpi, pg.icc, exif, xmp, data)
                    pendentes.add(tarefa)
                    gravados.append(caminhos[i])
        esperar(0)
    for c in antigas:
        c.unlink(missing_ok=True)
    return gravados
