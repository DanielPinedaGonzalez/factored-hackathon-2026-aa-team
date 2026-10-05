"""Las consultas informativas (B3, B10): una gestión fuera de alcance no elige un artículo por una palabra suelta, y pedir una
persona no descarta la pregunta que viene en el mismo mensaje."""
import json
import secrets

import pytest

from servicio.llm.cliente import ModeloFalso
from servicio.orquestador.orquestador import Entrada, procesar
from tests.apoyo import Guion, limpiar_cliente, token_de

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _pendientes(monkeypatch):
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")


def _estado_comunicable(m: ModeloFalso) -> list[dict]:
    ultima = [x for x in m.llamadas if x["proposito"] == "redactar"][-1]
    return json.loads(ultima["usuario"].split("ESTADO COMUNICABLE:\n", 1)[1])


def test_b3_fuera_de_alcance_busca_por_la_categoria_y_no_por_una_palabra_suelta_del_mensaje():
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    m = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: fuera_de_alcance | aumento de cupo de tarjeta"]))
    procesar("c_" + secrets.token_hex(6), Entrada(texto="súbanme el cupo de la tarjeta"), token, m)
    hechos = _estado_comunicable(m)
    citados = [e["articulo"] for e in hechos if e["clase"] == "RESPONDER"]
    assert not any(a.startswith("publico.nunca-te-pedimos-tu-clave") for a in citados)     # antes citaba este por la palabra "tarjeta"
    assert "fuera_de_alcance" in {e.get("hecho") for e in hechos}


def test_b4_fuera_de_alcance_con_categoria_clave_encuentra_el_articulo_de_la_clave():
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    m = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: fuera_de_alcance | clave"]))
    procesar("c_" + secrets.token_hex(6), Entrada(texto="se me olvidó la clave, cámbienmela"), token, m)
    assert any(e["clase"] == "RESPONDER" and e["articulo"].startswith("publico.cambiar-o-recuperar-tu-clave") for e in _estado_comunicable(m))


def test_b3_con_tema_del_catalogo_si_responde_con_ese_articulo():
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    m = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: fuera_de_alcance | cupo\nCOMANDO: consulta_informativa | publico.otras-gestiones"]))
    procesar("c_" + secrets.token_hex(6), Entrada(texto="súbanme el cupo de la tarjeta"), token, m)
    assert any(e["clase"] == "RESPONDER" and e["articulo"].startswith("publico.otras-gestiones") for e in _estado_comunicable(m))


def test_b10_pedir_una_persona_y_preguntar_en_el_mismo_mensaje_responde_y_traspasa():
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    m = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: pedir_persona\nCOMANDO: consulta_informativa | publico.si-llamas-por-otra-persona"]))
    s = procesar("c_" + secrets.token_hex(6), Entrada(texto="llamo por mi mamá, que no puede escribir"), token, m)
    hechos = _estado_comunicable(m)
    assert s.nodo == "N11" or s.traspaso                                           # pasó a una persona
    assert any(e["clase"] == "RESPONDER" and e["articulo"].startswith("publico.si-llamas-por-otra-persona") for e in hechos)


def test_la_respuesta_con_un_articulo_entrega_su_fuente_para_mostrarla():
    """5-oct (Daniel): cuando una respuesta sale de un documento del banco, el cliente ve de cuál."""
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    m = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: fuera_de_alcance | cupo\nCOMANDO: consulta_informativa | publico.otras-gestiones"]))
    s = procesar("c_" + secrets.token_hex(6), Entrada(texto="súbanme el cupo de la tarjeta"), token, m)
    fuente = next(u for u in s.ui if u["tipo"] == "fuente")
    assert fuente["id"] == "publico.otras-gestiones" and fuente["titulo"] and fuente["version"]

