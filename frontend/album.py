"""Janela que pede o nome do álbum (ao salvar) e mostra a pasta que será criada."""
from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout

from backend.processamento import carregar_album, nome_seguro, pasta_album
from . import tema


class DialogoAlbum(QDialog):
    """base: onde a pasta do álbum será criada; pasta_atual: pasta já usada nesta sessão (ou None)."""

    def __init__(self, base, sugestao="", pasta_atual=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Salvar álbum")
        self.setMinimumWidth(600)
        self._base = Path(base)
        self._pasta_atual = pasta_atual
        self.substituir = False  # o usuário confirmou substituir outro álbum com o mesmo nome

        titulo = QLabel("Salvar álbum")
        titulo.setObjectName("tituloGrande")
        sub = QLabel("Dê um nome ao álbum. As fotos vão para uma pasta com este nome, numeradas em sequência "
                     "(ex.: Férias 1987_001.png, Férias 1987_002.png…).")
        sub.setObjectName("subtitulo")
        sub.setWordWrap(True)
        self.campo = QLineEdit(sugestao, placeholderText="Ex.: Férias em Santos 1987")
        self.campo.textChanged.connect(self._atualizar)
        self.lbl_pasta = QLabel(wordWrap=True)
        self.lbl_pasta.setObjectName("subtitulo")
        alterar = tema.botao("Alterar local…", "pasta", tipo="link")
        alterar.clicked.connect(self._alterar_local)
        linha_pasta = QHBoxLayout()
        linha_pasta.addWidget(self.lbl_pasta, 1)
        linha_pasta.addWidget(alterar)
        self.lbl_aviso = QLabel(wordWrap=True)
        self.lbl_aviso.setObjectName("explicacao")

        self.btn_ok = tema.botao("Salvar álbum", "download", "primario", "white")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept)
        cancelar = tema.botao("Cancelar")
        cancelar.clicked.connect(self.reject)
        botoes = QHBoxLayout()
        botoes.addStretch()
        botoes.addWidget(cancelar)
        botoes.addWidget(self.btn_ok)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)
        lay.addWidget(titulo)
        lay.addWidget(sub)
        lay.addSpacing(6)
        lay.addWidget(self.campo)
        lay.addLayout(linha_pasta)
        lay.addWidget(self.lbl_aviso)
        lay.addSpacing(6)
        lay.addLayout(botoes)
        self.campo.selectAll()
        self._atualizar()

    def nome(self):
        return self.campo.text().strip()

    def pasta(self):
        return pasta_album(self._base, self.nome())

    def _alterar_local(self):
        escolhida = QFileDialog.getExistingDirectory(self, "Onde criar a pasta do álbum", str(self._base))
        if escolhida:
            self._base = Path(escolhida)
            self._atualizar()

    def _atualizar(self):
        self._mostrar_situacao()
        self.adjustSize()  # o aviso aparece/some: a janela acompanha a altura do texto

    def _mostrar_situacao(self):
        valido = bool(nome_seguro(self.nome()))
        self.btn_ok.setEnabled(valido)
        self.substituir = False
        self.btn_ok.setText("Salvar álbum")
        tema.definir_prop(self.btn_ok, "tipo", "primario")
        if not valido:
            self.lbl_pasta.setText(f"Local: {self._base}")
            self.lbl_aviso.hide()
            return
        pasta = self.pasta()
        self.lbl_pasta.setText(f"Pasta do álbum: {pasta}")
        if self._pasta_atual and pasta == self._pasta_atual:
            self.lbl_aviso.setText("Este é o álbum desta sessão: as fotos dele serão atualizadas.")
            self.lbl_aviso.show()
        elif carregar_album(pasta):
            self.substituir = True
            self.btn_ok.setText("Substituir álbum existente")
            tema.definir_prop(self.btn_ok, "tipo", "perigo")
            self.lbl_aviso.setText("⚠ Já existe outro álbum com este nome neste local. Se continuar, ele será "
                                   "<b>substituído</b> por este: as fotos dele serão sobrescritas ou apagadas. "
                                   "Para mantê-lo, escolha outro nome.")
            self.lbl_aviso.show()
        elif pasta.exists() and any(pasta.iterdir()):
            self.lbl_aviso.setText("⚠ Já existe uma pasta com este nome. As fotos do álbum serão gravadas nela, "
                                   "substituindo arquivos com o mesmo nome.")
            self.lbl_aviso.show()
        else:
            self.lbl_aviso.hide()
