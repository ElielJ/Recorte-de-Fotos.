"""Tela de revisão: lista de fotos extraídas, visualizador e painel de diagnóstico."""
import os
import traceback

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFrame, QGraphicsOpacityEffect,
                               QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView,
                               QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu,
                               QMessageBox, QProgressBar, QProgressDialog, QVBoxLayout, QWidget)

from backend import processamento
from . import tema
from .editor import EditorRecorte
from .imagens import pixmap_da_previa
from .metadados import DialogoMetadados

FILTROS = ["Todas as fotos", "Para revisar", "Prontas (OK / editadas)", "Excluídas"]
DIAGNOSTICO = {
    "revisar": ("alerta", "Atenção ao recorte"),
    "ok": ("ok", "Recorte automático OK"),
    "editado": ("lapis", "Recorte ajustado manualmente"),
    "excluida": ("lixeira", "Foto excluída do lote"),
}


def estado_visual(foto):
    return "excluida" if foto.excluida else foto.estado


class ExtracaoThread(QThread):
    foto_pronta = Signal(object)
    progresso = Signal(int, str)  # milésimos, texto
    erro = Signal(str, str)

    def __init__(self, arquivos, cfg):
        super().__init__()
        self.arquivos, self.cfg, self.cancelar = arquivos, cfg, False

    def run(self):
        n = len(self.arquivos)
        for k, arquivo in enumerate(self.arquivos):
            try:
                for foto, i, total in processamento.extrair(arquivo, self.cfg, lambda: self.cancelar):
                    self.foto_pronta.emit(foto)
                    self.progresso.emit(int(1000 * (k + i / total) / n),
                                        f"{arquivo.name}: página {i} de {total} (arquivo {k + 1} de {n})")
            except Exception as e:
                traceback.print_exc()
                self.erro.emit(arquivo.name, str(e))
            if self.cancelar:
                return


class SalvarThread(QThread):
    progresso = Signal(int, int)
    erro = Signal(str)

    def __init__(self, fotos, cfg, metadados):
        super().__init__()
        self.fotos, self.cfg, self.metadados, self.cancelar, self.pastas = fotos, cfg, metadados, False, []

    def run(self):
        try:
            self.pastas = processamento.salvar(self.fotos, self.cfg, self.progresso.emit, lambda: self.cancelar,
                                               self.metadados)
        except Exception as e:
            traceback.print_exc()
            self.erro.emit(str(e))


class CartaoFoto(QFrame):
    """Cartão da lista lateral: miniatura, nome, medidas e estado."""

    LARG, ALT = 60, 78

    def __init__(self):
        super().__init__()
        self.setObjectName("cartao")
        self.mini = QLabel(alignment=Qt.AlignCenter)
        self.mini.setObjectName("miniatura")
        self.mini.setFixedSize(self.LARG, self.ALT)
        self.numero = QLabel(self.mini)
        self.numero.setObjectName("numeroPagina")
        self.nome = QLabel()
        self.nome.setObjectName("nomeCartao")
        self.pagina = QLabel()
        self.pagina.setObjectName("suave")
        self.medidas = QLabel()
        self.medidas.setObjectName("suave")
        self.pilula = tema.Pilula()

        linha = QHBoxLayout()
        linha.addWidget(self.nome, 1)
        linha.addWidget(self.pagina)
        linha_estado = QHBoxLayout()
        linha_estado.addWidget(self.pilula)
        linha_estado.addStretch()
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addLayout(linha)
        col.addWidget(self.medidas)
        col.addLayout(linha_estado)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 9, 11, 9)
        lay.setSpacing(12)
        lay.addWidget(self.mini)
        lay.addLayout(col, 1)
        # Os cliques passam direto para a lista, que cuida da seleção.
        for w in [self] + self.findChildren(QWidget):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)

    def atualizar(self, foto, total_na_pagina=1):
        pix = pixmap_da_previa(foto).scaled(self.LARG - 4, self.ALT - 4, Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation)
        self.mini.setPixmap(pix)
        varias = total_na_pagina > 1
        self.numero.setText(f"#{foto.pagina + 1}" + (f".{foto.indice + 1}" if varias else ""))
        self.numero.adjustSize()
        self.numero.move(self.LARG - self.numero.width() - 4, self.ALT - self.numero.height() - 4)
        self.nome.setText(self.nome.fontMetrics().elidedText(foto.arquivo.stem, Qt.ElideRight, 150))
        self.nome.setToolTip(foto.arquivo.name)
        self.pagina.setText(f"pág. {foto.pagina + 1}" + (f" · {foto.indice + 1}/{total_na_pagina}" if varias else ""))
        tam = foto.tamanho_cm()
        partes = [f"{tam[0]:.1f} x {tam[1]:.1f} cm" if tam else f"{round(foto.recorte.w)} x "
                                                                  f"{round(foto.recorte.h)} px"]
        if foto.dpi:
            partes.append(f"{foto.dpi:g} dpi")
        self.medidas.setText(" • ".join(partes))
        self.pilula.definir(estado_visual(foto))
        if foto.excluida:
            efeito = QGraphicsOpacityEffect(self)
            efeito.setOpacity(0.45)
            self.setGraphicsEffect(efeito)
        else:
            self.setGraphicsEffect(None)

    def selecionar(self, sim):
        tema.definir_prop(self, "selecionado", "true" if sim else "false")


