"""Metadados do lote (data estimada, local, descrição) em EXIF e XMP.

O Google Fotos e outros organizadores usam principalmente o EXIF DateTimeOriginal
e as coordenadas GPS para colocar a foto na data e no lugar certos.
"""
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from xml.sax.saxutils import escape

import piexif
import piexif.helper

PROGRAMA = "Recorte de Fotos"
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
         "Novembro", "Dezembro"]


@dataclass
class Metadados:
    ano: int | None = None
    mes: int | None = None  # 1 a 12
    dia: int | None = None
    descricao: str = ""
    local: str = ""
    latitude: float | None = None
    longitude: float | None = None

    @classmethod
    def de_dict(cls, d):
        nomes = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in nomes})

    def como_dict(self):
        return asdict(self)

    def vazio(self):
        return self == Metadados()

    def data(self):
        """Data/hora usada no EXIF. Partes desconhecidas viram 1º de janeiro / dia 1, ao meio-dia."""
        if not self.ano:
            return None
        mes = self.mes or 1
        dia = self.dia if self.mes and self.dia else 1
        try:
            return datetime(self.ano, mes, dia, 12, 0, 0)
        except ValueError:
            return datetime(self.ano, mes, 1, 12, 0, 0)

    def texto_data(self):
        if not self.ano:
            return ""
        if self.mes and self.dia:
            return f"{self.dia:02d}/{self.mes:02d}/{self.ano}"
        if self.mes:
            return f"{MESES[self.mes - 1]} de {self.ano}"
        return str(self.ano)

    def texto_descricao(self):
        return " — ".join(p for p in (self.descricao.strip(), self.local.strip()) if p)

    def tem_gps(self):
        return self.latitude is not None and self.longitude is not None


def ler_coordenadas(texto):
    """Aceita "-23.5505, -46.6333" (formato copiado do Google Maps). Retorna (lat, lon) ou None."""
    numeros = re.findall(r"-?\d+(?:[.,]\d+)?", texto)
    if len(numeros) != 2:
        return None
    lat, lon = (float(n.replace(",", ".")) for n in numeros)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def _fuso():
    z = datetime.now().astimezone().strftime("%z")  # ex.: -0300
    return f"{z[:3]}:{z[3:]}"


def _racional_gps(valor):
    valor = abs(valor)
    graus = int(valor)
    minutos = int((valor - graus) * 60)
    segundos = round(((valor - graus) * 60 - minutos) * 60 * 10000)
    return ((graus, 1), (minutos, 1), (segundos, 10000))


def montar_exif(meta, dpi=None):
    """Bloco EXIF (formato TIFF, sem o prefixo 'Exif\\0\\0')."""
    zeroth = {piexif.ImageIFD.Software: PROGRAMA.encode()}
    exif = {piexif.ExifIFD.DateTimeDigitized: datetime.now().strftime("%Y:%m:%d %H:%M:%S").encode(),
            piexif.ExifIFD.OffsetTimeDigitized: _fuso().encode()}
    gps = {}
    if dpi:
        zeroth[piexif.ImageIFD.XResolution] = (round(dpi * 100), 100)
        zeroth[piexif.ImageIFD.YResolution] = (round(dpi * 100), 100)
        zeroth[piexif.ImageIFD.ResolutionUnit] = 2
    data = meta.data() if meta else None
    if data:
        texto = data.strftime("%Y:%m:%d %H:%M:%S").encode()
        zeroth[piexif.ImageIFD.DateTime] = texto
        exif[piexif.ExifIFD.DateTimeOriginal] = texto
        exif[piexif.ExifIFD.OffsetTimeOriginal] = _fuso().encode()
    descricao = meta.texto_descricao() if meta else ""
    if descricao:
        zeroth[piexif.ImageIFD.ImageDescription] = descricao.encode("utf-8")
        zeroth[piexif.ImageIFD.XPTitle] = tuple(descricao.encode("utf-16-le") + b"\0\0")
        exif[piexif.ExifIFD.UserComment] = piexif.helper.UserComment.dump(descricao, encoding="unicode")
    if meta and meta.tem_gps():
        gps = {piexif.GPSIFD.GPSVersionID: (2, 2, 0, 0),
               piexif.GPSIFD.GPSLatitudeRef: b"N" if meta.latitude >= 0 else b"S",
               piexif.GPSIFD.GPSLatitude: _racional_gps(meta.latitude),
               piexif.GPSIFD.GPSLongitudeRef: b"E" if meta.longitude >= 0 else b"W",
               piexif.GPSIFD.GPSLongitude: _racional_gps(meta.longitude)}
    return piexif.dump({"0th": zeroth, "Exif": exif, "GPS": gps})[6:]


def montar_xmp(meta):
    """Pacote XMP com as mesmas informações (inclui a data com a precisão real, ex.: só o ano)."""
    atributos = [f'xmp:CreatorTool="{PROGRAMA}"']
    data = meta.data()
    if data:
        completa = data.strftime("%Y-%m-%dT%H:%M:%S") + _fuso()
        atributos += [f'exif:DateTimeOriginal="{completa}"', f'xmp:CreateDate="{completa}"']
        parcial = f"{meta.ano:04d}" + (f"-{meta.mes:02d}" if meta.mes else "") + \
                  (f"-{meta.dia:02d}" if meta.mes and meta.dia else "")
        atributos.append(f'photoshop:DateCreated="{parcial}"')
    if meta.tem_gps():
        for nome, valor, pos, neg in (("GPSLatitude", meta.latitude, "N", "S"),
                                      ("GPSLongitude", meta.longitude, "E", "W")):
            v = abs(valor)
            atributos.append(f'exif:{nome}="{int(v)},{(v - int(v)) * 60:.6f}{pos if valor >= 0 else neg}"')
    descricao = meta.texto_descricao()
    corpo = (f'<dc:description><rdf:Alt><rdf:li xml:lang="x-default">{escape(descricao)}</rdf:li></rdf:Alt>'
             f'</dc:description>') if descricao else ""
    return ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description rdf:about="" xmlns:exif="http://ns.adobe.com/exif/1.0/" '
            'xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/" '
            f'xmlns:dc="http://purl.org/dc/elements/1.1/" {" ".join(atributos)}>{corpo}</rdf:Description>'
            '</rdf:RDF></x:xmpmeta><?xpacket end="w"?>')
