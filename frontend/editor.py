"""Editor de recortes da página: todos os recortes sobre a página original, com cantos, bordas e rotação.

Permite também adicionar uma foto que não foi detectada, dividir um recorte que juntou duas fotos e
remover um recorte falso.
"""
from math import atan2, cos, degrees, radians, sin

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QDialog, QDoubleSpinBox, QFormLayout, QFrame, QGraphicsItem, QGraphicsObject,
                               QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
                               QHBoxLayout, QLabel, QMessageBox, QVBoxLayout)

from backend.deteccao import ordem_leitura
from backend.recorte import Recorte, dividir
from . import tema
from .imagens import pixmap_de_array

COR = QColor("#3b82f6")
COR_INATIVA = QColor(226, 232, 240, 200)
ALCA = 10  # tamanho das alças em pixels de tela
DIST_GIRO = 40  # distância da alça de giro acima do recorte, em pixels de tela
TAM_MIN = 20.0


class AreaRecorte(QGraphicsObject):
    """Um recorte na página. Só o recorte ativo mostra alças; os outros podem ser clicados e movidos."""

    alterado = Signal()
    clicado = Signal(object)

    def __init__(self, r, foto=None, auto=None):
        super().__init__()
        self.foto = foto  # Foto existente, ou None para um recorte novo
        self.auto = auto or Recorte(r.cx, r.cy, r.w, r.h, r.angulo)
        self.numero = 1
        self.ativa = False
        self._w, self._h = r.w, r.h
        self.setPos(r.cx, r.cy)
        self.setRotation(r.angulo)
        self.setAcceptHoverEvents(True)
        self._arrasto = None

    def recorte(self):
        return Recorte(self.pos().x(), self.pos().y(), self._w, self._h, self.rotation())

    def definir(self, r):
        self.prepareGeometryChange()
        self._w, self._h = r.w, r.h
        self.setPos(r.cx, r.cy)
        self.setRotation(r.angulo)
        self.alterado.emit()

    def ativar(self, sim):
        self.ativa = sim
        self.setZValue(3 if sim else 2)
        self.unsetCursor()
        self.update()

    def poligono(self):
        return self.mapToScene(QRectF(-self._w / 2, -self._h / 2, self._w, self._h))

    def escala_mudou(self):
        self.prepareGeometryChange()

    def _px(self):
        """Tamanho de um pixel de tela em unidades da página."""
        views = self.scene().views() if self.scene() else []
        return 1 / views[0].transform().m11() if views else 1.0

    def boundingRect(self):
        s = self._px()
        m = ALCA * s
        return QRectF(-self._w / 2, -self._h / 2, self._w, self._h).adjusted(-m, -m - DIST_GIRO * s, m, m)

    def paint(self, p, *_):
        s = self._px()
        w2, h2 = self._w / 2, self._h / 2
        pen = QPen(COR if self.ativa else COR_INATIVA, 2 if self.ativa else 1.5)
        pen.setCosmetic(True)
        if not self.ativa:
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(-w2, -h2, self._w, self._h))

        # Número da foto no canto superior esquerdo (tamanho fixo na tela).
        p.save()
        p.translate(-w2, -h2)
        p.scale(s, s)
        p.setPen(Qt.NoPen)
        p.setBrush(COR if self.ativa else QColor(30, 41, 59, 230))
        p.drawEllipse(QRectF(8, 8, 24, 24))
        p.setPen(Qt.white)
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        p.drawText(QRectF(8, 8, 24, 24), Qt.AlignCenter, str(self.numero))
        p.restore()

        if not self.ativa:
            return
        p.setPen(pen)
        p.drawLine(QPointF(0, -h2), QPointF(0, -h2 - DIST_GIRO * s))
        p.setBrush(QBrush(Qt.white))
        a = ALCA * s
        for x in (-w2, 0, w2):
            for y in (-h2, 0, h2):
                if x or y:
                    p.drawRect(QRectF(x - a / 2, y - a / 2, a, a))
        p.setBrush(QBrush(COR))
        p.drawEllipse(QPointF(0, -h2 - DIST_GIRO * s), a * 0.7, a * 0.7)

    def _alvo(self, pt):
        w2, h2 = self._w / 2, self._h / 2
        x, y = pt.x(), pt.y()
        dentro = abs(x) < w2 and abs(y) < h2
        if not self.ativa:
            return ("mover",) if dentro else None
        s = self._px()
        tol = ALCA * s
        if (x ** 2 + (y + h2 + DIST_GIRO * s) ** 2) ** 0.5 <= tol * 1.2:
            return ("girar",)
        dentro_x, dentro_y = -w2 - tol <= x <= w2 + tol, -h2 - tol <= y <= h2 + tol
        sx = -1 if abs(x + w2) <= tol else 1 if abs(x - w2) <= tol else 0
        sy = -1 if abs(y + h2) <= tol else 1 if abs(y - h2) <= tol else 0
        sx, sy = (sx if dentro_y else 0), (sy if dentro_x else 0)
        if sx or sy:
            return ("redimensionar", sx, sy)
        return ("mover",) if dentro else None

    def hoverMoveEvent(self, ev):
        alvo = self._alvo(ev.pos())
        if alvo is None:
            self.unsetCursor()
        elif alvo[0] == "girar":
            self.setCursor(Qt.PointingHandCursor)
        elif alvo[0] == "mover":
            self.setCursor(Qt.SizeAllCursor if self.ativa else Qt.PointingHandCursor)
        else:
            # Escolhe o cursor de seta conforme a direção real (considerando o giro).
            d = (degrees(atan2(alvo[2], alvo[1])) + self.rotation()) % 180
            cursores = [Qt.SizeHorCursor, Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor]
            self.setCursor(cursores[round(d / 45) % 4])

    def mousePressEvent(self, ev):
        alvo = self._alvo(ev.pos())
        if alvo is None or ev.button() != Qt.LeftButton:
            ev.ignore()
            return
        if not self.ativa:
            self.clicado.emit(self)
        oposto = None
        if alvo[0] == "redimensionar":
            oposto = self.mapToScene(QPointF(-alvo[1] * self._w / 2, -alvo[2] * self._h / 2))
        self._arrasto = (alvo, ev.scenePos(), self.recorte(), oposto)
        ev.accept()

    def mouseMoveEvent(self, ev):
        if not self._arrasto:
            return
        alvo, inicio, r, oposto = self._arrasto
        p = ev.scenePos()
        if alvo[0] == "mover":
            r = Recorte(r.cx + p.x() - inicio.x(), r.cy + p.y() - inicio.y(), r.w, r.h, r.angulo)
        elif alvo[0] == "girar":
            ang = degrees(atan2(p.y() - r.cy, p.x() - r.cx)) + 90
            r = Recorte(r.cx, r.cy, r.w, r.h, round((ang + 180) % 360 - 180, 2))
        else:
            _, sx, sy = alvo
            c, s = cos(radians(r.angulo)), sin(radians(r.angulo))
            dx, dy = p.x() - oposto.x(), p.y() - oposto.y()
            lx, ly = dx * c + dy * s, -dx * s + dy * c  # vetor no sistema do recorte
            w = max(TAM_MIN, sx * lx) if sx else r.w
            h = max(TAM_MIN, sy * ly) if sy else r.h
            mx, my = sx * w / 2, sy * h / 2  # do lado fixo até o centro
            r = Recorte(oposto.x() + mx * c - my * s, oposto.y() + mx * s + my * c, w, h, r.angulo)
        self.definir(r)

    def mouseReleaseEvent(self, ev):
        self._arrasto = None


