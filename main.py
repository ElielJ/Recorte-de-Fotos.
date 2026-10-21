"""Recorte de Fotos.

Sem argumentos abre a interface. Com argumentos roda pela linha de comando:
    python main.py album.tiff outro.pdf C:\\Digitalizacoes --tamanho 15x21
"""
import argparse
import sys
from pathlib import Path


def linha_de_comando(args):
    from backend.processamento import Config, arquivos_existentes, extrair, listar_arquivos, salvar

    p = argparse.ArgumentParser(description="Extrai e recorta fotos de arquivos PDF/TIFF digitalizados.")
    p.add_argument("entradas", nargs="+", help="arquivos PDF/TIFF ou pastas")
    p.add_argument("--tamanho", default="15x21", help='tamanho esperado em cm, ex. "15x21", ou "livre"')
    p.add_argument("--margem", type=float, default=0.3, help="margem interna em mm (padrão 0.3)")
    p.add_argument("--saida", help="pasta de saída (padrão: ao lado de cada arquivo)")
    p.add_argument("--sobrescrever", action="store_true", help="substitui fotos já existentes")
    p.add_argument("--formato", choices=["png", "jpeg"], default="png",
                   help="png = máxima qualidade (padrão); jpeg = arquivos menores")
    a = p.parse_args(args)

    tamanho = None if a.tamanho == "livre" else tuple(float(x) for x in a.tamanho.lower().split("x"))
    cfg = Config(tamanho, a.margem, Path(a.saida) if a.saida else None, a.formato)
    arquivos = listar_arquivos(a.entradas)
    if not arquivos:
        print("Nenhum arquivo PDF/TIFF encontrado.")
        return 1
    for arquivo in arquivos:
        print(f"{arquivo.name}:")
        fotos = []
        for foto, i, total in extrair(arquivo, cfg):
            fotos.append(foto)
            aviso = f"  REVISAR: {foto.motivo}" if foto.estado == "revisar" else ""
            print(f"  página {i}/{total}, foto {foto.indice + 1}{aviso}")
        existentes = arquivos_existentes(fotos, cfg)
        if existentes and not a.sobrescrever:
            print(f"  {len(existentes)} foto(s) já existem; use --sobrescrever para substituir. Arquivo ignorado.")
            continue
        pastas = salvar(fotos, cfg)
        print(f"  {sum(not f.excluida for f in fotos)} foto(s) salvas em {pastas[0]}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(linha_de_comando(sys.argv[1:]))
    from frontend.janela import executar
    sys.exit(executar())