class VisualizadorPrevia(QGraphicsView):
    """Mostra a foto recortada com zoom pela roda do mouse e arraste para navegar."""

    zoom_mudou = Signal(int)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(tema.xadrez())
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.imagem = QGraphicsPixmapItem()
        self.imagem.setTransformationMode(Qt.SmoothTransformation)
        self.borda = QGraphicsRectItem()
        caneta = QPen(QColor(59, 130, 246, 210), 2)
        caneta.setCosmetic(True)
        self.borda.setPen(caneta)
        self.scene().addItem(self.imagem)
        self.scene().addItem(self.borda)
        self._ajustado = True
        self._escala_ajuste = 1.0

    def definir(self, pixmap):
        self.imagem.setPixmap(pixmap or QPixmap())
        self.imagem.setVisible(pixmap is not None and not pixmap.isNull())
        self.borda.setVisible(self.imagem.isVisible())
        r = self.imagem.boundingRect()
        self.borda.setRect(r)
        self.scene().setSceneRect(r.adjusted(-r.width(), -r.height(), r.width(), r.height()))
        self.ajustar()

    def ajustar(self):
        r = self.imagem.boundingRect()
        if r.isEmpty():
            return
        self.resetTransform()
        m = 60  # espaço livre para a barra flutuante e a dica
        f = min((self.viewport().width() - m) / r.width(), (self.viewport().height() - 2 * m) / r.height())
        f = max(f, 0.01)
        self.scale(f, f)
        self.centerOn(r.center())
        self._escala_ajuste = f
        self._ajustado = True
        self.zoom_mudou.emit(100)

    def zoom(self, fator):
        escala = self.transform().m11() * fator
        if 0.3 * self._escala_ajuste <= escala <= 12 * self._escala_ajuste:
            self.scale(fator, fator)
            self._ajustado = False
            self.zoom_mudou.emit(round(100 * escala / self._escala_ajuste))

    def wheelEvent(self, ev):
        self.zoom(1.2 ** (ev.angleDelta().y() / 120))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._ajustado:
            self.ajustar()


def sobrepor(base, widget, alinhamento, margens=(0, 0, 0, 0)):
    """Coloca 'widget' flutuando sobre 'base' (mesma célula de uma grade)."""
    grade = base.layout()
    suporte = QWidget()
    suporte.setAttribute(Qt.WA_TranslucentBackground)
    lay = QHBoxLayout(suporte)
    lay.setContentsMargins(*margens)
    lay.addWidget(widget)
    grade.addWidget(suporte, 0, 0, alinhamento)
    return suporte


