# Recorte de Fotos

Programa para Windows que **extrai e recorta automaticamente fotos digitalizadas** a partir de arquivos PDF ou TIFF, com a máxima qualidade possível. Permite revisar e ajustar cada recorte e gravar data, local e descrição dentro das fotos, para que serviços como o Google Fotos as organizem corretamente.

---

## Sumário

- [O problema](#o-problema)
- [Como o programa resolve](#como-o-programa-resolve)
- [Instalação](#instalação)
- [Como digitalizar (recomendações)](#como-digitalizar-recomendações)
- [Como usar](#como-usar)
- [Formatos de saída: PNG ou JPEG](#formatos-de-saída-png-ou-jpeg)
- [Metadados: data, local e descrição](#metadados-data-local-e-descrição)
- [Arquivos gerados](#arquivos-gerados)
- [Linha de comando](#linha-de-comando)
- [Limitações conhecidas](#limitações-conhecidas)
- [Privacidade](#privacidade)
- [Solução de problemas](#solução-de-problemas)
- [Para desenvolvedores](#para-desenvolvedores)

---

## O problema

Fotos antigas em papel são digitalizadas num scanner de documentos (uma por vez, pelo alimentador) ou no vidro de uma impressora multifuncional (várias de uma vez). O scanner sempre gera uma **página A4 inteira**, com uma ou mais fotos ocupando só uma parte e o resto preenchido pelo fundo do scanner. Normalmente várias páginas vão para um único PDF ou TIFF.

Transformar isso em fotos utilizáveis à mão é trabalhoso e arriscado:

- É preciso abrir cada página e recortar cada foto manualmente num editor de imagens.
- O recorte manual raramente é preciso: sobra uma faixa de fundo ou se corta parte da foto.
- A foto costuma entrar levemente torta no scanner e precisa ser endireitada.
- Cada vez que a imagem é aberta e salva de novo em formatos com perdas, como JPEG, a qualidade cai.
- As fotos digitalizadas ficam com a data da digitalização. Ao enviá-las ao Google Fotos, aparecem todas "tiradas hoje", misturadas com as fotos atuais, e sem localização.

## Como o programa resolve

```text
PDF/TIFF ──► extrai a página original ──► detecta as fotos ──► você revisa e ajusta ──► grava PNG/JPEG
             (sem perda de qualidade)     (uma ou várias;      (editor visual)          (com data, local
                                           posição, tamanho                             e descrição)
                                           e inclinação)
```

1. **Leitura sem perdas.** Em TIFF, cada página é lida diretamente. Em PDF, o programa **extrai a imagem original** que o scanner gravou, em vez de "imprimir" a página numa nova resolução, o que reamostraria a imagem. Páginas giradas no PDF são corrigidas automaticamente.
2. **Detecção automática das fotos.** O programa estima a cor do fundo do scanner pelas bordas da página e separa as fotos desse fundo. **Todas as fotos da página** são encontradas (manchas e poeira são ignoradas pelo tamanho) e numeradas em ordem de leitura: de cima para baixo e, na mesma linha, da esquerda para a direita. Para cada uma é calculado o retângulo exato: posição, largura, altura e **ângulo de inclinação**. Nos testes com imagens sintéticas, o erro ficou em cerca de 1 pixel na posição, e o ângulo saiu igual ao real.
3. **Recorte preservando os pixels originais.** Se a inclinação for desprezível (menos de 0,2°), a foto é recortada **sem rotação**, mantendo os pixels intactos. Se for preciso endireitar, a rotação é feita **uma única vez**, com interpolação de alta qualidade (Lanczos). Uma margem interna configurável elimina restos de fundo na borda.
4. **Validação.** O tamanho medido em centímetros, calculado pela resolução do arquivo, é comparado com o tamanho esperado da foto (por exemplo 10x15). Fotos com tamanho diferente, contorno irregular ou outras suspeitas são marcadas **"Revisar"**. Um recorte com o tamanho de duas fotos recebe o aviso "parece conter duas fotos encostadas". O programa **não divide sozinho**, porque uma foto 15x21 tem o mesmo tamanho de duas 10x15.
5. **Revisão e edição visual.** Uma tela mostra todas as fotos extraídas, com as suspeitas primeiro. O editor mostra **todos os recortes da página** sobre a imagem original e permite ajustar cantos, bordas, posição e ângulo, com zoom até o nível do pixel, além de **adicionar**, **dividir** ou **remover** recortes. **Toda edição recorta de novo a partir da página original**, então ajustar várias vezes não perde qualidade.
6. **Gravação num álbum, com metadados.** Cada sessão de extração é um **álbum**: os arquivos adicionados (um ou vários PDF/TIFF) viram uma pasta com o nome do álbum, com as fotos numeradas em sequência. Elas são gravadas em PNG (sem perdas) ou JPEG (menor), com a resolução (DPI), o perfil de cor, quando existir, e os metadados do álbum: data estimada, coordenadas GPS e descrição.

---

## Instalação

### Requisitos

- Windows 10 ou 11.
- Internet **apenas na primeira execução**, para baixar o Python e as bibliotecas (~500 MB instalados).
- Memória: o programa usa ~100–150 MB parado e chega a ~550 MB ao extrair páginas A4 a 600 dpi (o dobro em digitalizações de 48 bits ou páginas A3). Ao salvar, várias fotos são gravadas em paralelo (até 6, ~150 MB cada), conforme os núcleos do processador e a memória livre no momento; com pouca RAM livre, o programa grava menos fotos ao mesmo tempo. Computadores com 4 GB de RAM ou mais funcionam bem.

### Primeira execução

1. Copie a pasta do projeto para o computador. Se a pasta tiver uma subpasta `.venv` vinda de outro computador, ela pode ser apagada; o programa a recria.
2. Dê **duplo clique em `Recortar Fotos.bat`**.

O `.bat` verifica e instala sozinho o que faltar:

| Situação | O que o `.bat` faz |
| --- | --- |
| Python 3.11 ou mais novo não encontrado | Instala o Python 3.12 pelo `winget`, só para o usuário, sem pedir senha de administrador |
| Ambiente do programa (`.venv`) ausente ou quebrado | Cria um novo |
| Bibliotecas ausentes ou `requirements.txt` alterado | Instala ou atualiza |
| Tudo pronto | Abre o programa direto, sem janela de console |

Se o `winget` não estiver disponível, o `.bat` mostra o link para instalar o Python manualmente pelo site [python.org](https://www.python.org/downloads/). Marque a opção **"Add python.exe to PATH"** e rode o `.bat` de novo.

---

## Como digitalizar (recomendações)

A qualidade final nunca é maior que a da digitalização. Configure o software do scanner (PaperStream/ScandAll) assim:

| Configuração | Recomendado | Por quê |
| --- | --- | --- |
| Formato do arquivo | **TIFF** (PDF também é aceito) | O TIFF pode ser gravado sem perdas |
| Compressão | **Nenhuma ou LZW** | A compressão JPEG descarta detalhes na própria digitalização. Um TIFF com JPEG fica ~40x menor, mas com perdas. |
| Resolução | **600 dpi** | Fotos em papel raramente têm detalhe acima disso |
| Cor | 24 bits (ou 48 bits, se disponível) | O programa preserva 16 bits por canal no PNG |
| Tamanho da página | A4 | |
| Corte, endireitamento e nitidez automáticos | **Desligados** | O programa faz isso com mais controle |
| Fotos por página | Uma ou várias | O programa detecta todas as fotos da página |

**Scanner com alimentador** (ex.: Fujitsu fi-6130): uma foto por página.

> **Cuidado com o alimentador:** fotos antigas podem riscar, dobrar ou grudar nos roletes. Use uma **folha transportadora (carrier sheet)**.

Nesse tipo de scanner, a foto sai "encostada" na borda de cima da página. Isso é normal: quando o tamanho confere com o esperado, o programa sabe que a foto está inteira.

**Scanner de mesa (vidro de impressora multifuncional):** cabem várias fotos por página.

- Deixe **pelo menos 5 mm de espaço** entre as fotos. Fotos encostadas viram um único recorte e precisam ser divididas no editor.
- Mantenha a tampa fechada; o fundo dela é o "fundo" que o programa separa das fotos.
- As fotos podem ficar levemente tortas: a inclinação de cada uma é corrigida separadamente.

---

## Como usar

### 1. Tela inicial

1. **Adicione os arquivos:** arraste PDFs/TIFFs (ou uma pasta) para a janela, ou use **Adicionar arquivos…** / **Adicionar pasta…**.
2. **Ajuste as opções** (elas ficam gravadas para as próximas vezes):
   - **Tamanho da foto:** 10x15, 15x21, 15x25, outro tamanho ou "Não validar". Usado para conferir se a foto foi detectada inteira.
   - **Margem interna:** quanto recortar para dentro da borda detectada. O padrão é 0,3 mm, cerca de 7 pixels a 600 dpi.
   - **Formato das fotos:** PNG ou JPEG (veja [abaixo](#formatos-de-saída-png-ou-jpeg)).
3. Clique em **Extrair fotos**.

Todos os arquivos da lista formam **um álbum**. O nome do álbum é escolhido no final, ao **salvar**. Para criar outro álbum, volte à tela inicial (**Nova extração**) e comece uma nova lista.

### 2. Tela de revisão

As fotos aparecem à medida que são processadas.

- **Lista à esquerda:** miniatura, medidas e estado de cada foto. As que precisam de atenção aparecem primeiro. Em páginas com várias fotos, o cartão mostra a posição na página (ex.: "pág. 1 · 2/3").
- **Centro:** a foto selecionada, com zoom (roda do mouse), arraste para navegar, giro de 90° e ajustar à tela.
- **Painel à direita:** o diagnóstico (por que a foto está em "Revisar"), as especificações técnicas, os metadados do álbum e as ações.

Estados de cada foto:

| Estado | Significado |
| --- | --- |
| 🟢 **OK** | Detectada automaticamente com o tamanho esperado |
| 🟠 **Revisar** | Algo não conferiu; o motivo aparece no painel de diagnóstico |
| 🔵 **Editada** | Você ajustou o recorte manualmente |
| 🔴 **Excluída** | Não será salva |

Ações e atalhos:

| Ação | Atalho |
| --- | --- |
| Editar recorte | `Enter` ou duplo clique |
| Aprovar / reabrir para revisão | `Ctrl+K` (ao aprovar, pula para a próxima pendente) |
| Girar 90° à esquerda / à direita | `Ctrl+←` / `Ctrl+→` |
| Excluir / restaurar | `Delete` |
| Foto anterior / próxima | `↑` / `↓` |
| Metadados do álbum | `Ctrl+M` |
| Salvar todas | `Ctrl+S` |

Também há o filtro (Todas / Para revisar / Prontas / Excluídas), o link **Aprovar restantes** e seleção múltipla com `Ctrl`/`Shift` para girar, aprovar ou excluir várias fotos de uma vez.

### 3. Editor de recortes

Mostra a página digitalizada inteira com **todos os recortes da página**, numerados na ordem em que serão salvos. O recorte selecionado tem alças azuis; os outros aparecem tracejados. **Clique** num recorte para selecioná-lo.

- Arraste os **cantos** e as **bordas** para ajustar o tamanho.
- Arraste o **interior** para mover o recorte.
- Arraste o **círculo** acima do recorte para girar, ou digite o ângulo exato.
- Use a **roda do mouse** para dar zoom. **Zoom 100%** mostra os pixels reais, para um ajuste preciso.
- **Restaurar automático** volta ao recorte detectado pelo programa.
- **Adicionar foto** cria um recorte novo, do tamanho esperado, para uma foto que não foi detectada.
- **Dividir em duas** separa ao meio um recorte que juntou duas fotos encostadas; depois é só ajustar cada metade.
- **Remover esta foto** apaga um recorte falso, como uma mancha ou um papel detectado como foto.
- **Aplicar** volta à revisão. As fotos alteradas ou criadas ficam marcadas como "Editada".

### 4. Salvar

Clique em **Salvar todas** e **dê um nome ao álbum** (por exemplo, "Férias em Santos 1987"). A janela mostra a pasta que será criada: por padrão, na mesma pasta do primeiro arquivo da lista. **Alterar local…** permite escolher outro lugar. Ao final, o programa oferece abrir a pasta do álbum.

- **Salvar de novo na mesma sessão:** a janela já vem com o nome usado antes, e as fotos do álbum são atualizadas, com confirmação se alguma for substituída ou apagada.
- **Nome de um álbum que já existe no mesmo local:** a janela avisa quantas fotos ele tem, e o botão vira **"Substituir fotos existentes"**. Se continuar, as fotos com a mesma numeração são sobrescritas; as demais e qualquer outro arquivo da pasta ficam intactos. Para manter aquele álbum, escolha outro nome.

---

## Formatos de saída: PNG ou JPEG

| | **PNG** | **JPEG** |
| --- | --- | --- |
| Qualidade | Máxima, **sem nenhuma perda** | Muito alta (qualidade 95, cores sem subamostragem), com pequena perda por compressão |
| Profundidade de cor | Preserva 16 bits por canal, quando houver | 8 bits por canal |
| Tamanho (foto 10x15 a 600 dpi) | ~10 a 25 MB | ~3 a 5 MB, cerca de 4x menor |
| Indicado para | **Arquivar** e **editar** depois | **Compartilhar** e enviar a serviços de fotos |

O PNG não melhora uma digitalização feita em JPEG: ele preserva exatamente o que o scanner entregou e garante que nenhuma perda nova aconteça.

A compressão do PNG usa o nível 6. O nível máximo (9) levava cerca de 7 vezes mais tempo para gerar arquivos só ~3% menores, com a mesma qualidade.

---

## Metadados: data, local e descrição

Na revisão, clique em **Metadados** (ou `Ctrl+M`). Os dados valem para **todas as fotos do álbum**. Se as fotos forem de épocas ou lugares diferentes, crie um álbum para cada grupo.

| Campo | Como preencher |
| --- | --- |
| **Data estimada** | Ano (obrigatório), mês e dia (opcionais, "não sei") |
| **Nome do local** | Texto livre, por exemplo "Santos, SP" |
| **Coordenadas** | No Google Maps, clique com o botão direito no local e clique nos números que aparecem no topo do menu (eles são copiados). Cole no campo. Exemplo: `-23.9608, -46.3336` |
| **Descrição** | Texto livre, por exemplo "Férias em família" |

O que é gravado em cada foto:

- **EXIF `DateTimeOriginal`** com fuso horário: é a data que os organizadores de fotos usam para posicionar a foto na linha do tempo.
- **EXIF GPS**: faz a foto aparecer no mapa.
- **Descrição e local** como legenda, em EXIF e XMP.
- **XMP** com a data na precisão real (por exemplo, só "1987-06").
- **Data do próprio arquivo** igual à data estimada.

> **Datas incompletas:** os organizadores de fotos precisam de uma data completa. Se você informar só o ano, a foto é gravada como 1º de janeiro daquele ano, ao meio-dia. Se informar ano e mês, como dia 1º.
>
> **Preencha antes de enviar:** há relatos de que alterar a data de fotos que já estão no Google Fotos pode não ter efeito sem apagá-las e enviá-las de novo.

---

## Arquivos gerados

Todas as fotos do álbum vão para **uma pasta com o nome do álbum**, numeradas em sequência. A pasta recebe **só as fotos**: nenhum arquivo de controle é gravado junto.

```text
Digitalizações/
├── scan parte 1.tif             ← arquivos digitalizados (formam o álbum)
├── scan parte 2.pdf
└── Férias 1987/                 ← pasta do álbum, criada pelo programa
    ├── Férias 1987_001.png
    ├── Férias 1987_002.png
    ├── …
    └── Férias 1987_027.png
```

- A numeração segue a ordem dos arquivos na lista, depois a ordem das páginas e, dentro de cada página, a ordem de leitura (de cima para baixo, da esquerda para a direita).
- Fotos excluídas não recebem número. Se você excluir, dividir ou remover fotos e salvar de novo **na mesma sessão**, a numeração é refeita, e o programa avisa e **apaga as fotos que ele mesmo gravou nessa sessão** e que ficaram fora da nova numeração. Arquivos que já estavam na pasta nunca são apagados.
- Caracteres que o Windows não aceita em nomes de pasta (`: / \ * ? " < > |`) são trocados por espaço.
- Os recortes e edições valem enquanto o programa está aberto. Depois de salvar, as fotos são o resultado final; para refazer um álbum, extraia os arquivos de novo.

---

## Linha de comando

Também é possível criar um álbum sem a interface, sem revisão manual. Todos os arquivos informados formam um único álbum:

```powershell
.\.venv\Scripts\python.exe main.py "C:\Digitalizacoes\parte1.tif" "C:\Digitalizacoes\parte2.pdf" --album "Férias 1987"
.\.venv\Scripts\python.exe main.py "C:\Digitalizacoes" --album "Família" --formato jpeg --saida "D:\Fotos"
```

| Opção | Descrição | Padrão |
| --- | --- | --- |
| `entradas` | Arquivos PDF/TIFF ou pastas (sem subpastas) | — |
| `--album` | Nome do álbum (e da pasta) | Nome do primeiro arquivo |
| `--tamanho` | Tamanho esperado em cm (`10x15`, `15x21`…) ou `livre` | `10x15` |
| `--margem` | Margem interna em mm | `0.3` |
| `--saida` | Onde criar a pasta do álbum | Pasta do primeiro arquivo |
| `--formato` | `png` ou `jpeg` | `png` |
| `--sobrescrever` | Atualiza um álbum que já tem fotos salvas | Desligado |

As fotos que precisariam de revisão aparecem como `REVISAR` na saída. Se a pasta do álbum já tiver fotos com os mesmos nomes, o programa só as substitui com `--sobrescrever`.

---

## Limitações conhecidas

- **Fotos encostadas.** Fotos sem espaço entre si viram um único recorte. O programa avisa, mas a divisão é feita por você no editor (**Dividir em duas**).
- **Área digitalizada menor que a página.** Quando o scanner digitaliza menos que o tamanho de página escolhido (ex.: para no fim da foto, ou vidro A4 com página A3), o driver completa o resto com branco ou preto puro. O programa reconhece esse preenchimento artificial (cor exata, sem nenhum ruído, encostada na borda) e o ignora. Se a digitalização terminou **antes** do fim da foto, a foto vai para "Revisar" com o aviso "a digitalização terminou antes do fim da foto": a parte que faltou não foi escaneada e precisa ser digitalizada de novo.
- **Áreas lisas não viram foto.** Recortes de cor uniforme, sem textura (preenchimento, tampa do scanner, páginas em branco), são descartados automaticamente; uma página em branco não gera nenhuma foto.
- **Fotos muito pequenas.** Para ignorar poeira e manchas, só contam como foto objetos com pelo menos 35% da área do tamanho esperado, ou 2% da página quando o tamanho não é validado. Uma foto muito menor que o tamanho esperado (ex.: 3x4 com a opção em 10x15) não é detectada; adicione-a no editor ou use "Não validar o tamanho".
- **Foto clara sobre fundo claro.** Áreas muito claras encostadas na borda da foto (céu, moldura branca) sobre o fundo branco do scanner podem fazer a detecção cortar a foto menor. Nesses casos a validação de tamanho manda a foto para "Revisar", e o ajuste se faz no editor. Se muitas fotos tiverem moldura branca, prefira o fundo preto no scanner, se houver essa opção.
- **PDF sem imagem única.** Se uma página de PDF não tiver uma única imagem do scanner, ela é renderizada a 600 dpi e marcada para revisão.
- **Resolução desconhecida.** Sem informação de DPI no arquivo, a validação de tamanho em cm não é feita.
- **JPEG e 16 bits.** A saída em JPEG é sempre de 8 bits por canal e não leva o perfil de cor (ICC).

## Privacidade

- **Todo o processamento é local.** Nenhuma foto sai do computador.
- O único acesso à internet, além da instalação, é o botão **"Abrir no Google Maps"**. Ele abre o navegador pesquisando o nome do local digitado, e só quando clicado.
- **A data e a localização ficam gravadas dentro das fotos.** Quem receber os arquivos poderá ver onde e quando foram tiradas. Se não quiser expor isso, deixe as coordenadas em branco.
- Fotos de família são dados pessoais: mantenha backup e cuidado ao compartilhar as pastas.

## Solução de problemas

| Problema | Solução |
| --- | --- |
| `.bat` diz que o Python não foi encontrado após instalar | Feche a janela e abra o `.bat` novamente |
| Erro ao instalar bibliotecas | Verifique a internet e rode o `.bat` de novo |
| Fotos continuam em "Revisar" com o motivo de tamanho | Confira o **Tamanho da foto** na tela inicial antes de extrair |
| Todas as fotos com "foto encostada na borda" | Normal em scanners com alimentador quando o tamanho não confere: ajuste o tamanho esperado |
| Fotos em PNG muito grandes | Escolha o formato **JPEG** ou digitalize com compressão LZW |
| Terminal Linux/WSL não roda o programa | O ambiente é do Windows: use PowerShell (`.\.venv\Scripts\Activate.ps1`) ou o `.bat` |
| PowerShell bloqueia o `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

---

## Para desenvolvedores

### Tecnologias

| Biblioteca | Uso |
| --- | --- |
| [PyMuPDF](https://pymupdf.readthedocs.io/) 1.28 | Leitura de PDF e extração da imagem original. A versão 2.0 não é usada porque carrega um módulo de análise de layout com IA (onnxruntime) a cada abertura, gastando ~100 MB de RAM e 1 s sem necessidade |
| [tifffile](https://github.com/cgohlke/tifffile) + imagecodecs | Leitura de TIFF (várias páginas, LZW, JPEG, 16 bits) |
| [OpenCV](https://opencv.org/) | Detecção, recorte, rotação e codificação PNG/JPEG |
| NumPy | Manipulação dos pixels |
| [PySide6](https://doc.qt.io/qtforpython/) (Qt) | Interface gráfica |
| [piexif](https://github.com/hMatoba/Piexif) | Montagem dos metadados EXIF |

Python 3.11 ou mais novo. As versões estão fixadas em [`requirements.txt`](requirements.txt).

### Estrutura

```text
Recorte Fotos/
├── main.py                  # entrada: abre a interface ou roda pela linha de comando
├── Recortar Fotos.bat       # instalador/lançador para Windows
├── requirements.txt
├── backend/                 # processamento das imagens (não depende da interface)
│   ├── leitura.py           # leitura de páginas TIFF/PDF sem perdas
│   ├── deteccao.py          # detecção automática da foto e validação
│   ├── recorte.py           # recorte/rotação a partir da página original
│   ├── gravacao.py          # PNG (com DPI, ICC, EXIF, XMP) e JPEG
│   ├── metadados.py         # data, local e descrição → EXIF/XMP
│   └── processamento.py     # fluxo do álbum: extrair, numerar e salvar
└── frontend/                # interface gráfica (PySide6)
    ├── janela.py            # janela principal e tela inicial
    ├── revisao.py           # tela de revisão
    ├── editor.py            # editor de recorte
    ├── metadados.py         # janela de metadados do álbum
    ├── tema.py              # tema escuro, ícones e estilos
    └── imagens.py           # conversões NumPy ↔ Qt
```

O `backend` não importa nada do `frontend`: ele pode ser usado sozinho, como faz o modo de linha de comando. O `frontend` usa o `backend` por imports absolutos (`from backend.processamento import ...`).

### Executar em modo de desenvolvimento

```powershell
.\.venv\Scripts\Activate.ps1
python main.py                      # interface
python main.py arquivo.tif          # linha de comando
```

### Convenção de coordenadas do recorte

Um recorte é definido por centro (`cx`, `cy`), largura (`w`), altura (`h`) e `angulo` em graus, no sentido horário na tela, como no Qt. O sistema de coordenadas é contínuo: o pixel `i` ocupa o intervalo `[i, i+1]`. O giro de 90° escolhido na revisão (`rot90`) é aplicado depois do recorte e fica guardado separadamente.
