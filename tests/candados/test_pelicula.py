"""La película de lanzamiento (`docs/lanzamiento/`) sale de una sola fuente (`escenas.py`) y se abre sin errores.

El guion y la película no se editan a mano: si alguien cambia `escenas.py` y no regenera, esta prueba falla."""
import importlib.util
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
CARPETA = RAIZ / "docs" / "lanzamiento"


def _cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, CARPETA / f"{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_cada_escena_tiene_su_frase_en_ingles_y_su_sentido_en_espanol():
    esc = _cargar("escenas")
    ids = [e["id"] for e in esc.ESCENAS]
    assert len(ids) == len(set(ids)) and {e["bloque"] for e in esc.ESCENAS} <= {"WHY", "WHAT", "HOW", "CLOSE"}
    assert all(e["en"].strip() and e["es"].strip() and e["en"] != e["es"] and e["seg"] > 0 for e in esc.ESCENAS)
    html = (CARPETA / "plantilla.html").read_text(encoding="utf-8")
    assert all(f'data-id="{i}"' in html for i in ids), "una escena de escenas.py no tiene su <section> en la plantilla"


def test_la_pelicula_generada_esta_al_dia_con_las_escenas():
    esc, gen = _cargar("escenas"), _cargar("generar")
    esperado = (gen.ordenar((CARPETA / "plantilla.html").read_text(encoding="utf-8"))
                .replace("__ESCENAS__", json.dumps(esc.ESCENAS, ensure_ascii=False)).replace("__CHAT__", json.dumps(esc.CHAT_REAL, ensure_ascii=False)))
    assert (CARPETA / "lanzamiento.html").read_text(encoding="utf-8") == esperado, "regenera: python docs/lanzamiento/generar.py"
    assert gen.guion_md().count("### ") == len(esc.ESCENAS)
    import re
    en_pagina = re.findall(r'<section class="escena[^"]*" data-id="(\w+)"', esperado)
    assert en_pagina == [e["id"] for e in esc.ESCENAS], "el orden de las escenas en la página no es el del guion: la frase de voz se desfasaría"


def test_el_chat_de_la_pelicula_es_lo_que_dijo_el_modelo_real_sin_retocar():
    corrida = RAIZ / "evaluacion" / "corridas" / "20261004T041117_propuesto_desarrollo.json"
    if not corrida.exists():
        pytest.skip("las corridas no van en el export público")
    salidas = json.loads(corrida.read_text(encoding="utf-8"))["conversaciones"]["A1"]["salidas"]
    lora = [x["texto"] for x in _cargar("escenas").CHAT_REAL if x["quien"] == "lora"]
    assert lora == [s["texto"] for s in salidas[1:]]


def test_la_pelicula_recorre_todas_sus_escenas_sin_errores_de_javascript():
    sync_api = pytest.importorskip("playwright.sync_api")
    esc = _cargar("escenas")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:
            pytest.skip(f"sin navegador: {e}")
        pg = b.new_page(viewport={"width": 1280, "height": 720})
        errores = []
        pg.on("pageerror", lambda e: errores.append(str(e)))
        pg.goto((CARPETA / "lanzamiento.html").as_uri() + "?grabar=1")
        for _ in esc.ESCENAS[1:]:
            pg.keyboard.press("Space")
            pg.wait_for_timeout(150)
        assert pg.locator(".escena.activa").get_attribute("data-id") == esc.ESCENAS[-1]["id"]
        g = b.new_page()                                          # la ventana con la frase que se dice
        g.goto((CARPETA / "lanzamiento.html").as_uri() + "?guion=1")
        assert esc.ESCENAS[0]["en"] in g.locator("#guion .sig").inner_text()
        b.close()
    assert not errores, errores
