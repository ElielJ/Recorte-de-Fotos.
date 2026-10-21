"""Janela principal: tela inicial (escolha dos arquivos e opções) e tela de revisão."""
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, Signal
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
                               QGridLayout,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QStackedWidget, QVBoxLayout, QWidget)

from backend.processamento import Config, listar_arquivos
from . import tema
from .revisao import TelaRevisao

TAMANHOS = [("10 x 15 cm", (10.0, 15.0)), ("15 x 21 cm", (15.0, 21.0)), ("15 x 25 cm", (15.0, 25.0)),
            ("Outro…", "outro"), ("Não validar o tamanho", None)]

FORMATOS = {
    "png": ("PNG — máxima qualidade",
            "<b>PNG: máxima qualidade, sem nenhuma perda.</b> Guarda exatamente os pixels da digitalização "
            "(inclusive 16 bits de cor, quando houver). <b>Arquivos maiores</b>: cerca de 10 a 25 MB por foto "
            "10x15 a 600 dpi. Ideal para <b>arquivar</b> as fotos e para <b>editar</b> depois sem perder qualidade."),
    "jpeg": ("JPEG — arquivos menores",
             "<b>JPEG: qualidade muito alta (95), com uma pequena perda por compressão</b>, praticamente "
             "imperceptível a olho nu. <b>Arquivos cerca de 4x menores</b>: aprox. 3 a 5 MB por foto 10x15 a "
             "600 dpi. Abre em qualquer aparelho ou serviço; ideal para <b>compartilhar</b> e enviar a serviços "
             "de fotos. Cada nova edição salva em JPEG perde um pouco mais de qualidade."),
}


class LinhaArquivo(QFrame):
    """Linha da lista de arquivos: ícone, nome, pasta e botão de remover."""

    remover = Signal()

    def __init__(self, caminho):
        super().__init__()
        self.setObjectName("cartao")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 8, 8)
        lay.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(tema.icone("arquivo", "#60a5fa", 20).pixmap(20, 20))
        nome = QLabel(caminho.name)
        nome.setObjectName("nomeCartao")
        pasta = QLabel(str(caminho.parent))
        pasta.setObjectName("subtitulo")
        tipo = QLabel(caminho.suffix.upper().lstrip("."))
        tipo.setObjectName("contagem")
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(nome)
        col.addWidget(pasta)
        fechar = tema.botao("", "fechar", "icone", tema.SUAVE, "Remover da lista")
        fechar.clicked.connect(self.remover.emit)
        lay.addWidget(ic)
        lay.addLayout(col, 1)
        lay.addWidget(tipo)
        lay.addWidget(fechar)


