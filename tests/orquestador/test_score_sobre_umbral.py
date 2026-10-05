"""El camino para el que existe M1, de punta a punta: el cliente no reconoce un cargo cuyo score supera el umbral certificado.

Hasta aquí M1 solo tenía pruebas de unidad (`test_senal`, `test_motor`) y ningún caso de evaluación usaba un cargo sobre el
umbral (los 62 son `senal: bajo`). DEMO-1007 tiene un cargo de ayer con score 59,82 > 30 (`pipeline/seleccion.py`).

Lo que se afirma, con el Intérprete guionizado (lo que decide el código, no el modelo):
1. el cargo se muestra y el cliente dice que no lo reconoce;
2. la política ve el score sobre el umbral certificado y recomienda proteger: propone bloquear el producto del cargo, no abrir un reclamo;
3. nada se bloquea hasta que el cliente confirma (INV-CONFIRMA);
4. al confirmar, el producto queda bloqueado y el caso pasa a Fraude con prioridad 1;
5. el asesor recibe la evidencia (score calibrado, cota de falsas alarmas, versión de M1) y el cliente nunca ve el score."""
import json

import pytest

from servicio.llm.cliente import ModeloFalso
from servicio.orquestador.orquestador import Entrada, procesar
from servicio.riesgo import senal
from tests.apoyo import Guion, admin
from tests.orquestador.test_caminos import conv, iniciar_con_sesion, sesion

pytestmark = pytest.mark.db

NO_RECONOCE_AYER = "IDIOMA: es\nCOMANDO: iniciar | disputas.reportar_cargo\nRECONOCE: no\nCARGO: nuevo\nCUANDO: relativa ayer\nFIN_CARGO"
UN_SOLO_ALIAS = lambda opciones: "COINCIDEN: " + next(iter(opciones))


def _tipos(s):
    return [u["tipo"] for u in s.ui]


def _hasta_el_no_reconoce():
    token, cid = sesion("DEMO-1007")
    c = conv()
    m = ModeloFalso(Guion([NO_RECONOCE_AYER], comparar=UN_SOLO_ALIAS))
    iniciar_con_sesion(c, token, m)
    s = procesar(c, Entrada(texto="no reconozco un cargo de ayer"), token, m)
    if s.nodo == "N4":
        s = procesar(c, Entrada(evento={"tipo": "elegir", "alias": s.ui[-1]["opciones"][0]["alias"]}), token, m)
    assert s.nodo == "N5" and "tarjeta_cargo" in _tipos(s) and "confirmacion" not in _tipos(s)
    return token, cid, c, m


def test_el_cargo_de_demo_1007_supera_el_umbral_certificado():
    with admin() as a:
        score = a.execute("select max(fraud_score) from servicio.transacciones where customer_id = "
                          "(select customer_id from atencion.identidades_demo where documento_demo = 'DEMO-1007')").fetchone()[0]
    s = senal.evaluar(float(score))
    assert s.supera_umbral_certificado and s.p == 1.0 and s.cota_fdr is not None


def test_score_sobre_el_umbral_propone_bloquear_y_nada_se_bloquea_sin_confirmar():
    token, cid, c, m = _hasta_el_no_reconoce()
    s = procesar(c, Entrada(evento={"tipo": "reconoce", "valor": "no"}), token, m)
    conf = next(u for u in s.ui if u["tipo"] == "confirmacion")
    assert s.nodo == "N7" and conf["accion"] == "bloquear_producto"          # proteger primero, no un reclamo
    with admin() as a:
        assert a.execute("select count(*) from atencion.bloqueos where customer_id = %s", (cid,)).fetchone()[0] == 0
        assert a.execute("select count(*) from atencion.reclamos where customer_id = %s", (cid,)).fetchone()[0] == 0


def test_confirmar_bloquea_y_pasa_a_fraude_prioridad_1_con_la_evidencia_de_m1():
    token, cid, c, m = _hasta_el_no_reconoce()
    s = procesar(c, Entrada(evento={"tipo": "reconoce", "valor": "no"}), token, m)
    conf = next(u for u in s.ui if u["tipo"] == "confirmacion")
    s = procesar(c, Entrada(evento={"tipo": "confirmar", "action_intent_id": conf["action_intent_id"]}), token, m)
    assert s.nodo == "N11" and s.traspaso["habilidad"] == "fraude" and s.traspaso["prioridad"] == 1
    with admin() as a:
        assert a.execute("select count(*) from atencion.bloqueos where customer_id = %s and estado = 'bloqueado_temporal'", (cid,)).fetchone()[0] == 1
        paquete = a.execute("select paquete from atencion.traspasos where customer_id = %s", (cid,)).fetchone()[0]
    assert "bloqueo_recomendado_por_riesgo" in paquete["motivo_traspaso"]
    assert paquete["evidencia"]["senal"]["supera_umbral_certificado"] is True
    assert paquete["evidencia"]["senal"]["version_m1"] == senal.artefacto()["version"]
    visto_por_el_cliente = json.dumps([t for t in s.ui] + [getattr(s, "texto", "")], default=str)
    assert "fraud_score" not in visto_por_el_cliente and "59.82" not in visto_por_el_cliente


# ---- «sí lo reconozco» con score sobre el umbral: se cierra igual, pero queda una marca de auditoría que el cliente nunca ve

def _marcas(conversation_id):
    with admin() as a:
        return a.execute("""select p->'detalle'->>'marca' from operacion.registro_turnos r, jsonb_array_elements(r.registro->'pasos') p
                            where r.conversation_id = %s and p->'detalle' ? 'marca'""", (conversation_id,)).fetchall()


def test_reconocer_un_cargo_sobre_el_umbral_cierra_igual_y_deja_una_marca_que_el_cliente_no_ve():
    token, cid, c, m = _hasta_el_no_reconoce()
    s = procesar(c, Entrada(evento={"tipo": "reconoce", "valor": "si"}), token, m)
    assert s.nodo == "N12"                                                   # misma conversación para el cliente: cierra y ofrece reclamar
    assert not any(u["tipo"] in ("confirmacion", "opciones") for u in s.ui)
    assert [f[0] for f in _marcas(c)] == ["reconocido_con_senal_sobre_umbral"]
    visto = json.dumps(s.ui, default=str) + s.texto
    assert "umbral" not in visto.lower() and "riesgo" not in visto.lower() and "score" not in visto.lower()
    with admin() as a:
        assert a.execute("select count(*) from atencion.bloqueos where customer_id = %s", (cid,)).fetchone()[0] == 0
        assert a.execute("select count(*) from atencion.traspasos where customer_id = %s and conversation_id = %s", (cid, c)).fetchone()[0] == 0


def test_reconocer_un_cargo_bajo_el_umbral_no_deja_marca():
    token, cid = sesion("DEMO-1001")
    c = conv()
    m = ModeloFalso(Guion([NO_RECONOCE_AYER], comparar=UN_SOLO_ALIAS))
    iniciar_con_sesion(c, token, m)
    s = procesar(c, Entrada(texto="no reconozco un cargo de ayer"), token, m)
    if s.nodo == "N4":
        s = procesar(c, Entrada(evento={"tipo": "elegir", "alias": s.ui[-1]["opciones"][0]["alias"]}), token, m)
    s = procesar(c, Entrada(evento={"tipo": "reconoce", "valor": "si"}), token, m)
    assert s.nodo == "N12" and _marcas(c) == []
