"""Tema escuro, ícones (traços no estilo Lucide) e componentes visuais reutilizáveis."""
import tempfile
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

# Cores
FUNDO = "#0b0f17"
SUPERFICIE = "#111827"
CARTAO = "#161f30"
BORDA = "#1f293d"
BORDA_FORTE = "#334155"
TEXTO = "#e2e8f0"
SUAVE = "#94a3b8"
AZUL = "#3b82f6"
CORES_ESTADO = {"revisar": "#f59e0b", "ok": "#10b981", "editado": "#60a5fa", "excluida": "#f43f5e"}

# Ícones de traço em viewBox 24x24 (desenho inspirado no conjunto Lucide, licença ISC).
ICONES = {
    "crop": '<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M18 22V8a2 2 0 0 0-2-2H2"/>',
    "pasta": '<path d="M12 10v6"/><path d="M9 13h6"/><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 '
             '0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "arquivo": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 '
               '2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/>'
              '<line x1="12" x2="12" y1="3" y2="15"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/>'
                '<line x1="12" x2="12" y1="15" y2="3"/>',
    "camadas": '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58'
               '-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 '
               '12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    "alerta": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
              '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    "ok": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "lapis": '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>',
    "lixeira": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4'
               'c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/>',
    "restaurar": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    "girar_esq": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    "girar_dir": '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>',
    "zoom_mais": '<circle cx="11" cy="11" r="8"/><line x1="21" x2="16.65" y1="21" y2="16.65"/>'
                 '<line x1="11" x2="11" y1="8" y2="14"/><line x1="8" x2="14" y1="11" y2="11"/>',
    "zoom_menos": '<circle cx="11" cy="11" r="8"/><line x1="21" x2="16.65" y1="21" y2="16.65"/>'
                  '<line x1="8" x2="14" y1="11" y2="11"/>',
    "ajustar": '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 '
               '2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>',
    "anterior": '<path d="m15 18-6-6 6-6"/>',
    "proximo": '<path d="m9 18 6-6-6-6"/>',
    "voltar": '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    "filtro": '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    "grade": '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/>'
             '<rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "fechar": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "lampada": '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 '
               '1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/>',
    "regua": '<path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4'
             'l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z"/><path d="m14.5 12.5 2-2"/><path d="m11.5 9.5 2-2"/>'
             '<path d="m8.5 6.5 2-2"/><path d="m17.5 15.5 2-2"/>',
    "imagem": '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/>'
              '<path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
    "calendario": '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/>'
                  '<path d="M3 10h18"/>',
    "local": '<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 '
             '0 0 1 16 0"/><circle cx="12" cy="10" r="3"/>',
    "texto": '<path d="M17 6.1H3"/><path d="M21 12.1H3"/><path d="M15.1 18H3"/>',
}


def icone(nome, cor="#cbd5e1", tamanho=16):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{cor}" '
           f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICONES[nome]}</svg>')
    escala = 3  # desenha em alta resolução para ficar nítido em telas com zoom
    pix = QPixmap(tamanho * escala, tamanho * escala)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    pix.setDevicePixelRatio(escala)
    return QIcon(pix)


def logo(tamanho=36):
    """Quadrado arredondado em degradê com o ícone de recorte."""
    pix = QPixmap(tamanho * 3, tamanho * 3)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, pix.width(), pix.height())
    g.setColorAt(0, QColor("#3b82f6"))
    g.setColorAt(1, QColor("#4f46e5"))
    p.setBrush(QBrush(g))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(0, 0, pix.width(), pix.height()), pix.width() * 0.28, pix.width() * 0.28)
    m = pix.width() * 0.25
    icone("crop", "white", tamanho).paint(p, int(m), int(m), int(pix.width() - 2 * m), int(pix.width() - 2 * m))
    p.end()
    pix.setDevicePixelRatio(3)
    return pix


def xadrez():
    """Padrão quadriculado discreto para o fundo do visualizador."""
    pix = QPixmap(20, 20)
    pix.fill(QColor(FUNDO))
    p = QPainter(pix)
    p.fillRect(0, 0, 10, 10, QColor("#141c2b"))
    p.fillRect(10, 10, 10, 10, QColor("#141c2b"))
    p.end()
    return QBrush(pix)


def definir_prop(widget, nome, valor):
    """Altera uma propriedade usada pelo estilo e reaplica o estilo."""
    widget.setProperty(nome, valor)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def botao(texto="", nome_icone=None, tipo=None, cor_icone="#cbd5e1", dica=None, tamanho_icone=16):
    b = QPushButton(texto)
    if nome_icone:
        b.setIcon(icone(nome_icone, cor_icone, tamanho_icone))
    if tipo:
        b.setProperty("tipo", tipo)
    if dica:
        b.setToolTip(dica)
    b.setCursor(Qt.PointingHandCursor)
    return b


