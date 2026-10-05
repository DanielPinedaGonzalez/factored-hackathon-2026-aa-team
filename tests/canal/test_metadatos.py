"""SEGURIDAD T-4: las fotos se guardan sin metadatos (ubicación, cámara, fecha); la imagen queda intacta."""
import struct
import zlib

import pytest

from servicio.canal.metadatos import ArchivoIlegible, limpiar


def _seg(marca: int, carga: bytes) -> bytes:
    return bytes([0xFF, marca]) + struct.pack(">H", len(carga) + 2) + carga


def test_jpeg_pierde_exif_y_comentarios_y_conserva_la_imagen():
    exif = _seg(0xE1, b"Exif\x00\x00GPS 19.4326N 99.1332W iPhone")
    jfif = _seg(0xE0, b"JFIF\x00\x01\x01")
    comentario = _seg(0xFE, b"tomada en casa")
    tabla = _seg(0xDB, b"\x00" + bytes(64))
    escaneo = b"\xff\xda" + struct.pack(">H", 8) + b"\x01\x01\x00\x00\x3f\x00" + b"\x12\x34\xff\x00\x56" + b"\xff\xd9"
    original = b"\xff\xd8" + jfif + exif + comentario + tabla + escaneo
    limpio = limpiar(original, "image/jpeg")
    assert b"GPS" not in limpio and b"iPhone" not in limpio and b"tomada" not in limpio
    assert limpio == b"\xff\xd8" + jfif + tabla + escaneo


def _chunk(tipo: bytes, datos: bytes) -> bytes:
    return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos))


def test_png_pierde_texto_y_fecha_y_conserva_los_fragmentos_de_la_imagen():
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = _chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
    iend = _chunk(b"IEND", b"")
    original = b"\x89PNG\r\n\x1a\n" + ihdr + _chunk(b"tEXt", b"GPS\x0019.43N") + _chunk(b"tIME", bytes(7)) + idat + iend
    assert limpiar(original, "image/png") == b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def test_un_archivo_que_no_se_puede_recorrer_se_rechaza_y_el_pdf_no_se_toca():
    with pytest.raises(ArchivoIlegible):
        limpiar(b"\xff\xd8\xff\xe1\xff\xff", "image/jpeg")
    assert limpiar(b"%PDF-1.4 x", "application/pdf") == b"%PDF-1.4 x"


# --- archivos que intentan llevar algo más (SEGURIDAD T-4) ---

def test_lo_que_venga_despues_del_fin_de_un_jpeg_no_se_guarda():
    """Una imagen con un archivo pegado al final (una imagen que es a la vez otra cosa) llega solo con la imagen."""
    escaneo = b"\xff\xda" + struct.pack(">H", 8) + b"\x01\x01\x00\x00\x3f\x00" + b"\x12\x34\xff\x00\x56" + b"\xff\xd9"
    imagen = b"\xff\xd8" + _seg(0xDB, b"\x00" + bytes(64)) + escaneo
    limpio = limpiar(imagen + b"MZ\x90\x00 programa escondido PK\x03\x04 zip escondido", "image/jpeg")
    assert limpio == imagen and b"MZ" not in limpio and b"PK" not in limpio


def test_lo_que_venga_despues_del_fin_de_un_png_no_se_guarda():
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = _chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
    imagen = b"\x89PNG\r\n\x1a\n" + ihdr + idat + _chunk(b"IEND", b"")
    assert limpiar(imagen + b"MZ\x90\x00 programa escondido", "image/png") == imagen


@pytest.mark.parametrize("activo", [b"/JavaScript (app.alert(1))", b"/JS (x)", b"/OpenAction 5 0 R", b"/Launch /F (cmd.exe)", b"/EmbeddedFile",
                                    b"/AA << /O 3 0 R >>", b"/SubmitForm", b"/J#61vaScript (oculto con escapes)"])
def test_un_pdf_con_contenido_activo_se_rechaza(activo):
    with pytest.raises(ArchivoIlegible):
        limpiar(b"%PDF-1.4\n1 0 obj << " + activo + b" >> endobj\n%%EOF", "application/pdf")


def test_un_pdf_comun_con_enlaces_y_texto_pasa_intacto():
    pdf = b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n3 0 obj << /Type /Annot /URI (https://banco.example) >> endobj\n%%EOF"
    assert limpiar(pdf, "application/pdf") == pdf
