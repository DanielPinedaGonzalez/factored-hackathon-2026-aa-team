"""Idiomas: una sola fuente y ningún respaldo invisible (contratos/idiomas.py)."""
import re
from pathlib import Path

import yaml

from contratos.idiomas import IDIOMA_BASE, IDIOMAS, declarado, es_soportado, normalizar
from servicio.conocimiento.conocimiento import _fila_a_articulo

RAIZ = Path(__file__).resolve().parents[2]


def test_la_lista_de_idiomas_no_se_repite_fuera_de_su_fuente():
    patron = re.compile(r'\(\s*"es"\s*,\s*"pt"\s*\)')
    repetidos = [str(p.relative_to(RAIZ)) for d in ("servicio", "contratos", "pipeline", "ml", "evaluacion")
                 for p in (RAIZ / d).rglob("*.py") if p.name != "idiomas.py" and patron.search(p.read_text())]
    assert not repetidos, f"escriben la lista de idiomas a mano: {repetidos}"


def test_normalizar_y_declarar_no_se_confunden():
    assert normalizar("pt") == "pt" and normalizar("en") == IDIOMA_BASE and normalizar(None) == IDIOMA_BASE
    assert declarado("pt") == "pt" and declarado("en") == "otro"       # un texto en inglés no se disfraza de español
    assert es_soportado("es") and not es_soportado("en")


def test_un_respaldo_de_articulo_se_declara():
    f = {"id": "x", "version": 1, "titulo": "t", "cabecera": {"id": "x", "titulo": "t"}, "cuerpo_es": "texto", "cuerpo_pt": None,
         "criticidad": "alta"}
    assert _fila_a_articulo(f, "pt")["idioma_cuerpo"] == "es"           # sin pt: cae al base y lo dice
    assert _fila_a_articulo({**f, "cuerpo_pt": "texto pt"}, "pt")["idioma_cuerpo"] == "pt"


def test_todo_articulo_para_el_cliente_trae_su_cuerpo_en_cada_idioma():
    faltan = []
    for p in (RAIZ / "conocimiento" / "publico").glob("*.md"):
        cuerpo = p.read_text()
        faltan += [f"{p.name}:{i}" for i in IDIOMAS if not re.search(rf"^## {i}\b", cuerpo, re.M)]
    assert not faltan, f"artículos públicos sin cuerpo en un idioma soportado: {faltan}"