class BotaoAtalho(QPushButton):
    """Botão largo com ícone e texto à esquerda e a tecla de atalho à direita."""

    def __init__(self, texto, nome_icone, atalho, tipo=None, cor_icone="#60a5fa"):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(38)
        if tipo:
            self.setProperty("tipo", tipo)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 10, 0)
        self._icone = QLabel()
        self._texto = QLabel()
        self._texto.setObjectName("textoBotao")
        self._atalho = QLabel(atalho)
        self._atalho.setObjectName("kbd")
        for w in (self._icone, self._texto, self._atalho):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self._icone)
        lay.addWidget(self._texto, 1)
        lay.addWidget(self._atalho)
        self.definir(texto, nome_icone, cor_icone, tipo)

    def definir(self, texto, nome_icone, cor_icone="#60a5fa", tipo=None):
        self._texto.setText(texto)
        self._icone.setPixmap(icone(nome_icone, cor_icone, 16).pixmap(16, 16))
        definir_prop(self, "tipo", tipo or "")
        definir_prop(self._texto, "tipo", tipo or "")
        definir_prop(self._atalho, "tipo", tipo or "")


class Pilula(QLabel):
    """Etiqueta arredondada com o estado da foto (revisar, ok, editado, excluida)."""

    TEXTOS = {"revisar": "Revisar", "ok": "OK", "editado": "Editada", "excluida": "Excluída"}

    def __init__(self, estado="ok", texto=None):
        super().__init__()
        self.setObjectName("pilula")
        self.definir(estado, texto)

    def definir(self, estado, texto=None):
        self.setText(texto if texto is not None else self.TEXTOS[estado])
        definir_prop(self, "estado", estado)


class Toast(QLabel):
    """Aviso rápido que some sozinho."""

    def __init__(self):
        super().__init__()
        self.setObjectName("toast")
        self.hide()
        self._timer = QTimer(self, singleShot=True, interval=2600, timeout=self.hide)

    def mostrar(self, texto):
        self.setText(texto)
        self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start()


def separador_vertical():
    s = QFrame()
    s.setObjectName("separador")
    s.setFixedSize(1, 22)
    return s