class TelaInicial(QWidget):
    extrair = Signal(list, object, object)  # arquivos, Config, local onde criar a pasta do álbum

    def __init__(self):
        super().__init__()
        self.setObjectName("fundo")
        self.setAcceptDrops(True)
        self.config = QSettings("RecorteFotos", "RecorteFotos")

        # Cabeçalho
        cab = QFrame()
        cab.setObjectName("cabecalho")
        cab.setFixedHeight(64)
        lc = QHBoxLayout(cab)
        lc.setContentsMargins(18, 0, 18, 0)
        lc.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(tema.logo(36))
        titulos = QVBoxLayout()
        titulos.setSpacing(0)
        t = QLabel("Recorte de Fotos")
        t.setObjectName("titulo")
        s = QLabel("Extração e recorte de fotos digitalizadas")
        s.setObjectName("subtitulo")
        titulos.addStretch()
        titulos.addWidget(t)
        titulos.addWidget(s)
        titulos.addStretch()
        lc.addWidget(logo)
        lc.addLayout(titulos)
        lc.addStretch()

        # Área de soltar arquivos
        self.zona = QFrame()
        self.zona.setObjectName("zonaSoltar")
        lz = QVBoxLayout(self.zona)
        lz.setContentsMargins(20, 26, 20, 26)
        lz.setSpacing(8)
        ic = QLabel(alignment=Qt.AlignCenter)
        ic.setPixmap(tema.icone("upload", "#60a5fa", 34).pixmap(34, 34))
        texto = QLabel("Arraste arquivos PDF ou TIFF para cá", alignment=Qt.AlignCenter)
        texto.setObjectName("titulo")
        ou = QLabel("ou escolha no computador", alignment=Qt.AlignCenter)
        ou.setObjectName("subtitulo")
        botoes = QHBoxLayout()
        botoes.addStretch()
        b_arq = tema.botao("Adicionar arquivos…", "arquivo", cor_icone="#60a5fa")
        b_arq.clicked.connect(self._escolher_arquivos)
        b_pasta = tema.botao("Adicionar pasta…", "pasta", cor_icone="#60a5fa")
        b_pasta.clicked.connect(self._escolher_pasta)
        botoes.addWidget(b_arq)
        botoes.addWidget(b_pasta)
        botoes.addStretch()
        lz.addWidget(ic)
        lz.addWidget(texto)
        lz.addWidget(ou)
        lz.addSpacing(6)
        lz.addLayout(botoes)

        # Lista de arquivos
        cab_lista = QHBoxLayout()
        ic_l = QLabel()
        ic_l.setPixmap(tema.icone("camadas", "#60a5fa", 14).pixmap(14, 14))
        sec = QLabel("ARQUIVOS DO ÁLBUM")
        sec.setObjectName("secao")
        self.lbl_qtd = QLabel("0")
        self.lbl_qtd.setObjectName("contagem")
        b_limpar = tema.botao("Limpar lista", tipo="link")
        b_limpar.clicked.connect(self._limpar)
        cab_lista.addWidget(ic_l)
        cab_lista.addWidget(sec)
        cab_lista.addWidget(self.lbl_qtd)
        cab_lista.addStretch()
        cab_lista.addWidget(b_limpar)
        self.lista = QListWidget()
        self.lista.setSpacing(3)
        self.lista.setSelectionMode(QListWidget.NoSelection)
        self.lista.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.lbl_vazio = QLabel("Nenhum arquivo adicionado ainda.", alignment=Qt.AlignCenter)
        self.lbl_vazio.setObjectName("subtitulo")
        area_lista = QWidget()
        g = QGridLayout(area_lista)
        g.setContentsMargins(0, 0, 0, 0)
        g.addWidget(self.lista, 0, 0)
        g.addWidget(self.lbl_vazio, 0, 0)

        # Opções
        self.tamanho = QComboBox()
        for texto_t, valor in TAMANHOS:
            self.tamanho.addItem(texto_t, valor)
        self.larg = QDoubleSpinBox(minimum=1, maximum=60, decimals=1, suffix=" cm")
        self.alt = QDoubleSpinBox(minimum=1, maximum=60, decimals=1, suffix=" cm")
        self.outro = QWidget()
        lo = QHBoxLayout(self.outro)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.addWidget(self.larg)
        lo.addWidget(QLabel("x"))
        lo.addWidget(self.alt)
        self.tamanho.currentIndexChanged.connect(lambda: self.outro.setVisible(self.tamanho.currentData() == "outro"))
        self.margem = QDoubleSpinBox(minimum=0, maximum=5, decimals=2, singleStep=0.1, suffix=" mm")
        self.margem.setToolTip("Quanto recortar para dentro da borda detectada, para não sobrar fundo do scanner.")

        opcoes = QFrame()
        opcoes.setObjectName("caixa")
        lop = QGridLayout(opcoes)
        lop.setContentsMargins(16, 14, 16, 14)
        lop.setHorizontalSpacing(14)
        lop.setVerticalSpacing(6)
        for col, (rotulo, w) in enumerate((("Tamanho da foto", self.tamanho), ("Margem interna", self.margem))):
            r = QLabel(rotulo)
            r.setObjectName("subtitulo")
            lop.addWidget(r, 0, col)
            lop.addWidget(w, 1, col)
        lop.addWidget(self.outro, 2, 0)
        # Formato de saída: dois botões exclusivos e a explicação do escolhido logo abaixo.
        rot_formato = QLabel("Formato das fotos")
        rot_formato.setObjectName("subtitulo")
        self.grupo_formato = QButtonGroup(self)
        linha_formato = QHBoxLayout()
        linha_formato.setSpacing(8)
        for chave, (titulo, _) in FORMATOS.items():
            b = tema.botao(titulo, "imagem", "segmento", "#60a5fa")
            b.setCheckable(True)
            b.setProperty("formato", chave)
            self.grupo_formato.addButton(b)
            linha_formato.addWidget(b)
        linha_formato.addStretch()
        self.grupo_formato.buttonToggled.connect(self._atualizar_formato)
        self.explicacao = QLabel(textFormat=Qt.RichText, wordWrap=True)
        self.explicacao.setObjectName("explicacao")
        lop.addWidget(rot_formato, 3, 0, 1, 2)
        lop.addLayout(linha_formato, 4, 0, 1, 2)
        lop.addWidget(self.explicacao, 5, 0, 1, 2)

        # Rodapé
        rodape = QHBoxLayout()
        info = QLabel()
        info.setPixmap(tema.icone("info", "#60a5fa", 14).pixmap(14, 14))
        nota = QLabel("Os arquivos desta lista formam um álbum. Ao salvar as fotos, você dá um nome a ele e elas "
                      "vão para uma pasta com esse nome.")
        nota.setObjectName("subtitulo")
        self.btn_extrair = tema.botao("Extrair fotos", "crop", "primario", "white")
        self.btn_extrair.setIconSize(QSize(16, 16))
        self.btn_extrair.clicked.connect(self._extrair)
        rodape.addWidget(info)
        rodape.addWidget(nota)
        rodape.addStretch()
        rodape.addWidget(self.btn_extrair)

        corpo = QWidget()
        corpo.setMaximumWidth(980)
        lb = QVBoxLayout(corpo)
        lb.setContentsMargins(24, 22, 24, 22)
        lb.setSpacing(14)
        lb.addWidget(self.zona)
        lb.addLayout(cab_lista)
        lb.addWidget(area_lista, 1)
        lb.addWidget(opcoes)
        lb.addLayout(rodape)
        centro = QHBoxLayout()
        centro.addStretch()
        centro.addWidget(corpo, 100)
        centro.addStretch()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(cab)
        lay.addLayout(centro, 1)

        self._carregar_opcoes()
        self._atualizar_lista()

    # ---------------- arquivos ----------------

    def arquivos(self):
        return [Path(self.lista.item(i).data(Qt.UserRole)) for i in range(self.lista.count())]

    def adicionar(self, caminhos):
        atuais = set(self.arquivos())
        novos = [a for a in listar_arquivos(caminhos) if a not in atuais]
        for a in novos:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, str(a))
            item.setSizeHint(QSize(0, 56))
            self.lista.addItem(item)
            linha = LinhaArquivo(a)
            linha.remover.connect(lambda it=item: self._remover(it))
            self.lista.setItemWidget(item, linha)
        if caminhos and not novos and not atuais.intersection(map(Path, caminhos)):
            QMessageBox.information(self, "Nenhum arquivo", "Nenhum arquivo PDF ou TIFF foi encontrado.")
        self._atualizar_lista()

    def _escolher_arquivos(self):
        nomes, _ = QFileDialog.getOpenFileNames(self, "Escolher arquivos", self.config.value("ultima_pasta", ""),
                                                "Digitalizações (*.pdf *.tif *.tiff)")
        if nomes:
            self.config.setValue("ultima_pasta", str(Path(nomes[0]).parent))
            self.adicionar(nomes)

    def _escolher_pasta(self):
        pasta = QFileDialog.getExistingDirectory(self, "Escolher pasta", self.config.value("ultima_pasta", ""))
        if pasta:
            self.config.setValue("ultima_pasta", pasta)
            self.adicionar([pasta])

    def _remover(self, item):
        self.lista.takeItem(self.lista.row(item))
        self._atualizar_lista()

    def _limpar(self):
        self.lista.clear()
        self._atualizar_lista()

    def _atualizar_lista(self):
        n = self.lista.count()
        self.lbl_qtd.setText(str(n))
        self.lbl_vazio.setVisible(n == 0)
        self.btn_extrair.setEnabled(n > 0)

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()
            tema.definir_prop(self.zona, "ativo", "true")

    def dragLeaveEvent(self, ev):
        tema.definir_prop(self.zona, "ativo", "false")

    def dropEvent(self, ev):
        tema.definir_prop(self.zona, "ativo", "false")
        self.adicionar([u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()])

    # ---------------- opções ----------------

    def formato(self):
        b = self.grupo_formato.checkedButton()
        return b.property("formato") if b else "png"

    def _atualizar_formato(self):
        self.explicacao.setText(FORMATOS[self.formato()][1])

    def _carregar_opcoes(self):
        c = self.config
        indice = self.tamanho.findText(c.value("tamanho_texto", "10 x 15 cm"))
        self.tamanho.setCurrentIndex(max(0, indice))
        self.larg.setValue(float(c.value("larg", 10)))
        self.alt.setValue(float(c.value("alt", 15)))
        self.margem.setValue(float(c.value("margem", 0.3)))
        formato = c.value("formato", "png")
        botoes = self.grupo_formato.buttons()
        (next((b for b in botoes if b.property("formato") == formato), botoes[0])).setChecked(True)
        self._atualizar_formato()
        self.outro.setVisible(self.tamanho.currentData() == "outro")

    def _salvar_opcoes(self):
        for chave, valor in (("tamanho_texto", self.tamanho.currentText()), ("larg", self.larg.value()),
                             ("alt", self.alt.value()), ("margem", self.margem.value()),
                             ("formato", self.formato())):
            self.config.setValue(chave, valor)

    def _extrair(self):
        tamanho = self.tamanho.currentData()
        if tamanho == "outro":
            tamanho = (self.larg.value(), self.alt.value())
        arquivos = self.arquivos()
        base = arquivos[0].parent  # local sugerido para o álbum; pode ser alterado ao salvar
        # O album.json identifica cada arquivo pelo nome: dois arquivos com o mesmo nome se confundiriam.
        nomes = {}
        for a in arquivos:
            nomes.setdefault(a.name.lower(), []).append(str(a))
        repetidos = [c for c in nomes.values() if len(c) > 1]
        if repetidos:
            QMessageBox.warning(self, "Nomes repetidos",
                                "Um álbum não pode ter dois arquivos com o mesmo nome. Renomeie um deles:\n\n"
                                + "\n\n".join("\n".join(c) for c in repetidos))
            return
        # O nome do álbum é escolhido ao salvar; aqui só seguem o local e as opções.
        cfg = Config(None, None, tamanho, self.margem.value(), self.formato())
        self._salvar_opcoes()
        self.extrair.emit(arquivos, cfg, base)


class JanelaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Recorte de Fotos")
        self.resize(1440, 880)
        self.setMinimumSize(1100, 680)
        self.inicial = TelaInicial()
        self.revisao = TelaRevisao()
        self.telas = QStackedWidget()
        self.telas.addWidget(self.inicial)
        self.telas.addWidget(self.revisao)
        self.setCentralWidget(self.telas)
        self.inicial.extrair.connect(self._iniciar)
        self.revisao.voltar.connect(self._voltar)

    def _iniciar(self, arquivos, cfg, base):
        self.telas.setCurrentWidget(self.revisao)
        self.revisao.iniciar(arquivos, cfg, base)

    def _pode_descartar(self):
        if self.revisao.extraindo() or self.revisao.alterado:
            return QMessageBox.question(
                self, "Descartar?",
                "Há fotos extraídas ou alterações que ainda não foram salvas. Descartar mesmo assim?",
            ) == QMessageBox.Yes
        return True

    def _voltar(self):
        if self._pode_descartar():
            self.revisao.parar()
            self.revisao.alterado = False
            self.telas.setCurrentWidget(self.inicial)

    def closeEvent(self, ev):
        if self.telas.currentWidget() is self.revisao and not self._pode_descartar():
            ev.ignore()
            return
        self.revisao.parar()
        ev.accept()


def _mostrar_erro(tipo, valor, tb):
    texto = "".join(traceback.format_exception(tipo, valor, tb))
    sys.__stderr__ and sys.__stderr__.write(texto)
    QMessageBox.critical(None, "Erro inesperado", f"Ocorreu um erro inesperado:\n\n{valor}\n\n{texto[-2000:]}")


def executar():
    app = QApplication(sys.argv)
    app.setApplicationName("Recorte de Fotos")
    tema.aplicar(app)
    sys.excepthook = _mostrar_erro
    janela = JanelaPrincipal()
    janela.show()
    return app.exec()
