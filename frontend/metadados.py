"""Janela para informar os metadados do álbum: data estimada, local e descrição."""
from datetime import date
from urllib.parse import quote

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QSpinBox, QVBoxLayout)

from backend.metadados import MESES, Metadados, ler_coordenadas
from . import tema


def _secao(nome_icone, texto):
    lay = QHBoxLayout()
    ic = QLabel()
    ic.setPixmap(tema.icone(nome_icone, "#60a5fa", 14).pixmap(14, 14))
    sec = QLabel(texto)
    sec.setObjectName("secao")
    lay.addWidget(ic)
    lay.addWidget(sec)
    lay.addStretch()
    return lay


class DialogoMetadados(QDialog):
    def __init__(self, metadados, album, parent=None):
        """metadados: Metadados atuais do álbum; album: nome (None se ainda não foi salvo).

        O resultado fica em self.resultado.
        """
        super().__init__(parent)
        self.setWindowTitle("Metadados do álbum")
        self.setMinimumWidth(820)
        self.resultado = metadados

        titulo = QLabel(f"Metadados do álbum “{album}”" if album else "Metadados do álbum")
        titulo.setObjectName("tituloGrande")
        sub = QLabel("Gravados em todas as fotos do álbum. O Google Fotos e outros organizadores usam a data e a "
                     "localização para colocar cada foto no lugar certo da linha do tempo e do mapa.")
        sub.setObjectName("subtitulo")
        sub.setWordWrap(True)

        # Data
        self.usar_data = QCheckBox("Informar a data em que as fotos foram tiradas")
        hoje = date.today().year
        self.ano = QSpinBox(minimum=1826, maximum=hoje, value=hoje - 30)
        self.mes = QComboBox()
        self.mes.addItem("Mês: não sei", None)
        for i, m in enumerate(MESES, 1):
            self.mes.addItem(m, i)
        self.dia = QComboBox()
        self.dia.addItem("Dia: não sei", None)
        for d in range(1, 32):
            self.dia.addItem(str(d), d)
        self.lbl_data = QLabel()
        self.lbl_data.setObjectName("subtitulo")
        self.lbl_data.setWordWrap(True)
        grade_data = QGridLayout()
        for col, (rot, w) in enumerate((("Ano", self.ano), ("Mês", self.mes), ("Dia", self.dia))):
            r = QLabel(rot)
            r.setObjectName("subtitulo")
            grade_data.addWidget(r, 0, col)
            grade_data.addWidget(w, 1, col)
        for w in (self.usar_data,):
            w.toggled.connect(self._atualizar)
        self.ano.valueChanged.connect(self._atualizar)
        self.mes.currentIndexChanged.connect(self._atualizar)
        self.dia.currentIndexChanged.connect(self._atualizar)

        # Local
        self.local = QLineEdit(placeholderText="Ex.: Santos, SP")
        self.coords = QLineEdit(placeholderText="Ex.: -23.9608, -46.3336")
        self.coords.textChanged.connect(self._atualizar)
        self.lbl_coords = QLabel()
        self.lbl_coords.setObjectName("subtitulo")
        self.lbl_coords.setWordWrap(True)
        abrir_mapa = tema.botao("Abrir no Google Maps", "local", tipo="link")
        abrir_mapa.setToolTip("Abre o navegador pesquisando o nome do local digitado acima")
        abrir_mapa.clicked.connect(self._abrir_mapa)
        grade_local = QGridLayout()
        for lin, (rot, w) in enumerate((("Nome do local", self.local), ("Coordenadas (latitude, longitude)",
                                                                        self.coords))):
            r = QLabel(rot)
            r.setObjectName("subtitulo")
            grade_local.addWidget(r, lin * 2, 0)
            grade_local.addWidget(w, lin * 2 + 1, 0)
        dica_mapa = QLabel("Para obter as coordenadas: no Google Maps, clique com o botão direito no local e "
                           "clique nos números que aparecem no topo do menu; eles são copiados. Cole aqui.")
        dica_mapa.setObjectName("subtitulo")
        dica_mapa.setWordWrap(True)

        # Descrição
        self.descricao = QLineEdit(placeholderText="Ex.: Férias em família")

        aviso = QFrame()
        aviso.setObjectName("diagnostico")
        tema.definir_prop(aviso, "estado", "revisar")
        la = QHBoxLayout(aviso)
        la.setContentsMargins(12, 10, 12, 10)
        ic = QLabel(alignment=Qt.AlignTop)
        ic.setPixmap(tema.icone("alerta", tema.CORES_ESTADO["revisar"], 16).pixmap(16, 16))
        txt = QLabel("<b>Privacidade:</b> a data e a localização ficam gravadas dentro dos arquivos. Quem receber "
                     "as fotos poderá ver onde e quando foram tiradas.")
        txt.setWordWrap(True)
        la.addWidget(ic)
        la.addWidget(txt, 1)

        salvar = tema.botao("Salvar metadados", "check", "primario", "white")
        salvar.setDefault(True)
        salvar.clicked.connect(self._confirmar)
        cancelar = tema.botao("Cancelar")
        cancelar.clicked.connect(self.reject)
        botoes = QHBoxLayout()
        botoes.addStretch()
        botoes.addWidget(cancelar)
        botoes.addWidget(salvar)

        # Duas colunas: data e descrição à esquerda, local à direita (cabe em telas baixas).
        esquerda = QVBoxLayout()
        esquerda.setSpacing(8)
        esquerda.addLayout(_secao("calendario", "DATA ESTIMADA"))
        esquerda.addWidget(self.usar_data)
        esquerda.addLayout(grade_data)
        esquerda.addWidget(self.lbl_data)
        esquerda.addSpacing(10)
        esquerda.addLayout(_secao("texto", "DESCRIÇÃO"))
        esquerda.addWidget(self.descricao)
        esquerda.addStretch()
        direita = QVBoxLayout()
        direita.setSpacing(8)
        direita.addLayout(_secao("local", "LOCAL"))
        direita.addLayout(grade_local)
        direita.addWidget(self.lbl_coords)
        direita.addWidget(dica_mapa)
        direita.addWidget(abrir_mapa, 0, Qt.AlignLeft)
        direita.addStretch()
        colunas = QHBoxLayout()
        colunas.setSpacing(28)
        colunas.addLayout(esquerda, 1)
        colunas.addLayout(direita, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)
        lay.addWidget(titulo)
        lay.addWidget(sub)
        lay.addSpacing(8)
        lay.addLayout(colunas)
        lay.addSpacing(8)
        lay.addWidget(aviso)
        lay.addLayout(botoes)

        self._carregar(metadados)

    # ---------------- campos <-> Metadados ----------------

    def _carregar(self, m):
        self.usar_data.setChecked(bool(m.ano))
        if m.ano:
            self.ano.setValue(m.ano)
        self.mes.setCurrentIndex(m.mes or 0)
        self.dia.setCurrentIndex(m.dia or 0)
        self.local.setText(m.local)
        self.coords.setText(f"{m.latitude}, {m.longitude}" if m.tem_gps() else "")
        self.descricao.setText(m.descricao)
        self._atualizar()

    def _ler(self):
        """Metadados dos campos; retorna None (e avisa) se as coordenadas forem inválidas."""
        coords = None
        if self.coords.text().strip():
            coords = ler_coordenadas(self.coords.text())
            if coords is None:
                QMessageBox.warning(self, "Coordenadas inválidas",
                                    "Use o formato latitude, longitude. Exemplo: -23.9608, -46.3336")
                return None
        usar = self.usar_data.isChecked()
        mes = self.mes.currentData() if usar else None
        return Metadados(ano=self.ano.value() if usar else None, mes=mes,
                         dia=self.dia.currentData() if usar and mes else None,
                         descricao=self.descricao.text().strip(), local=self.local.text().strip(),
                         latitude=coords[0] if coords else None, longitude=coords[1] if coords else None)

    def _atualizar(self):
        usar = self.usar_data.isChecked()
        self.ano.setEnabled(usar)
        self.mes.setEnabled(usar)
        self.dia.setEnabled(usar and self.mes.currentData() is not None)
        if usar:
            m = Metadados(self.ano.value(), self.mes.currentData(),
                          self.dia.currentData() if self.mes.currentData() else None)
            gravada = m.data().strftime("%d/%m/%Y")
            nota = "" if m.mes and m.dia else " Partes desconhecidas são gravadas como dia/mês 1."
            self.lbl_data.setText(f"Data gravada nas fotos: {gravada} (estimativa: {m.texto_data()}).{nota}")
        else:
            self.lbl_data.setText("Sem data: os serviços de fotos usarão a data do envio.")
        texto = self.coords.text().strip()
        if not texto:
            self.lbl_coords.setText("Sem coordenadas: as fotos não aparecerão no mapa.")
            self.lbl_coords.setStyleSheet("")
        elif ler_coordenadas(texto):
            lat, lon = ler_coordenadas(texto)
            self.lbl_coords.setText(f"✓ Coordenadas válidas: {abs(lat):.4f}° {'S' if lat < 0 else 'N'}, "
                                    f"{abs(lon):.4f}° {'O' if lon < 0 else 'L'}")
            self.lbl_coords.setStyleSheet(f"color: {tema.CORES_ESTADO['ok']};")
        else:
            self.lbl_coords.setText("Formato não reconhecido. Exemplo: -23.9608, -46.3336")
            self.lbl_coords.setStyleSheet(f"color: {tema.CORES_ESTADO['excluida']};")

    def _abrir_mapa(self):
        termo = self.local.text().strip()
        url = f"https://www.google.com/maps/search/{quote(termo)}" if termo else "https://www.google.com/maps"
        QDesktopServices.openUrl(QUrl(url))

    def _confirmar(self):
        m = self._ler()
        if m is None:
            return
        self.resultado = m
        self.accept()
