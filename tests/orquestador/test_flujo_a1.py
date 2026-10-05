"""Rebanada vertical: identidad → cargo → hechos → política → confirmación → herramienta → verificación."""
import secrets

import pytest

from servicio.llm.cliente import ModeloFalso
from servicio.orquestador.orquestador import Entrada, procesar
from tests.apoyo import Guion, admin, limpiar_cliente, token_de

pytestmark = pytest.mark.db

A1 = """IDIOMA: es
COMANDO: iniciar | disputas.reportar_cargo
RECONOCE: no
TIPO_DISPUTA: no_autorizada
CARGO: nuevo
CUANDO: relativa ayer
FIN_CARGO
BORRADOR: Te ayudo con eso."""


def test_reportar_cargo_de_punta_a_punta(monkeypatch):
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    conv = "c_" + secrets.token_hex(6)
    m = ModeloFalso(Guion([A1]))
    s1 = procesar(conv, Entrada(texto="me salió un cobro raro ayer, yo no hice eso"), None, m)
    assert s1.nodo == "N1" and any(u["tipo"] == "formulario_identidad" for u in s1.ui)
    assert s1.texto.startswith("Saludo de prueba.\nSoy Lora")   # saludo del Redactor + divulgación LITERAL del primer turno
    s2 = procesar(conv, Entrada(evento={"tipo": "identidad_verificada"}), token, m)
    assert s2.nodo in ("N5", "N4")
    if s2.nodo == "N4":
        alias = next(u for u in s2.ui if u["tipo"] == "opciones")["opciones"][0]["alias"]
        s2 = procesar(conv, Entrada(evento={"tipo": "elegir", "alias": alias}), token, m)
    # aunque ya dijo "yo no hice eso", primero ve el cargo y es él quien dice que no lo reconoce; solo entonces se propone
    assert any(u["tipo"] == "tarjeta_cargo" for u in s2.ui) and not any(u["tipo"] == "confirmacion" for u in s2.ui)
    s3 = procesar(conv, Entrada(evento={"tipo": "reconoce", "valor": "no"}), token, m)
    conf = next(u for u in s3.ui if u["tipo"] == "confirmacion")
    assert s3.nodo == "N7" and conf["accion"] == "abrir_reclamo"
    s4 = procesar(conv, Entrada(evento={"tipo": "confirmar", "action_intent_id": conf["action_intent_id"]}), token, m)
    caso = next(u for u in s4.ui if u["tipo"] == "estado_caso")
    assert s4.nodo == "N10" and caso["numero"] in s4.texto
    with admin() as c:
        n = c.execute("select count(*) from atencion.reclamos where customer_id = %s and estado = 'abierto'", (cid,)).fetchone()[0]
        ev = c.execute("select count(*) from atencion.reclamo_eventos where customer_id = %s", (cid,)).fetchone()[0]
        reg = c.execute("select count(*) from operacion.registro_turnos where conversation_id = %s", (conv,)).fetchone()[0]
    assert n == 1 and ev == 1 and reg >= 3
    # La misma confirmación reenviada no abre otro reclamo (idempotencia)
    procesar(conv, Entrada(evento={"tipo": "confirmar", "action_intent_id": conf["action_intent_id"]}), token, m)
    with admin() as c:
        assert c.execute("select count(*) from atencion.reclamos where customer_id = %s", (cid,)).fetchone()[0] == 1
    # Si después pide una persona, el paquete lleva lo hecho en turnos anteriores y el cargo legible (R5)
    procesar(conv, Entrada(evento={"tipo": "pedir_persona"}), token, m)
    with admin() as c:
        paquete = c.execute("select paquete from atencion.traspasos where conversation_id = %s", (conv,)).fetchone()[0]
    assert [(a["accion"], a["resultado"]["numero"]) for a in paquete["acciones_realizadas"]] == [("abrir_reclamo", caso["numero"])]
    assert all(h.get("movimiento") and h.get("monto") and h.get("fecha") for h in paquete["hechos_verificados"])


def test_en_vivo_el_cargo_de_ayer_se_muestra_con_la_fecha_real_del_cliente(monkeypatch):
    """La conversación en vivo usa el reloj de la persona: el cargo del día anterior al corte de los datos es ayer."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from servicio.redactor import formato
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    conv = "c_" + secrets.token_hex(6)
    s = procesar(conv, Entrada(texto="me salió un cobro raro ayer"), token, ModeloFalso(Guion([A1])))
    if s.nodo == "N4":
        alias = next(u for u in s.ui if u["tipo"] == "opciones")["opciones"][0]["alias"]
        s = procesar(conv, Entrada(evento={"tipo": "elegir", "alias": alias}), token, ModeloFalso(Guion([A1])))
    tarjeta = next(u for u in s.ui if u["tipo"] == "tarjeta_cargo")
    ayer = datetime.now(ZoneInfo("America/Mexico_City")).date() - timedelta(days=1)
    assert tarjeta["fecha"] == formato.fecha(ayer, "es")
