"""El idioma de la conversación (ARQUITECTURA §8.5): lo entiende el modelo, lo guarda y lo decide el código.

El Intérprete declara el idioma del MENSAJE; el cliente pide uno con el selector ES/PT de la interfaz (evento
`cambiar_idioma`, que no pasa por el modelo); el código fija el idioma y el Redactor escribe en él con los hechos del turno.
Se probó un comando `pedir_idioma` para el Intérprete y bajó su detección de inyecciones de 20/20 a 11/20 en B6
(`evaluacion/EXPERIMENTOS.md`, E-02): por eso lo que ve el Intérprete se mantiene como estaba y las pruebas de abajo lo vigilan.
"""
import re
import secrets
from pathlib import Path

import pytest

from contratos import catalogo
from contratos.modelos import EstadoConversacion
from servicio.interprete.interprete import estado_para_modelo
from servicio.llm.cliente import ModeloFalso
from servicio.orquestador.orquestador import MIN_CARACTERES_PARA_CAMBIAR_IDIOMA, Entrada, procesar
from tests.apoyo import admin, limpiar_cliente, redactor_falso, token_de

RAIZ = Path(__file__).resolve().parents[2]
CHARLA_ES = "IDIOMA: es\nCOMANDO: charla\nBORRADOR: Hola."


def _modelo(interpretaciones: list[str]) -> ModeloFalso:
    """Intérprete en orden; Redactor y Comparador falsos que escriben en el idioma que el sistema les pidió."""
    cola = list(interpretaciones)

    def guion(sistema, usuario, proposito):
        if proposito == "interpretar":
            return cola.pop(0)
        idioma = re.search(r"^IDIOMA: (es|pt)", usuario, re.M)
        if proposito == "comparar":
            return "COINCIDEN: ninguna"
        return redactor_falso(usuario, idioma.group(1) if idioma else "es")
    return ModeloFalso(guion)


def _idioma_pedido_al_redactor(m: ModeloFalso) -> str:
    ultima = [x for x in m.llamadas if x["proposito"] == "redactar"][-1]
    return re.search(r"^IDIOMA: (es|pt)", ultima["usuario"], re.M).group(1)


def _hechos_del_ultimo_turno(m: ModeloFalso) -> list[str]:
    import json
    ultima = [x for x in m.llamadas if x["proposito"] == "redactar"][-1]
    return [e.get("hecho") or e.get("pregunta") for e in json.loads(ultima["usuario"].split("ESTADO COMUNICABLE:\n", 1)[1])]


def _idioma_guardado(conversation_id: str) -> str:
    with admin() as c:
        return c.execute("select idioma from atencion.conversaciones where conversation_id = %s", (conversation_id,)).fetchone()[0]


def _conversacion(monkeypatch):
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    return token, "c_" + secrets.token_hex(6)


# ---------- Lo que ve el Intérprete: se mantiene como estaba (sin base de datos) ----------

def test_el_interprete_ve_lo_mismo_que_cuando_se_midio_su_deteccion_de_inyecciones():
    assert set(estado_para_modelo(EstadoConversacion(conversation_id="c"))) == {
        "nodo", "ultima_pregunta", "cargos", "opciones_mostradas", "accion_propuesta", "datos_dados", "temas_pendientes",
        "identidad_verificada"}, "agregar algo al estado del Intérprete exige volver a medir B6 (E-02)"
    assert "pedir_idioma" not in catalogo.cargar()["comandos"]
    assert "pedir_idioma" not in (RAIZ / "prompts" / "interprete.md").read_text(encoding="utf-8")


# ---------- Lo que decide el código (con base de datos) ----------

@pytest.mark.db
def test_el_selector_cambia_la_conversacion_y_el_redactor_escribe_en_ese_idioma(monkeypatch):
    token, c = _conversacion(monkeypatch)
    m = _modelo([CHARLA_ES])
    procesar(c, Entrada(texto="hola"), token, m)
    assert _idioma_guardado(c) == "es"
    procesar(c, Entrada(evento={"tipo": "cambiar_idioma", "idioma": "pt"}), token, m)
    assert _idioma_guardado(c) == "pt" and _idioma_pedido_al_redactor(m) == "pt" and "idioma_cambiado" in _hechos_del_ultimo_turno(m)
    procesar(c, Entrada(evento={"tipo": "cambiar_idioma", "idioma": "es"}), token, m)
    assert _idioma_guardado(c) == "es" and _idioma_pedido_al_redactor(m) == "es"