class TelaRevisao(QWidget):
    voltar = Signal()

    def __init__(self):
        super().__init__()
        self.fotos, self.cfg, self.thread = [], None, None
        self.metadados = {}  # {arquivo: Metadados} de cada lote
        self.alterado = False
        self._erros = []
        self._ordem_arquivo = {}

        conteudo = QWidget()
        conteudo.setObjectName("fundo")
        lc = QVBoxLayout(conteudo)
        lc.setContentsMargins(0, 0, 0, 0)
        lc.setSpacing(0)
        lc.addWidget(self._criar_cabecalho())
        lc.addWidget(self._criar_progresso())
        corpo = QHBoxLayout()
        corpo.setSpacing(0)
        corpo.addWidget(self._criar_lista())
        corpo.addWidget(self._criar_centro(), 1)
        corpo.addWidget(self._criar_lateral())
        lc.addLayout(corpo, 1)

        raiz = QGridLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(conteudo, 0, 0)
        self.toast = tema.Toast()
        # Canto inferior direito da área central, sem cobrir os botões do painel lateral.
        sobrepor(self, self.toast, Qt.AlignBottom | Qt.AlignRight, (0, 0, 360, 52))
        self._criar_atalhos()
        self._mostrar_atual()

    # ---------------- construção ----------------

    def _criar_cabecalho(self):
        cab = QFrame()
        cab.setObjectName("cabecalho")
        cab.setFixedHeight(64)
        lay = QHBoxLayout(cab)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(tema.logo(36))
        titulos = QVBoxLayout()
        titulos.setSpacing(0)
        t = QLabel("Recorte de Fotos")
        t.setObjectName("titulo")
        s = QLabel("Revisão das fotos extraídas")
        s.setObjectName("subtitulo")
        titulos.addStretch()
        titulos.addWidget(t)
        titulos.addWidget(s)
        titulos.addStretch()
        self.btn_voltar = tema.botao("Nova extração", "voltar", cor_icone="#60a5fa")
        self.btn_voltar.clicked.connect(self.voltar.emit)

        caixa = QFrame()
        caixa.setObjectName("contadores")
        lcx = QHBoxLayout(caixa)
        lcx.setContentsMargins(4, 4, 4, 4)
        lcx.setSpacing(4)
        self.cont_total = tema.Pilula("neutro", "")
        self.cont_revisar = tema.Pilula("revisar", "")
        self.cont_prontas = tema.Pilula("ok", "")
        self.cont_excluidas = tema.Pilula("excluida", "")
        for p in (self.cont_total, self.cont_revisar, self.cont_prontas, self.cont_excluidas):
            lcx.addWidget(p)

        icone_filtro = QLabel()
        icone_filtro.setPixmap(tema.icone("filtro", tema.SUAVE, 13).pixmap(13, 13))
        rotulo = QLabel("Filtro:")
        rotulo.setObjectName("subtitulo")
        self.filtro = QComboBox()
        self.filtro.addItems(FILTROS)
        self.filtro.currentIndexChanged.connect(self._aplicar_filtro)
        self.btn_salvar = tema.botao("Salvar todas", "download", "primario", "white")
        self.btn_salvar.clicked.connect(self.salvar)
        self.btn_metadados = tema.botao("Metadados", "calendario", cor_icone="#60a5fa",
                                        dica="Data estimada, local e descrição do lote (Ctrl+M)")
        self.btn_metadados.clicked.connect(self.editar_metadados)

        lay.addWidget(logo)
        lay.addLayout(titulos)
        lay.addSpacing(6)
        lay.addWidget(tema.separador_vertical())
        lay.addWidget(self.btn_voltar)
        lay.addStretch()
        lay.addWidget(caixa, 0, Qt.AlignVCenter)
        lay.addStretch()
        lay.addWidget(self.btn_metadados)
        lay.addSpacing(6)
        lay.addWidget(icone_filtro)
        lay.addWidget(rotulo)
        lay.addWidget(self.filtro)
        lay.addSpacing(6)
        lay.addWidget(self.btn_salvar)
        return cab

    def _criar_progresso(self):
        self.faixa_progresso = QFrame()
        self.faixa_progresso.setObjectName("faixa")
        lay = QHBoxLayout(self.faixa_progresso)
        lay.setContentsMargins(18, 8, 18, 8)
        self.lbl_progresso = QLabel("Iniciando…")
        self.lbl_progresso.setObjectName("subtitulo")
        self.barra = QProgressBar(maximum=1000, textVisible=False)
        self.btn_cancelar = tema.botao("Cancelar", "fechar")
        self.btn_cancelar.clicked.connect(self._cancelar_extracao)
        lay.addWidget(self.lbl_progresso)
        lay.addWidget(self.barra, 1)
        lay.addWidget(self.btn_cancelar)
        self.faixa_progresso.hide()
        return self.faixa_progresso

    def _criar_lista(self):
        painel = QFrame()
        painel.setObjectName("listaLateral")
        painel.setFixedWidth(340)
        lay = QVBoxLayout(painel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        topo = QFrame()
        topo.setObjectName("faixa")
        lt = QHBoxLayout(topo)
        lt.setContentsMargins(14, 11, 14, 11)
        ic = QLabel()
        ic.setPixmap(tema.icone("grade", "#60a5fa", 15).pixmap(15, 15))
        sec = QLabel("FOTOS EXTRAÍDAS")
        sec.setObjectName("secao")
        self.lbl_contagem = QLabel("0 de 0")
        self.lbl_contagem.setObjectName("contagem")
        lt.addWidget(ic)
        lt.addWidget(sec)
        lt.addStretch()
        lt.addWidget(self.lbl_contagem)

        area = QWidget()
        QGridLayout(area).setContentsMargins(0, 0, 0, 0)
        self.lista = QListWidget()
        self.lista.setSpacing(5)
        self.lista.setSelectionMode(QListWidget.ExtendedSelection)
        self.lista.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.lista.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu)
        self.lista.itemDoubleClicked.connect(lambda _: self.editar())
        self.lista.currentItemChanged.connect(lambda *_: self._mostrar_atual())
        self.lista.itemSelectionChanged.connect(self._marcar_selecao)
        area.layout().addWidget(self.lista, 0, 0)
        self.lbl_vazio = QLabel("Nenhuma foto neste filtro.", alignment=Qt.AlignCenter)
        self.lbl_vazio.setObjectName("subtitulo")
        area.layout().addWidget(self.lbl_vazio, 0, 0)

        rodape = QFrame()
        rodape.setObjectName("rodape")
        lr = QHBoxLayout(rodape)
        lr.setContentsMargins(14, 8, 10, 8)
        info = QLabel()
        info.setPixmap(tema.icone("info", "#60a5fa", 13).pixmap(13, 13))
        dica = QLabel("Navegar: <b>↑ ↓</b>")
        dica.setObjectName("subtitulo")
        self.btn_aprovar_restantes = tema.botao("Aprovar restantes", tipo="link")
        self.btn_aprovar_restantes.setToolTip("Marca como OK todas as fotos que ainda estão para revisar")
        self.btn_aprovar_restantes.clicked.connect(self._aprovar_restantes)
        lr.addWidget(info)
        lr.addWidget(dica)
        lr.addStretch()
        lr.addWidget(self.btn_aprovar_restantes)

        lay.addWidget(topo)
        lay.addWidget(area, 1)
        lay.addWidget(rodape)
        return painel

    def _criar_centro(self):
        centro = QWidget()
        lay = QVBoxLayout(centro)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        faixa = QFrame()
        faixa.setObjectName("faixa")
        faixa.setFixedHeight(48)
        lf = QHBoxLayout(faixa)
        lf.setContentsMargins(20, 0, 16, 0)
        self.titulo_foto = QLabel()
        self.titulo_foto.setTextFormat(Qt.RichText)
        self.pilula_foto = tema.Pilula()
        self.btn_anterior = tema.botao("", "anterior", dica="Foto anterior (↑)")
        self.btn_anterior.clicked.connect(lambda: self.navegar(-1))
        self.lbl_posicao = QLabel()
        self.lbl_posicao.setObjectName("subtitulo")
        self.btn_proxima = tema.botao("", "proximo", dica="Próxima foto (↓)")
        self.btn_proxima.clicked.connect(lambda: self.navegar(1))
        lf.addWidget(self.titulo_foto)
        lf.addSpacing(6)
        lf.addWidget(self.pilula_foto, 0, Qt.AlignVCenter)
        lf.addStretch()
        lf.addWidget(self.btn_anterior)
        lf.addWidget(self.lbl_posicao)
        lf.addWidget(self.btn_proxima)

        area = QWidget()
        QGridLayout(area).setContentsMargins(0, 0, 0, 0)
        self.visualizador = VisualizadorPrevia()
        area.layout().addWidget(self.visualizador, 0, 0)

        barra = QFrame()
        barra.setObjectName("barraFlutuante")
        lb = QHBoxLayout(barra)
        lb.setContentsMargins(6, 4, 6, 4)
        lb.setSpacing(4)
        b_esq = tema.botao("-90°", "girar_esq", "icone", "#60a5fa", "Girar 90° anti-horário (Ctrl+←)")
        b_esq.clicked.connect(lambda: self._girar(-1))
        b_dir = tema.botao("+90°", "girar_dir", "icone", "#60a5fa", "Girar 90° horário (Ctrl+→)")
        b_dir.clicked.connect(lambda: self._girar(1))
        b_menos = tema.botao("", "zoom_menos", "icone", dica="Diminuir zoom")
        b_menos.clicked.connect(lambda: self.visualizador.zoom(1 / 1.25))
        self.lbl_zoom = QLabel("100%", alignment=Qt.AlignCenter)
        self.lbl_zoom.setObjectName("zoomTexto")
        self.lbl_zoom.setFixedWidth(42)
        b_mais = tema.botao("", "zoom_mais", "icone", dica="Aumentar zoom")
        b_mais.clicked.connect(lambda: self.visualizador.zoom(1.25))
        b_ajustar = tema.botao("", "ajustar", "icone", dica="Ajustar à tela")
        b_ajustar.clicked.connect(self.visualizador.ajustar)
        self.visualizador.zoom_mudou.connect(lambda p: self.lbl_zoom.setText(f"{p}%"))
        for w in (b_esq, tema.separador_vertical(), b_dir, tema.separador_vertical(), b_menos, self.lbl_zoom,
                  b_mais, tema.separador_vertical(), b_ajustar):
            lb.addWidget(w)
        sobrepor(area, barra, Qt.AlignTop | Qt.AlignHCenter, (0, 14, 0, 0))
        dica = QLabel("Roda do mouse: zoom • Arraste para inspecionar as bordas • Duplo clique na lista: editar")
        dica.setObjectName("dica")
        sobrepor(area, dica, Qt.AlignBottom | Qt.AlignHCenter, (0, 0, 0, 12))

        lay.addWidget(faixa)
        lay.addWidget(area, 1)
        return centro

    def _criar_lateral(self):
        lateral = QFrame()
        lateral.setObjectName("lateral")
        lateral.setFixedWidth(340)
        lay = QVBoxLayout(lateral)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(16)

        self.diag = QFrame()
        self.diag.setObjectName("diagnostico")
        ld = QHBoxLayout(self.diag)
        ld.setContentsMargins(14, 14, 14, 14)
        ld.setSpacing(12)
        self.diag_icone = QLabel(alignment=Qt.AlignTop)
        self.diag_titulo = QLabel()
        self.diag_titulo.setObjectName("tituloDiag")
        self.diag_texto = QLabel(wordWrap=True)
        self.diag_dica = QLabel(wordWrap=True)
        self.diag_dica.setObjectName("dicaDiag")
        col = QVBoxLayout()
        col.setSpacing(5)
        col.addWidget(self.diag_titulo)
        col.addWidget(self.diag_texto)
        col.addWidget(self.diag_dica)
        ld.addWidget(self.diag_icone)
        ld.addLayout(col, 1)

        cab_spec = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(tema.icone("regua", "#60a5fa", 14).pixmap(14, 14))
        sec = QLabel("ESPECIFICAÇÕES TÉCNICAS")
        sec.setObjectName("secao")
        cab_spec.addWidget(ic)
        cab_spec.addWidget(sec)
        cab_spec.addStretch()
        grade = QGridLayout()
        grade.setSpacing(8)
        self.specs = {}
        for i, (chave, nome) in enumerate((("cm", "Dimensões reais"), ("esperado", "Tamanho esperado"),
                                           ("dpi", "Resolução"), ("px", "Pixels"))):
            cartao = QFrame()
            cartao.setObjectName("spec")
            lc = QVBoxLayout(cartao)
            lc.setContentsMargins(10, 8, 10, 8)
            lc.setSpacing(2)
            rot = QLabel(nome)
            rot.setObjectName("subtitulo")
            valor = QLabel("–")
            valor.setObjectName("specValor")
            lc.addWidget(rot)
            lc.addWidget(valor)
            grade.addWidget(cartao, i // 2, i % 2)
            self.specs[chave] = valor

        cab_meta = QHBoxLayout()
        ic_m = QLabel()
        ic_m.setPixmap(tema.icone("calendario", "#60a5fa", 14).pixmap(14, 14))
        sec_m = QLabel("METADADOS DO LOTE")
        sec_m.setObjectName("secao")
        editar_meta = tema.botao("Editar…", tipo="link")
        editar_meta.setToolTip("Data estimada, local e descrição (Ctrl+M)")
        editar_meta.clicked.connect(self.editar_metadados)
        cab_meta.addWidget(ic_m)
        cab_meta.addWidget(sec_m)
        cab_meta.addStretch()
        cab_meta.addWidget(editar_meta)
        grade_meta = QGridLayout()
        grade_meta.setSpacing(8)
        for col, (chave, nome) in enumerate((("data", "Data estimada"), ("local", "Local"))):
            cartao = QFrame()
            cartao.setObjectName("spec")
            lc = QVBoxLayout(cartao)
            lc.setContentsMargins(10, 8, 10, 8)
            lc.setSpacing(2)
            rot = QLabel(nome)
            rot.setObjectName("subtitulo")
            valor = QLabel("–")
            valor.setObjectName("specValor")
            valor.setWordWrap(True)
            lc.addWidget(rot)
            lc.addWidget(valor)
            grade_meta.addWidget(cartao, 0, col)
            self.specs[chave] = valor

        self.btn_editar = tema.BotaoAtalho("Editar recorte manual…", "crop", "Enter")
        self.btn_editar.clicked.connect(self.editar)
        giros = QHBoxLayout()
        self.btn_girar_esq = tema.botao("Girar à esquerda", "girar_esq", cor_icone=tema.SUAVE,
                                        dica="Girar 90° anti-horário (Ctrl+←)")
        self.btn_girar_esq.clicked.connect(lambda: self._girar(-1))
        self.btn_girar_dir = tema.botao("Girar à direita", "girar_dir", cor_icone=tema.SUAVE,
                                        dica="Girar 90° horário (Ctrl+→)")
        self.btn_girar_dir.clicked.connect(lambda: self._girar(1))
        giros.addWidget(self.btn_girar_esq)
        giros.addWidget(self.btn_girar_dir)
        self.btn_ok = tema.BotaoAtalho("Aprovar e marcar como OK", "ok", "Ctrl+K", "sucesso", "#d1fae5")
        self.btn_ok.clicked.connect(self._alternar_ok)
        self.btn_excluir = tema.botao("Excluir foto do lote (Del)", "lixeira", "perigo", "#fb7185")
        self.btn_excluir.clicked.connect(self._alternar_exclusao)

        linha = QFrame()
        linha.setFixedHeight(1)
        linha.setStyleSheet(f"background: {tema.BORDA};")
        lay.addWidget(self.diag)
        lay.addLayout(cab_spec)
        lay.addLayout(grade)
        lay.addLayout(cab_meta)
        lay.addLayout(grade_meta)
        lay.addStretch()
        lay.addWidget(linha)
        lay.addWidget(self.btn_editar)
        lay.addLayout(giros)
        lay.addWidget(self.btn_ok)
        lay.addWidget(self.btn_excluir)
        self._botoes_acao = [self.btn_editar, self.btn_girar_esq, self.btn_girar_dir, self.btn_ok,
                             self.btn_excluir]
        return lateral

    def _criar_atalhos(self):
        self.acoes = {}
        for chave, texto, atalhos, funcao in (
                ("editar", "Editar recorte…", ["Return", "Enter"], self.editar),
                ("esq", "Girar à esquerda", ["Ctrl+Left"], lambda: self._girar(-1)),
                ("dir", "Girar à direita", ["Ctrl+Right"], lambda: self._girar(1)),
                ("ok", "Aprovar / reabrir para revisão", ["Ctrl+K"], self._alternar_ok),
                ("excluir", "Excluir / restaurar", ["Delete"], self._alternar_exclusao),
                ("ant", "Foto anterior", ["Up"], lambda: self.navegar(-1)),
                ("prox", "Próxima foto", ["Down"], lambda: self.navegar(1)),
                ("meta", "Metadados do lote", ["Ctrl+M"], self.editar_metadados),
                ("salvar", "Salvar todas", ["Ctrl+S"], self.salvar)):
            acao = QAction(texto, self)
            acao.setShortcuts([QKeySequence(a) for a in atalhos])
            acao.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            acao.triggered.connect(funcao)
            self.addAction(acao)
            self.acoes[chave] = acao

    # ---------------- extração ----------------

    def iniciar(self, arquivos, cfg):
        self.fotos, self.cfg = [], cfg
        self.metadados = {a: processamento.carregar_metadados(a, cfg) for a in arquivos}
        self.lista.clear()
        self.filtro.setCurrentIndex(0)
        self.alterado = False
        self._ordem_arquivo = {a: i for i, a in enumerate(arquivos)}
        self._erros = []
        self.barra.setValue(0)
        self.lbl_progresso.setText("Iniciando…")
        self.faixa_progresso.show()
        self.thread = ExtracaoThread(arquivos, cfg)
        self.thread.foto_pronta.connect(self._adicionar_foto)
        self.thread.progresso.connect(lambda v, t: (self.barra.setValue(v), self.lbl_progresso.setText(t)))
        self.thread.erro.connect(lambda arq, msg: self._erros.append(f"{arq}: {msg}"))
        self.thread.finished.connect(self._extracao_terminou)
        self.thread.start()
        self._atualizar()

    def extraindo(self):
        return self.thread is not None and self.thread.isRunning()

    def _cancelar_extracao(self):
        if self.thread:
            self.thread.cancelar = True
            self.lbl_progresso.setText("Cancelando…")

    def parar(self):
        if self.extraindo():
            self.thread.cancelar = True
            self.thread.wait()

    def _adicionar_foto(self, foto):
        self.fotos.append(foto)
        item = self._inserir_item(foto)
        for outro in self._itens_da_pagina(foto):  # numeração "1/2", "2/2" nos cartões da página
            self._renderizar(outro)
        if self.lista.currentItem() is None:
            self.lista.setCurrentItem(item)
        self._atualizar()

    def _inserir_item(self, foto, grupo=None):
        item = QListWidgetItem()
        item.setData(Qt.UserRole, foto)
        # Ordem fixa: as que precisam de revisão primeiro, depois por arquivo, página e posição na página.
        grupo = (foto.estado != "revisar") if grupo is None else grupo
        chave = (grupo, self._ordem_arquivo[foto.arquivo], foto.pagina, foto.indice)
        item.setData(Qt.UserRole + 1, chave)
        posicao = next((i for i in range(self.lista.count())
                        if self.lista.item(i).data(Qt.UserRole + 1) > chave), self.lista.count())
        item.setSizeHint(QSize(0, 98))
        self.lista.insertItem(posicao, item)
        self.lista.setItemWidget(item, CartaoFoto())
        self._renderizar(item)
        return item

    def _da_pagina(self, foto):
        return [f for f in self.fotos if f.arquivo == foto.arquivo and f.pagina == foto.pagina]

    def _itens_da_pagina(self, foto):
        return [self.lista.item(i) for i in range(self.lista.count())
                if (lambda f: f.arquivo == foto.arquivo and f.pagina == foto.pagina)(
                    self.lista.item(i).data(Qt.UserRole))]

    def _extracao_terminou(self):
        self.faixa_progresso.hide()
        self.alterado = bool(self.fotos)
        self._atualizar()
        self._mostrar_atual()
        if self._erros:
            QMessageBox.warning(self, "Erros na extração",
                                "Não foi possível ler alguns arquivos:\n\n" + "\n".join(self._erros))
        elif not self.fotos:
            QMessageBox.information(self, "Extração", "Nenhuma página foi encontrada nos arquivos.")
        else:
            rev = sum(f.estado == "revisar" for f in self.fotos)
            self.toast.mostrar(f"Extração concluída: {len(self.fotos)} foto(s)"
                               + (f", {rev} para revisar." if rev else ", todas OK."))

    # ---------------- exibição ----------------

    def _renderizar(self, item):
        foto = item.data(Qt.UserRole)
        cartao = self.lista.itemWidget(item)
        cartao.atualizar(foto, len(self._da_pagina(foto)))
        cartao.selecionar(item.isSelected())
        self._aplicar_filtro_item(item)

    def _marcar_selecao(self):
        for i in range(self.lista.count()):
            item = self.lista.item(i)
            cartao = self.lista.itemWidget(item)
            if cartao is not None:  # o cartão é criado logo depois de o item entrar na lista
                cartao.selecionar(item.isSelected())

    def _aplicar_filtro(self):
        for i in range(self.lista.count()):
            self._aplicar_filtro_item(self.lista.item(i))
        atual = self.lista.currentItem()
        if atual is None or atual.isHidden():
            visiveis = self._visiveis()
            self.lista.setCurrentItem(visiveis[0] if visiveis else None)
        self._atualizar()

    def _aplicar_filtro_item(self, item):
        foto = item.data(Qt.UserRole)
        filtro = self.filtro.currentIndex()
        visivel = (filtro == 0
                   or (filtro == 1 and foto.estado == "revisar" and not foto.excluida)
                   or (filtro == 2 and foto.estado in ("ok", "editado") and not foto.excluida)
                   or (filtro == 3 and foto.excluida))
        item.setHidden(not visivel)

    def _visiveis(self):
        return [self.lista.item(i) for i in range(self.lista.count()) if not self.lista.item(i).isHidden()]

    def _mostrar_atual(self):
        item = self.lista.currentItem()
        tem_foto = item is not None and not item.isHidden()
        for b in self._botoes_acao:
            b.setEnabled(tem_foto)
        self.btn_editar.setEnabled(tem_foto and not self.extraindo())
        if not tem_foto:
            self.visualizador.definir(None)
            self.titulo_foto.setText("<span style='color:#94a3b8'>Nenhuma foto selecionada</span>")
            self.pilula_foto.hide()
            self.lbl_posicao.setText("")
            self.diag.hide()
            for v in self.specs.values():
                v.setText("–")
            return
        foto = item.data(Qt.UserRole)
        estado = estado_visual(foto)
        self.visualizador.definir(pixmap_da_previa(foto))
        n_pagina = len(self._da_pagina(foto))
        posicao = f"&nbsp;&nbsp;•&nbsp;&nbsp;foto {foto.indice + 1} de {n_pagina}" if n_pagina > 1 else ""
        self.titulo_foto.setText(f"<b style='color:white'>{foto.arquivo.name}</b>"
                                 f"<span style='color:#94a3b8'>&nbsp;&nbsp;•&nbsp;&nbsp;página {foto.pagina + 1}"
                                 f"{posicao}</span>")
        self.pilula_foto.definir(estado, {"revisar": "Requer atenção", "ok": "Pronta para salvar",
                                          "editado": "Editada • pronta para salvar",
                                          "excluida": "Marcada para exclusão"}[estado])
        self.pilula_foto.show()
        visiveis = self._visiveis()
        self.lbl_posicao.setText(f"{visiveis.index(item) + 1} de {len(visiveis)}")

        # Diagnóstico
        nome_icone, titulo = DIAGNOSTICO[estado]
        aprovada_manualmente = estado == "ok" and foto.motivo
        if aprovada_manualmente:
            titulo = "Aprovada por você"
        texto = {
            "revisar": foto.motivo or "Confira o recorte antes de salvar.",
            "ok": f"Aviso original: {foto.motivo}" if aprovada_manualmente else
                  "A foto foi detectada automaticamente" + (" com o tamanho esperado." if self.cfg and
                                                            self.cfg.tamanho_cm else "."),
            "editado": "O recorte que você ajustou será usado ao salvar.",
            "excluida": "Esta foto não será salva. Use “Restaurar foto” para incluí-la novamente.",
        }[estado]
        self.diag_icone.setPixmap(tema.icone(nome_icone, tema.CORES_ESTADO[estado], 22).pixmap(22, 22))
        self.diag_titulo.setText(titulo)
        self.diag_texto.setText(texto)
        self.diag_dica.setText("💡 Abra o editor (Enter) para ajustar ou aprove com Ctrl+K."
                               if estado == "revisar" else "")
        self.diag_dica.setVisible(estado == "revisar")
        tema.definir_prop(self.diag, "estado", estado)
        tema.definir_prop(self.diag_titulo, "estado", estado)
        self.diag.show()

        # Especificações
        tam = foto.tamanho_cm()
        self.specs["cm"].setText(f"{tam[0]:.1f} x {tam[1]:.1f} cm" if tam else "–")
        esperado = self.cfg.tamanho_cm if self.cfg else None
        self.specs["esperado"].setText(f"{esperado[0]:g} x {esperado[1]:g} cm" if esperado else "Não validado")
        self.specs["dpi"].setText(f"{foto.dpi:g} dpi" if foto.dpi else "Desconhecida")
        w, h = round(foto.recorte.w), round(foto.recorte.h)
        self.specs["px"].setText(f"{h} x {w} px" if foto.rot90 % 2 else f"{w} x {h} px")
        meta = self.metadados.get(foto.arquivo)
        self.specs["data"].setText(meta.texto_data() if meta and meta.ano else "Não informada")
        local = meta.local if meta else ""
        coords = ""
        if meta and meta.tem_gps():
            coords = f"{meta.latitude:.4f}, {meta.longitude:.4f}"
            local = f"{local} 📍" if local else f"📍 {meta.latitude:.2f}, {meta.longitude:.2f}"
        self.specs["local"].setText(local or "Não informado")
        self.specs["local"].setToolTip(f"Coordenadas: {coords}" if coords else "Sem coordenadas GPS")

        # Botões que mudam conforme o estado
        if foto.estado == "revisar":
            self.btn_ok.definir("Aprovar e marcar como OK", "ok", "#d1fae5", "sucesso")
        else:
            self.btn_ok.definir("Reabrir para revisão", "restaurar", tema.SUAVE)
        if foto.excluida:
            self.btn_excluir.setText("Restaurar foto")
            self.btn_excluir.setIcon(tema.icone("restaurar", "#60a5fa"))
            tema.definir_prop(self.btn_excluir, "tipo", "")
        else:
            self.btn_excluir.setText("Excluir foto do lote (Del)")
            self.btn_excluir.setIcon(tema.icone("lixeira", "#fb7185"))
            tema.definir_prop(self.btn_excluir, "tipo", "perigo")

    def _atualizar(self):
        n = len(self.fotos)
        rev = sum(f.estado == "revisar" and not f.excluida for f in self.fotos)
        prontas = sum(f.estado in ("ok", "editado") and not f.excluida for f in self.fotos)
        exc = sum(f.excluida for f in self.fotos)
        self.cont_total.setText(f"Total: {n}")
        self.cont_revisar.setText(f"Para revisar: {rev}")
        self.cont_prontas.setText(f"Prontas: {prontas}")
        self.cont_excluidas.setText(f"Excluídas: {exc}")
        visiveis = len(self._visiveis())
        self.lbl_contagem.setText(f"{visiveis} de {n}")
        self.lbl_vazio.setVisible(n > 0 and visiveis == 0)
        self.btn_salvar.setEnabled(n > exc and not self.extraindo())
        self.btn_aprovar_restantes.setEnabled(rev > 0)
        self.acoes["editar"].setEnabled(not self.extraindo())

    # ---------------- ações ----------------

    def navegar(self, passo):
        visiveis = self._visiveis()
        if not visiveis:
            return
        atual = self.lista.currentItem()
        i = visiveis.index(atual) + passo if atual in visiveis else 0
        if 0 <= i < len(visiveis):
            self._selecionar_unico(visiveis[i])

    def _selecionar_unico(self, item):
        self.lista.setCurrentItem(item)
        self.lista.clearSelection()
        item.setSelected(True)
        self.lista.scrollToItem(item)

    def _selecionados(self):
        itens = [i for i in self.lista.selectedItems() if not i.isHidden()]
        atual = self.lista.currentItem()
        return itens or ([atual] if atual is not None and not atual.isHidden() else [])

    def _alterar(self, funcao, mensagem=None):
        itens = self._selecionados()
        for item in itens:
            funcao(item.data(Qt.UserRole))
            self._renderizar(item)
        if itens:
            self.alterado = True
            self._mostrar_atual()
            self._atualizar()
            if mensagem:
                self.toast.mostrar(mensagem(len(itens)) if callable(mensagem) else mensagem)
        return itens

    def _girar(self, sentido):
        self._alterar(lambda f: setattr(f, "rot90", (f.rot90 + sentido) % 4),
                      lambda n: f"{n} foto(s) girada(s) 90° {'à direita' if sentido > 0 else 'à esquerda'}.")

    def _alternar_ok(self):
        itens = self._selecionados()
        if not itens:
            return
        aprovar = any(i.data(Qt.UserRole).estado == "revisar" for i in itens)

        def mudar(f):
            if aprovar and f.estado == "revisar":
                f.estado = "ok"
            elif not aprovar:
                f.estado = "revisar"
        self._alterar(mudar, "Foto(s) aprovada(s)." if aprovar else "Foto(s) reaberta(s) para revisão.")
        if aprovar and len(itens) == 1:
            self._ir_para_proxima_pendente(itens[0])

    def _ir_para_proxima_pendente(self, depois_de):
        visiveis = self._visiveis()
        if not visiveis:
            return
        inicio = visiveis.index(depois_de) + 1 if depois_de in visiveis else 0
        for item in visiveis[inicio:] + visiveis[:inicio]:
            f = item.data(Qt.UserRole)
            if f.estado == "revisar" and not f.excluida:
                self._selecionar_unico(item)
                return
        if depois_de.isHidden():  # saiu do filtro "Para revisar"
            self._selecionar_unico(visiveis[0])

    def _alternar_exclusao(self):
        excluir = not all(i.data(Qt.UserRole).excluida for i in self._selecionados())
        self._alterar(lambda f: setattr(f, "excluida", excluir),
                      "Foto(s) excluída(s) do lote." if excluir else "Foto(s) restaurada(s).")

    def _aprovar_restantes(self):
        n = 0
        for i in range(self.lista.count()):
            item = self.lista.item(i)
            f = item.data(Qt.UserRole)
            if f.estado == "revisar" and not f.excluida:
                f.estado = "ok"
                n += 1
                self._renderizar(item)
        if n:
            self.alterado = True
            self._aplicar_filtro()
            self._mostrar_atual()
            self.toast.mostrar(f"{n} foto(s) aprovada(s).")

    def _menu(self, pos):
        if self.lista.itemAt(pos):
            menu = QMenu(self)
            for chave in ("editar", "esq", "dir", "ok", "excluir"):
                menu.addAction(self.acoes[chave])
            menu.exec(self.lista.mapToGlobal(pos))

    def editar(self):
        item = self.lista.currentItem()
        if item is None or item.isHidden():
            return
        if self.extraindo():
            self.toast.mostrar("Aguarde o fim da extração para editar recortes.")
            return
        foto = item.data(Qt.UserRole)
        # O editor mostra todos os recortes da página (as excluídas ficam de fora, salvo a selecionada).
        editaveis = [f for f in self._da_pagina(foto) if not f.excluida or f is foto]
        editaveis.sort(key=lambda f: f.indice)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            pagina = processamento.carregar_pagina(foto)
            editor = EditorRecorte(editaveis, foto, pagina.imagem, self.cfg.tamanho_cm, self)
        finally:
            QApplication.restoreOverrideCursor()
        editor.setWindowState(Qt.WindowMaximized)
        if editor.exec() != QDialog.Accepted:
            return
        resultado, indice_ativo = editor.resultado()
        self._aplicar_edicao(foto, editaveis, resultado, indice_ativo, pagina.imagem)

    def _aplicar_edicao(self, modelo, editaveis, resultado, indice_ativo, imagem):
        """Aplica na lista o que foi feito no editor: recortes alterados, novos e removidos."""
        mantidas = {id(f) for f, _ in resultado if f is not None}
        removidas = [f for f in editaveis if id(f) not in mantidas]
        alteradas = []
        for f, r in resultado:
            if f is None:
                nova = processamento.nova_foto(modelo, r)
                self.fotos.append(nova)
                alteradas.append(nova)
            elif r != f.recorte:
                f.recorte = r
                f.estado, f.motivo = "editado", ""
                alteradas.append(f)
        if not alteradas and not removidas:
            return
        ativa = resultado[indice_ativo][0] or alteradas[-1]
        ids_removidas = {id(f) for f in removidas}
        self.fotos = [f for f in self.fotos if id(f) not in ids_removidas]

        # Renumera a página e recria os cartões dela na posição certa da lista.
        itens = self._itens_da_pagina(modelo)
        grupo = min(i.data(Qt.UserRole + 1)[0] for i in itens)
        for i in itens:
            self.lista.takeItem(self.lista.row(i))
        da_pagina = self._da_pagina(modelo)
        processamento.renumerar(da_pagina)
        for f in alteradas:
            processamento.atualizar_previa(f, imagem)
        novos = {id(f): self._inserir_item(f, grupo) for f in sorted(da_pagina, key=lambda f: f.indice)}
        self._selecionar_unico(novos[id(ativa)])
        self.alterado = True
        self._mostrar_atual()
        self._atualizar()
        n = len([f for f in da_pagina if not f.excluida])
        self.toast.mostrar("Recorte atualizado." if n == 1 and not removidas and len(resultado) == 1
                           else f"Página atualizada: {n} foto(s).")

    def editar_metadados(self):
        if not self.metadados:
            return
        item = self.lista.currentItem()
        atual = item.data(Qt.UserRole).arquivo if item is not None else next(iter(self.metadados))
        dialogo = DialogoMetadados(self.metadados, atual, self)
        if dialogo.exec() != QDialog.Accepted or dialogo.resultado == self.metadados:
            return
        self.metadados = dialogo.resultado
        self.alterado = True
        self._mostrar_atual()
        self.toast.mostrar("Metadados atualizados. Serão gravados ao salvar as fotos.")

    def salvar(self):
        if not self.btn_salvar.isEnabled():
            return
        existentes = processamento.arquivos_existentes(self.fotos, self.cfg)
        if existentes and QMessageBox.question(
                self, "Substituir fotos?",
                f"{len(existentes)} foto(s) já existem nas pastas de saída e serão substituídas.\n\nContinuar?",
        ) != QMessageBox.Yes:
            return
        total = sum(not f.excluida for f in self.fotos)
        formato = self.cfg.formato.upper()
        dialogo = QProgressDialog(f"Salvando fotos em {formato}…", "Cancelar", 0, total, self)
        dialogo.setWindowTitle("Salvando")
        dialogo.setWindowModality(Qt.WindowModal)
        dialogo.setMinimumDuration(0)
        dialogo.setValue(0)
        erros = []
        t = SalvarThread(self.fotos, self.cfg, self.metadados)
        t.progresso.connect(lambda feitas, _: dialogo.setValue(feitas))
        t.erro.connect(erros.append)
        dialogo.canceled.connect(lambda: setattr(t, "cancelar", True))
        t.finished.connect(dialogo.reset)
        t.start()
        dialogo.exec()
        t.wait()
        if erros:
            QMessageBox.critical(self, "Erro ao salvar", "\n".join(erros))
            return
        if t.cancelar:
            QMessageBox.information(self, "Cancelado", "O salvamento foi interrompido; algumas fotos podem "
                                                       "não ter sido gravadas.")
            return
        self.alterado = False
        caixa = QMessageBox(QMessageBox.Information, "Fotos salvas",
                            f"{total} foto(s) salvas em {formato} em:\n\n" + "\n".join(map(str, t.pastas)), parent=self)
        abrir = caixa.addButton("Abrir pasta", QMessageBox.AcceptRole)
        caixa.addButton("Fechar", QMessageBox.RejectRole)
        caixa.exec()
        if caixa.clickedButton() is abrir:
            for pasta in t.pastas[:5]:
                os.startfile(pasta)