QSS = f"""
* {{ font-family: "Segoe UI"; font-size: 9pt; color: {TEXTO}; }}
QMainWindow, QDialog, #fundo {{ background: {FUNDO}; }}
#painel {{ background: {SUPERFICIE}; }}
#cabecalho {{ background: {SUPERFICIE}; border-bottom: 1px solid {BORDA}; }}
#faixa {{ background: rgba(17,24,39,0.6); border-bottom: 1px solid {BORDA}; }}
#rodape {{ background: {SUPERFICIE}; border-top: 1px solid {BORDA}; }}
#lateral {{ background: {SUPERFICIE}; border-left: 1px solid {BORDA}; }}
#listaLateral {{ background: {SUPERFICIE}; border-right: 1px solid {BORDA}; }}
#titulo {{ font-size: 10.5pt; font-weight: 600; color: white; }}
#tituloGrande {{ font-size: 16pt; font-weight: 600; color: white; }}
#subtitulo, #suave {{ color: {SUAVE}; font-size: 8pt; }}
#secao {{ color: #cbd5e1; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }}
#separador {{ background: {BORDA_FORTE}; }}
#contagem {{ background: #1f293d; color: {SUAVE}; border: 1px solid {BORDA_FORTE}; border-radius: 9px;
             padding: 1px 8px; font-size: 8pt; }}

QPushButton {{ background: #1f293d; border: 1px solid {BORDA_FORTE}; border-radius: 8px; padding: 6px 12px;
               color: #cbd5e1; }}
QPushButton:hover {{ background: {BORDA_FORTE}; border-color: #64748b; }}
QPushButton:pressed {{ background: #1e293b; }}
QPushButton:disabled {{ color: #475569; background: {CARTAO}; border-color: {BORDA}; }}
QPushButton[tipo="primario"] {{ border: none; color: white; font-weight: 600; padding: 8px 18px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #4f46e5); }}
QPushButton[tipo="primario"]:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #6366f1); }}
QPushButton[tipo="primario"]:disabled {{ background: #1e293b; color: #475569; }}
QPushButton[tipo="sucesso"] {{ background: #059669; border: none; }}
QPushButton[tipo="sucesso"]:hover {{ background: #10b981; }}
QPushButton[tipo="perigo"] {{ background: rgba(244,63,94,0.10); border: 1px solid rgba(244,63,94,0.30);
                              color: #fb7185; }}
QPushButton[tipo="perigo"]:hover {{ background: rgba(244,63,94,0.20); }}
QPushButton[tipo="icone"] {{ background: transparent; border: none; padding: 5px; border-radius: 6px; }}
QPushButton[tipo="icone"]:hover {{ background: {BORDA_FORTE}; }}
QPushButton[tipo="link"] {{ background: transparent; border: none; color: #60a5fa; padding: 2px; }}
QPushButton[tipo="link"]:hover {{ color: #93c5fd; text-decoration: underline; }}
QPushButton[tipo="segmento"] {{ padding: 8px 16px; }}
QPushButton[tipo="segmento"]:checked {{ background: rgba(37,99,235,0.25); border: 1px solid {AZUL};
                                        color: white; font-weight: 600; }}
#explicacao {{ background: {CARTAO}; border: 1px solid {BORDA}; border-radius: 8px; padding: 10px 12px;
               color: #cbd5e1; }}
#textoBotao {{ font-weight: 500; color: white; }}
#textoBotao[tipo="sucesso"] {{ font-weight: 600; }}
#kbd {{ background: {SUPERFICIE}; border: 1px solid {BORDA_FORTE}; border-radius: 4px; padding: 1px 6px;
        color: {SUAVE}; font-family: Consolas; font-size: 8pt; }}
#kbd[tipo="sucesso"] {{ background: #047857; border-color: #10b981; color: white; }}

QComboBox, QAbstractSpinBox, QLineEdit {{ background: {SUPERFICIE}; border: 1px solid {BORDA_FORTE};
    border-radius: 6px; padding: 4px 8px; min-height: 18px; }}
QComboBox:hover, QAbstractSpinBox:hover, QLineEdit:hover {{ border-color: #64748b; }}
QComboBox:focus, QAbstractSpinBox:focus, QLineEdit:focus {{ border-color: {AZUL}; }}
QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled {{ color: #475569; background: {CARTAO}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDA_FORTE}; border-radius: 4px;
                        background: {SUPERFICIE}; }}
QCheckBox::indicator:hover {{ border-color: {AZUL}; }}
QCheckBox::indicator:checked {{ background: {AZUL}; border-color: {AZUL}; image: url(MARCA_OK); }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url(SETA_BAIXO); width: 12px; height: 12px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ border: none; width: 18px; background: transparent; }}
QAbstractSpinBox::up-arrow {{ image: url(SETA_CIMA); width: 10px; height: 10px; }}
QAbstractSpinBox::down-arrow {{ image: url(SETA_BAIXO); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{ background: {SUPERFICIE}; border: 1px solid {BORDA_FORTE};
    selection-background-color: #1e3a8a; outline: 0; }}

#pilula {{ border-radius: 9px; padding: 2px 9px; font-size: 8pt; font-weight: 600; }}
#pilula[estado="revisar"] {{ background: rgba(245,158,11,0.15); color: #fcd34d; border: 1px solid rgba(245,158,11,0.35); }}
#pilula[estado="ok"] {{ background: rgba(16,185,129,0.15); color: #6ee7b7; border: 1px solid rgba(16,185,129,0.35); }}
#pilula[estado="editado"] {{ background: rgba(59,130,246,0.15); color: #93c5fd; border: 1px solid rgba(59,130,246,0.35); }}
#pilula[estado="excluida"] {{ background: rgba(244,63,94,0.15); color: #fda4af; border: 1px solid rgba(244,63,94,0.35); }}
#pilula[estado="neutro"] {{ background: transparent; color: #cbd5e1; border: 1px solid transparent; }}
#contadores {{ background: rgba(11,15,23,0.7); border: 1px solid {BORDA}; border-radius: 10px; }}

#cartao {{ background: {CARTAO}; border: 1px solid {BORDA}; border-radius: 10px; }}
#cartao:hover {{ border-color: {BORDA_FORTE}; }}
#cartao[selecionado="true"] {{ background: rgba(30,58,138,0.30); border: 1px solid {AZUL}; }}
#miniatura {{ background: {FUNDO}; border: 1px solid {BORDA_FORTE}; border-radius: 6px; }}
#numeroPagina {{ background: rgba(11,15,23,0.85); color: #cbd5e1; font-family: Consolas; font-size: 7pt;
                 border-radius: 3px; padding: 0 3px; }}
#nomeCartao {{ font-weight: 600; color: #e2e8f0; }}

#diagnostico {{ border-radius: 12px; }}
#diagnostico[estado="revisar"] {{ background: rgba(120,53,15,0.25); border: 1px solid rgba(245,158,11,0.35); }}
#diagnostico[estado="ok"] {{ background: rgba(6,78,59,0.25); border: 1px solid rgba(16,185,129,0.35); }}
#diagnostico[estado="editado"] {{ background: rgba(30,58,138,0.25); border: 1px solid rgba(59,130,246,0.35); }}
#diagnostico[estado="excluida"] {{ background: rgba(136,19,55,0.25); border: 1px solid rgba(244,63,94,0.35); }}
#tituloDiag {{ font-weight: 600; }}
#tituloDiag[estado="revisar"] {{ color: #fcd34d; }}
#tituloDiag[estado="ok"] {{ color: #6ee7b7; }}
#tituloDiag[estado="editado"] {{ color: #93c5fd; }}
#tituloDiag[estado="excluida"] {{ color: #fda4af; }}
#dicaDiag {{ color: #fbbf24; font-size: 8pt; font-weight: 500; }}
#spec {{ background: {CARTAO}; border: 1px solid {BORDA}; border-radius: 8px; }}
#specValor {{ font-weight: 600; color: #e2e8f0; }}

#barraFlutuante {{ background: rgba(17,24,39,0.92); border: 1px solid {BORDA_FORTE}; border-radius: 12px; }}
#zoomTexto {{ color: {SUAVE}; font-family: Consolas; font-size: 8pt; }}
#dica {{ background: rgba(17,24,39,0.88); border: 1px solid {BORDA}; border-radius: 10px; color: {SUAVE};
         padding: 3px 12px; font-size: 8pt; }}
#toast {{ background: #1f293d; border: 1px solid {BORDA_FORTE}; border-radius: 10px; padding: 10px 16px;
          color: white; }}
#zonaSoltar {{ border: 2px dashed {BORDA_FORTE}; border-radius: 14px; background: {SUPERFICIE}; }}
#zonaSoltar[ativo="true"] {{ border-color: {AZUL}; background: rgba(30,58,138,0.25); }}
#caixa {{ background: {SUPERFICIE}; border: 1px solid {BORDA}; border-radius: 12px; }}

QListWidget {{ background: transparent; border: none; outline: 0; }}
QListWidget::item, QListWidget::item:selected, QListWidget::item:hover {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(100,116,139,0.45); border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(100,116,139,0.75); }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: rgba(100,116,139,0.45); border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width: 0; height: 0;
    background: none; }}
QProgressBar {{ background: {BORDA}; border: none; border-radius: 3px; max-height: 6px; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #6366f1);
                       border-radius: 3px; }}
QToolTip {{ background: #1f293d; color: {TEXTO}; border: 1px solid {BORDA_FORTE}; padding: 4px; }}
QMessageBox QLabel {{ color: {TEXTO}; }}
QSplitter::handle {{ background: {BORDA}; }}
QGraphicsView {{ border: none; }}
"""