@pytest.mark.db
def test_lo_pedido_se_mantiene_aunque_el_modelo_detecte_otro_idioma_en_un_mensaje_largo(monkeypatch):
    token, c = _conversacion(monkeypatch)
    m = _modelo([CHARLA_ES, "IDIOMA: es\nCOMANDO: consulta_informativa | publico.hablar-con-una-persona"])
    procesar(c, Entrada(texto="hola"), token, m)
    procesar(c, Entrada(evento={"tipo": "cambiar_idioma", "idioma": "pt"}), token, m)
    procesar(c, Entrada(texto="quiero saber cómo hablo con una persona del banco"), token, m)   # escrito en español, pidió portugués
    assert _idioma_guardado(c) == "pt" and _idioma_pedido_al_redactor(m) == "pt"


@pytest.mark.db
def test_un_idioma_no_soportado_pedido_no_cambia_la_conversacion(monkeypatch):
    token, c = _conversacion(monkeypatch)
    m = _modelo([CHARLA_ES])
    procesar(c, Entrada(texto="hola"), token, m)
    procesar(c, Entrada(evento={"tipo": "cambiar_idioma", "idioma": "en"}), token, m)
    assert _idioma_guardado(c) == "es" and "idioma_no_soportado" in _hechos_del_ultimo_turno(m)


@pytest.mark.db
def test_pedir_el_idioma_a_mitad_de_un_tramite_conserva_lo_pendiente(monkeypatch):
    token, c = _conversacion(monkeypatch)
    m = _modelo(["IDIOMA: es\nCOMANDO: iniciar | disputas.reportar_cargo\nRECONOCE: no\nTIPO_DISPUTA: no_autorizada\n"
                 "EVIDENCIA_TIPO: no lo hice\nCARGO: nuevo\nCUANDO: relativa ayer\nFIN_CARGO"])
    procesar(c, Entrada(texto="no reconozco un cargo de ayer"), token, m)
    antes = procesar(c, Entrada(evento={"tipo": "reconoce", "valor": "no"}), token, m)              # ve el cargo y dice que no lo reconoce
    despues = procesar(c, Entrada(evento={"tipo": "cambiar_idioma", "idioma": "pt"}), token, m)
    assert antes.nodo == despues.nodo and any(u["tipo"] == "confirmacion" for u in antes.ui)    # sigue donde estaba
    assert {"idioma_cambiado", "pendiente_recordado"} <= set(_hechos_del_ultimo_turno(m)) and _idioma_guardado(c) == "pt"


@pytest.mark.db
def test_el_primer_mensaje_fija_el_idioma_sea_cual_sea_su_largo(monkeypatch):
    token, c = _conversacion(monkeypatch)
    m = _modelo(["IDIOMA: pt\nCOMANDO: charla\nBORRADOR: Oi."])
    procesar(c, Entrada(texto="oi"), token, m)
    assert len("oi") < MIN_CARACTERES_PARA_CAMBIAR_IDIOMA and _idioma_guardado(c) == "pt"


@pytest.mark.db
def test_un_mensaje_corto_no_voltea_la_conversacion_pero_uno_con_texto_si(monkeypatch):
    token, c = _conversacion(monkeypatch)
    m = _modelo([CHARLA_ES, "IDIOMA: pt\nCOMANDO: consulta_informativa | publico.hablar-con-una-persona",
                 "IDIOMA: pt\nCOMANDO: consulta_informativa | publico.hablar-con-una-persona"])
    procesar(c, Entrada(texto="hola"), token, m)
    procesar(c, Entrada(texto="não"), token, m)                                   # corto: ni el "no" en portugués ni un "ok" la voltean
    assert _idioma_guardado(c) == "es"
    procesar(c, Entrada(texto="quero falar com uma pessoa do banco, por favor"), token, m)
    assert _idioma_guardado(c) == "pt"
