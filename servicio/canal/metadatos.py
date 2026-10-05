"""Metadatos de las imágenes que envía el cliente (SEGURIDAD T-4): una foto puede traer la ubicación GPS, el modelo del
teléfono y la hora exacta. Se quitan antes de guardarla, leyendo la estructura del archivo (no su contenido visual):

- JPEG: se quitan los segmentos de aplicación APP1-APP13 y APP15 (EXIF, XMP, IPTC y similares) y los comentarios; se
  conservan APP0 (JFIF) y APP14 (Adobe), que el decodificador puede necesitar para mostrar los colores.
- PNG: se quitan los fragmentos de texto, fecha y EXIF; se conservan los críticos y los que definen cómo se ve.

Un archivo que no se puede recorrer con esa estructura se rechaza: es mejor no guardarlo que guardarlo con datos
ocultos. Lo que venga después del final de la imagen (un archivo pegado al final, para que una imagen sea a la vez otra cosa) se descarta.

- PDF: no se reescribe (declarado), pero se rechaza el que declare contenido activo (JavaScript, acciones al abrir o lanzar un programa, archivos
  incrustados, formularios que envían datos) o esconda sus nombres con escapes hexadecimales. Es defensa en profundidad, no un antivirus: un PDF con
  el contenido en flujos comprimidos no se ve desde aquí; por eso el PDF solo se sirve como descarga, nunca se abre en el navegador del asesor.
"""
from __future__ import annotations

import re
import struct


class ArchivoIlegible(ValueError):
    """La estructura del archivo no corresponde a su tipo."""


_JPEG_CONSERVAR = {0xE0, 0xEE}                                  # APP0 (JFIF) y APP14 (Adobe)
_PNG_CONSERVAR = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT", b"bKGD", b"pHYs"}


def _jpeg(datos: bytes) -> bytes:
    if datos[:2] != b"\xff\xd8":
        raise ArchivoIlegible("jpeg sin inicio")
    salida, i = bytearray(b"\xff\xd8"), 2
    while i < len(datos):
        if datos[i] != 0xFF:
            raise ArchivoIlegible("jpeg: segmento sin marca")
        marca = datos[i + 1]
        if marca == 0xD9:                                       # fin de imagen
            salida += datos[i:i + 2]
            return bytes(salida)
        if marca == 0xDA:                                       # inicio del escaneo: el resto son datos de la imagen, hasta el fin (EOI)
            resto = datos[i:]
            fin_imagen = resto.rfind(b"\xff\xd9")
            if fin_imagen < 0:
                raise ArchivoIlegible("jpeg sin fin de imagen")
            salida += resto[: fin_imagen + 2]                   # lo que haya después del fin de la imagen no se guarda
            return bytes(salida)
        if 0xD0 <= marca <= 0xD7 or marca == 0x01:              # marcas sin longitud
            salida += datos[i:i + 2]
            i += 2
            continue
        if i + 4 > len(datos):
            raise ArchivoIlegible("jpeg cortado")
        largo = struct.unpack(">H", datos[i + 2:i + 4])[0]
        fin = i + 2 + largo
        if largo < 2 or fin > len(datos):
            raise ArchivoIlegible("jpeg: longitud inválida")
        es_metadato = (0xE1 <= marca <= 0xEF and marca not in _JPEG_CONSERVAR) or marca == 0xFE
        if not es_metadato:
            salida += datos[i:fin]
        i = fin
    raise ArchivoIlegible("jpeg sin fin")


def _png(datos: bytes) -> bytes:
    firma = b"\x89PNG\r\n\x1a\n"
    if datos[:8] != firma:
        raise ArchivoIlegible("png sin firma")
    salida, i = bytearray(firma), 8
    while i + 8 <= len(datos):
        largo = struct.unpack(">I", datos[i:i + 4])[0]
        tipo = datos[i + 4:i + 8]
        fin = i + 12 + largo
        if fin > len(datos):
            raise ArchivoIlegible("png: fragmento cortado")
        if tipo in _PNG_CONSERVAR:
            salida += datos[i:fin]
        if tipo == b"IEND":
            return bytes(salida)
        i = fin
    raise ArchivoIlegible("png sin fin")


_PDF_ACTIVO = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|OpenAction|AA|RichMedia|XFA|SubmitForm|ImportData|GoToR)(?![A-Za-z0-9])")
_PDF_NOMBRE_OCULTO = re.compile(rb"/[A-Za-z]*#[0-9A-Fa-f]{2}")           # /J#61vaScript: un nombre escrito con escapes para que no se lea


def _pdf(datos: bytes) -> bytes:
    if _PDF_ACTIVO.search(datos) or _PDF_NOMBRE_OCULTO.search(datos):
        raise ArchivoIlegible("pdf con contenido activo")
    return datos


def limpiar(datos: bytes, tipo: str) -> bytes:
    """El archivo sin sus metadatos y sin lo que no debe llevar, según su tipo real. El audio no se guarda y vuelve igual."""
    if tipo == "image/jpeg":
        return _jpeg(datos)
    if tipo == "image/png":
        return _png(datos)
    if tipo == "application/pdf":
        return _pdf(datos)
    return datos