class Visualizador(QGraphicsView):
    def __init__(self, pixmap):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(tema.xadrez())

        self.imagem = QGraphicsPixmapItem(pixmap)
        self.scene().addItem(self.imagem)
        self.mascara = QGraphicsPathItem()
        self.mascara.setBrush(QColor(0, 0, 0, 120))
        self.mascara.setPen(Qt.NoPen)
        self.mascara.setAcceptedMouseButtons(Qt.NoButton)
        self.mascara.setZValue(1)
        self.scene().addItem(self.mascara)
        self.areas = []

    def adicionar(self, area):
        self.areas.append(area)
        self.scene().addItem(area)
        area.alterado.connect(self.atualizar_mascara)
        self.atualizar_mascara()

    def remover(self, area):
        self.areas.remove(area)
        self.scene().removeItem(area)
        self.atualizar_mascara()

    def atualizar_mascara(self):
        # Escurece tudo o que está fora dos recortes.
        fora = QPainterPath()
        fora.addRect(self.imagem.boundingRect())
        dentro = QPainterPath()
        dentro.setFillRule(Qt.WindingFill)
        for a in self.areas:
            dentro.addPolygon(a.poligono())
            dentro.closeSubpath()
        self.mascara.setPath(fora.subtracted(dentro))
        # Números em ordem de leitura (como serão salvas as fotos).
        for k, i in enumerate(ordem_leitura([a.recorte() for a in self.areas])):
            if self.areas[i].numero != k + 1:
                self.areas[i].numero = k + 1
                self.areas[i].update()

    def ajustar(self):
        self.fitInView(self.imagem.boundingRect().adjusted(-40, -80, 40, 40), Qt.KeepAspectRatio)
        self._escala_mudou()

    def tamanho_real(self, area):
        self.resetTransform()
        self.centerOn(area.pos())
        self._escala_mudou()

    def centro_visivel(self):
        return self.mapToScene(self.viewport().rect().center())

    def wheelEvent(self, ev):
        f = 1.25 ** (ev.angleDelta().y() / 120)
        escala = self.transform().m11() * f
        if 0.02 <= escala <= 16:
            self.scale(f, f)
            self._escala_mudou()

    def _escala_mudou(self):
        # Ampliado: mostra os pixels nítidos e sem cache; reduzido: suavizado e em cache.
        ampliado = self.transform().m11() >= 1
        self.imagem.setTransformationMode(Qt.FastTransformation if ampliado else Qt.SmoothTransformation)
        self.imagem.setCacheMode(QGraphicsItem.NoCache if ampliado else QGraphicsItem.DeviceCoordinateCache)
        for a in self.areas:
            a.escala_mudou()


