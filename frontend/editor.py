"""Editor de recorte: retângulo com cantos, bordas e rotação sobre a página original."""
from math import atan2, cos, degrees, radians, sin

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QDialog, QDoubleSpinBox, QFormLayout, QFrame, QGraphicsItem, QGraphicsObject,
                               QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
                               QHBoxLayout, QLabel, QVBoxLayout)

from backend.recorte import Recorte
from . import tema
from .imagens import pixmap_de_array

COR = QColor("#3b82f6")
ALCA = 10  # tamanho das alças em pixels de tela
DIST_GIRO = 40  # distância da alça de giro acima do recorte, em pixels de tela
TAM_MIN = 20.0


class AreaRecorte(QGraphicsObject):
    alterado = Signal()

    def __init__(self, r):
        super().__init__()
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
        pen = QPen(COR, 2)
        pen.setCosmetic(True)
        p.setPen(pen)
        w2, h2 = self._w / 2, self._h / 2
        p.drawRect(QRectF(-w2, -h2, self._w, self._h))
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
        s = self._px()
        tol = ALCA * s
        w2, h2 = self._w / 2, self._h / 2
        x, y = pt.x(), pt.y()
        if (x ** 2 + (y + h2 + DIST_GIRO * s) ** 2) ** 0.5 <= tol * 1.2:
            return ("girar",)
        dentro_x, dentro_y = -w2 - tol <= x <= w2 + tol, -h2 - tol <= y <= h2 + tol
        sx = -1 if abs(x + w2) <= tol else 1 if abs(x - w2) <= tol else 0
        sy = -1 if abs(y + h2) <= tol else 1 if abs(y - h2) <= tol else 0
        sx, sy = (sx if dentro_y else 0), (sy if dentro_x else 0)
        if sx or sy:
            return ("redimensionar", sx, sy)
        if abs(x) < w2 and abs(y) < h2:
            return ("mover",)
        return None

    def hoverMoveEvent(self, ev):
        alvo = self._alvo(ev.pos())
        if alvo is None:
            self.unsetCursor()
        elif alvo[0] == "girar":
            self.setCursor(Qt.PointingHandCursor)
        elif alvo[0] == "mover":
            self.setCursor(Qt.SizeAllCursor)
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
    def __init__(self, pixmap, recorte):
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
        self.scene().addItem(self.mascara)
        self.area = AreaRecorte(recorte)
        self.scene().addItem(self.area)
        self.area.alterado.connect(self._atualizar_mascara)
        self._atualizar_mascara()

    def _atualizar_mascara(self):
        caminho = QPainterPath()
        caminho.addRect(self.imagem.boundingRect())
        caminho.addPolygon(self.area.poligono())  # preenchimento par/ímpar deixa o recorte vazado
        self.mascara.setPath(caminho)

    def ajustar(self):
        self.fitInView(self.imagem.boundingRect().adjusted(-40, -80, 40, 40), Qt.KeepAspectRatio)
        self._escala_mudou()

    def tamanho_real(self):
        self.resetTransform()
        self.centerOn(self.area.pos())
        self._escala_mudou()

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
        self.area.escala_mudou()


class EditorRecorte(QDialog):
    def __init__(self, foto, imagem, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Editar recorte: {foto.arquivo.name}, página {foto.pagina + 1}")
        self._foto = foto
        self.view = Visualizador(pixmap_de_array(imagem), foto.recorte)
        self.area = self.view.area

        lateral = QFrame()
        lateral.setObjectName("lateral")
        lateral.setFixedWidth(300)
        lv = QVBoxLayout(lateral)
        lv.setContentsMargins(18, 18, 18, 18)
        lv.setSpacing(10)
        titulo = QLabel("Editar recorte")
        titulo.setObjectName("titulo")
        sub = QLabel(f"{foto.arquivo.name} • página {foto.pagina + 1}")
        sub.setObjectName("subtitulo")
        lv.addWidget(titulo)
        lv.addWidget(sub)
        lv.addSpacing(6)
        self.angulo = QDoubleSpinBox(minimum=-180, maximum=180, decimals=2, singleStep=0.05, suffix="°")
        self.angulo.setKeyboardTracking(False)
        self.lbl_tamanho = QLabel()
        self.lbl_tamanho.setObjectName("specValor")
        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Ângulo:", self.angulo)
        form.addRow("Tamanho:", self.lbl_tamanho)
        lv.addLayout(form)
        lv.addSpacing(6)
        for texto, nome_icone, acao in (("Restaurar automático", "restaurar", lambda: self.area.definir(foto.auto)),
                                        ("Ajustar à janela", "ajustar", self.view.ajustar),
                                        ("Zoom 100% (pixels reais)", "zoom_mais", self.view.tamanho_real)):
            b = tema.botao(texto, nome_icone, cor_icone="#60a5fa")
            b.clicked.connect(acao)
            lv.addWidget(b)
        ajuda = QLabel(
            "• Arraste os <b>cantos</b> e as <b>bordas</b> para ajustar o recorte.<br><br>"
            "• Arraste o <b>círculo</b> acima do recorte para girar, ou digite o ângulo.<br><br>"
            "• Arraste o <b>interior</b> para mover o recorte.<br><br>"
            "• <b>Roda do mouse</b>: zoom. Arraste fora do recorte para navegar.")
        ajuda.setWordWrap(True)
        ajuda.setObjectName("subtitulo")
        ajuda.setStyleSheet("margin-top: 12px;")
        lv.addWidget(ajuda)
        lv.addStretch()
        aplicar = tema.botao("Aplicar recorte", "check", "primario", "white")
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

        self.area.alterado.connect(self._sincronizar)
        self.angulo.valueChanged.connect(self._angulo_digitado)
        self._sincronizar()

    def showEvent(self, ev):
        super().showEvent(ev)
        self.view.ajustar()

    def _sincronizar(self):
        r = self.area.recorte()
        self.angulo.blockSignals(True)
        self.angulo.setValue(r.angulo)
        self.angulo.blockSignals(False)
        texto = f"{round(r.w)} x {round(r.h)} px"
        if self._foto.dpi:
            texto += f"\n{r.w / self._foto.dpi * 2.54:.1f} x {r.h / self._foto.dpi * 2.54:.1f} cm"
        self.lbl_tamanho.setText(texto)

    def _angulo_digitado(self, valor):
        r = self.area.recorte()
        r.angulo = valor
        self.area.definir(r)

    def recorte(self):
        return self.area.recorte()
