"""Cuando el modelo responde pero su salida no se puede leer (dos veces), no es una caída: se le pide al cliente que lo diga de otra forma.
Si el mensaje siguiente tampoco se entiende, pasa a una persona. Si el modelo no está disponible, pasa a una persona como siempre."""
import json
import secrets

import pytest

from servicio.llm.cliente import ModeloFalso, ModeloNoDisponible
from servicio.orquestador.orquestador import Entrada, procesar
from tests.apoyo import Guion, limpiar_cliente, token_de

pytestmark = pytest.mark.db

ILEGIBLE = "NOTA: esto no es el formato"
BIEN = "IDIOMA: es\nCOMANDO: fuera_de_alcance | cerveza"


def _hechos(m: ModeloFalso) -> str:
    ultima = [x for x in m.llamadas if x["proposito"] == "redactar"][-1]
    return ultima["usuario"].split("ESTADO COMUNICABLE:\n", 1)[1]


def test_el_primer_mensaje_ilegible_se_repregunta_y_no_pasa_a_una_persona():
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    m = ModeloFalso(Guion([ILEGIBLE, ILEGIBLE]))                     # el Intérprete falla dos veces (la corrección también)
    s = procesar("c_" + secrets.token_hex(6), Entrada(texto="ahace unsoo dias me llegi un conrro"), token, m)
    assert not s.sin_modelo and not s.traspaso
    assert "no_se_entendio" in _hechos(m)                              # el redactor recibe la pregunta, el texto lo escribe el modelo


def test_el_segundo_mensaje_ilegible_seguido_pasa_a_una_persona():
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    conv = "c_" + secrets.token_hex(6)
    m = ModeloFalso(Guion([ILEGIBLE, ILEGIBLE, ILEGIBLE, ILEGIBLE]))
    procesar(conv, Entrada(texto="ahace unsoo dias"), token, m)
    s = procesar(conv, Entrada(texto="un conrro que no ice"), token, m)
    assert s.sin_modelo and s.traspaso


def test_entender_un_mensaje_reinicia_la_cuenta():
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    conv = "c_" + secrets.token_hex(6)
    m = ModeloFalso(Guion([ILEGIBLE, ILEGIBLE, BIEN, ILEGIBLE, ILEGIBLE]))
    procesar(conv, Entrada(texto="uno"), token, m)                     # se repregunta
    procesar(conv, Entrada(texto="quiero una cerveza"), token, m)      # se entiende: la cuenta vuelve a cero
    s = procesar(conv, Entrada(texto="otro ilegible"), token, m)       # de nuevo se repregunta, no pasa a una persona
    assert not s.sin_modelo and not s.traspaso
