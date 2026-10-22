"""Recorte de Fotos.

Sem argumentos abre a interface. Com argumentos roda pela linha de comando; todos os arquivos
informados formam um álbum:
    python main.py parte1.tiff parte2.pdf --album "Férias 1987" --tamanho 10x15
"""
import argparse
import sys


def linha_de_comando(args):
    from backend.processamento import Config, conflitos, extrair, listar_arquivos, nome_seguro, pasta_album, salvar

    p = argparse.ArgumentParser(description="Extrai e recorta as fotos de arquivos PDF/TIFF digitalizados "
                                            "e grava tudo num álbum (uma pasta com o nome do álbum).")
    p.add_argument("entradas", nargs="+", help="arquivos PDF/TIFF ou pastas")
    p.add_argument("--album", help="nome do álbum (padrão: nome do primeiro arquivo)")
    p.add_argument("--tamanho", default="10x15", help='tamanho esperado em cm, ex. "10x15", ou "livre"')
    p.add_argument("--margem", type=float, default=0.3, help="margem interna em mm (padrão 0.3)")
    p.add_argument("--saida", help="onde criar a pasta do álbum (padrão: pasta do primeiro arquivo)")
    p.add_argument("--sobrescrever", action="store_true", help="substitui fotos já existentes no álbum")
    p.add_argument("--formato", choices=["png", "jpeg"], default="png",
                   help="png = máxima qualidade (padrão); jpeg = arquivos menores")
    a = p.parse_args(args)

    arquivos = listar_arquivos(a.entradas)
    if not arquivos:
        print("Nenhum arquivo PDF/TIFF encontrado.")
        return 1
    nome = a.album or arquivos[0].stem
    if not nome_seguro(nome):
        print("Nome de álbum inválido.")
        return 1
    tamanho = None if a.tamanho == "livre" else tuple(float(x) for x in a.tamanho.lower().split("x"))
    pasta = pasta_album(a.saida or arquivos[0].parent, nome)
    cfg = Config(nome, pasta, tamanho, a.margem, a.formato)

    print(f"Álbum \"{nome}\" em {pasta}")
    fotos = []
    for arquivo in arquivos:
        print(f"{arquivo.name}:")
        for foto, i, total in extrair(arquivo, cfg):
            fotos.append(foto)
            aviso = f"  REVISAR: {foto.motivo}" if foto.estado == "revisar" else ""
            print(f"  página {i}/{total}, foto {foto.indice + 1}{aviso}")
    existentes, _ = conflitos(fotos, cfg)
    if existentes and not a.sobrescrever:
        print(f"A pasta do álbum já tem {len(existentes)} foto(s) com os mesmos nomes; "
              f"use --sobrescrever para substituí-las.")
        return 1
    salvar(fotos, cfg)
    print(f"{sum(not f.excluida for f in fotos)} foto(s) salvas em {pasta}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(linha_de_comando(sys.argv[1:]))
    from frontend.janela import executar
    sys.exit(executar())