def aplicar(app):
    app.setStyle("Fusion")
    pal = QPalette()
    for papel, cor in ((QPalette.Window, FUNDO), (QPalette.WindowText, TEXTO), (QPalette.Base, SUPERFICIE),
                       (QPalette.AlternateBase, CARTAO), (QPalette.Text, TEXTO), (QPalette.Button, "#1f293d"),
                       (QPalette.ButtonText, TEXTO), (QPalette.Highlight, "#1e3a8a"),
                       (QPalette.HighlightedText, "white"), (QPalette.ToolTipBase, "#1f293d"),
                       (QPalette.ToolTipText, TEXTO), (QPalette.PlaceholderText, "#64748b")):
        pal.setColor(papel, QColor(cor))
    app.setPalette(pal)
    app.setFont(QFont("Segoe UI", 9))
    # O QSS só aceita imagens por arquivo: grava as setas numa pasta temporária.
    pasta = Path(tempfile.gettempdir()) / "recorte_fotos_ui"
    pasta.mkdir(exist_ok=True)
    qss = QSS
    for nome, desenho, cor in (("SETA_BAIXO", "m6 9 6 6 6-6", SUAVE), ("SETA_CIMA", "m18 15-6-6-6 6", SUAVE),
                               ("MARCA_OK", "M20 6 9 17l-5-5", "white")):
        arquivo = pasta / f"{nome.lower()}.svg"
        arquivo.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
                           f'stroke="{cor}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
                           f'<path d="{desenho}"/></svg>')
        qss = qss.replace(nome, arquivo.as_posix())
    app.setStyleSheet(qss)
    app.setWindowIcon(QIcon(logo(64)))