class EditorRecorte(QDialog):
    """Edita todos os recortes de uma página.

    fotos: fotos da página que podem ser editadas; ativa: a foto selecionada ao abrir;
    tamanho_cm: tamanho esperado (usado como tamanho inicial ao adicionar uma foto).
    """

    def __init__(self, fotos, ativa, imagem, tamanho_cm=None, parent=None):
        super().__init__(parent)
        modelo = fotos[0]
        self.setWindowTitle(f"Editar recortes: {modelo.arquivo.name}, página {modelo.pagina + 1}")
        self._dpi = modelo.dpi
        self._tamanho_cm = tamanho_cm
        self.view = Visualizador(pixmap_de_array(imagem))
        self.area = None  # recorte ativo
        for f in fotos:
            a = AreaRecorte(f.recorte, f, f.auto)
            self._ligar(a)
            if f is ativa:
                self.area = a
        self.area = self.area or self.view.areas[0]

        lateral = QFrame()
        lateral.setObjectName("lateral")
        lateral.setFixedWidth(300)
        lv = QVBoxLayout(lateral)
        lv.setContentsMargins(18, 18, 18, 18)
        lv.setSpacing(10)
        titulo = QLabel("Editar recortes")
        titulo.setObjectName("titulo")
        sub = QLabel(f"{modelo.arquivo.name} • página {modelo.pagina + 1}")
        sub.setObjectName("subtitulo")
        lv.addWidget(titulo)
        lv.addWidget(sub)
        lv.addSpacing(6)

        self.lbl_ativa = QLabel()
        self.lbl_ativa.setObjectName("secao")
        lv.addWidget(self.lbl_ativa)
        self.angulo = QDoubleSpinBox(minimum=-180, maximum=180, decimals=2, singleStep=0.05, suffix="°")
        self.angulo.setKeyboardTracking(False)
        self.lbl_tamanho = QLabel()
        self.lbl_tamanho.setObjectName("specValor")
        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Ângulo:", self.angulo)
        form.addRow("Tamanho:", self.lbl_tamanho)
        lv.addLayout(form)
        for texto, nome_icone, acao in (("Restaurar automático", "restaurar", lambda: self.area.definir(self.area.auto)),
                                        ("Zoom 100% (pixels reais)", "zoom_mais",
                                         lambda: self.view.tamanho_real(self.area)),
                                        ("Ajustar à janela", "ajustar", self.view.ajustar)):
            b = tema.botao(texto, nome_icone, cor_icone="#60a5fa")
            b.clicked.connect(acao)
            lv.addWidget(b)

        lv.addSpacing(8)
        self.lbl_qtd = QLabel()
        self.lbl_qtd.setObjectName("secao")
        lv.addWidget(self.lbl_qtd)
        b_add = tema.botao("Adicionar foto", "mais", cor_icone="#60a5fa",
                           dica="Cria um recorte novo para uma foto que não foi detectada")
        b_add.clicked.connect(self._adicionar)
        b_div = tema.botao("Dividir em duas", "dividir", cor_icone="#60a5fa",
                           dica="Separa ao meio um recorte que juntou duas fotos encostadas")
        b_div.clicked.connect(self._dividir)
        b_rem = tema.botao("Remover esta foto", "lixeira", "perigo", "#fb7185",
                           dica="Apaga o recorte selecionado (ex.: uma mancha detectada como foto)")
        b_rem.clicked.connect(self._remover)
        for b in (b_add, b_div, b_rem):
            lv.addWidget(b)

        ajuda = QLabel(
            "• <b>Clique</b> num recorte para selecioná-lo.<br>"
            "• Arraste os <b>cantos</b> e as <b>bordas</b> para ajustar; o <b>círculo</b> gira.<br>"
            "• Arraste o <b>interior</b> para mover.<br>"
            "• <b>Roda do mouse</b>: zoom. Arraste fora dos recortes para navegar.")
        ajuda.setWordWrap(True)
        ajuda.setObjectName("subtitulo")
        ajuda.setStyleSheet("margin-top: 8px;")
        lv.addWidget(ajuda)
        lv.addStretch()
        aplicar = tema.botao("Aplicar", "check", "primario", "white")
        aplicar.setDefault(True)
        aplicar.clicked.connect(self.accept)
        cancelar = tema.botao("Cancelar")
        cancelar.clicked.connect(self.reject)
        lv.addWidget(aplicar)
        lv.addWidget(cancelar)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.view, 1)
        lay.addWidget(lateral)

        self.angulo.valueChanged.connect(self._angulo_digitado)
        self._ativar(self.area)

    def showEvent(self, ev):
        super().showEvent(ev)
        self.view.ajustar()

    # ---------------- recortes ----------------

    def _ligar(self, area):
        self.view.adicionar(area)
        area.alterado.connect(lambda a=area: self._sincronizar() if a is self.area else None)
        area.clicado.connect(self._ativar)

    def _ativar(self, area):
        for a in self.view.areas:
            a.ativar(a is area)
        self.area = area
        self._sincronizar()

    def _sincronizar(self):
        r = self.area.recorte()
        n = len(self.view.areas)
        self.lbl_ativa.setText(f"FOTO {self.area.numero} DE {n} (SELECIONADA)")
        self.lbl_qtd.setText(f"FOTOS NESTA PÁGINA: {n}")
        self.angulo.blockSignals(True)
        self.angulo.setValue(r.angulo)
        self.angulo.blockSignals(False)
        texto = f"{round(r.w)} x {round(r.h)} px"
        if self._dpi:
            texto += f"\n{r.w / self._dpi * 2.54:.1f} x {r.h / self._dpi * 2.54:.1f} cm"
        self.lbl_tamanho.setText(texto)

    def _angulo_digitado(self, valor):
        r = self.area.recorte()
        r.angulo = valor
        self.area.definir(r)

    def _adicionar(self):
        pagina = self.view.imagem.boundingRect()
        if self._dpi and self._tamanho_cm:
            w, h = (v / 2.54 * self._dpi for v in self._tamanho_cm)
        else:
            w, h = pagina.width() * 0.3, pagina.height() * 0.3
        c = self.view.centro_visivel()
        cx = min(max(c.x(), w / 2), pagina.width() - w / 2)
        cy = min(max(c.y(), h / 2), pagina.height() - h / 2)
        nova = AreaRecorte(Recorte(cx, cy, w, h))
        self._ligar(nova)
        self._ativar(nova)

    def _dividir(self):
        primeira, segunda = dividir(self.area.recorte())
        self.area.definir(primeira)
        nova = AreaRecorte(segunda)
        self._ligar(nova)
        self._ativar(nova)

    def _remover(self):
        if len(self.view.areas) == 1:
            QMessageBox.information(self, "Remover foto",
                                    "A página precisa ter ao menos um recorte. Para não salvar esta foto, "
                                    "use “Excluir” na tela de revisão.")
            return
        self.view.remover(self.area)
        self._ativar(self.view.areas[0])

    def resultado(self):
        """[(foto existente ou None, Recorte)] de cada recorte, e a foto/índice do recorte ativo."""
        return [(a.foto, a.recorte()) for a in self.view.areas], self.view.areas.index(self.area)
