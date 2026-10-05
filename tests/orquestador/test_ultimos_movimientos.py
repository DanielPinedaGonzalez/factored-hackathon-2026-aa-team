"""«No me acuerdo» / «yo no lo hice»: antes de pensar en robo, el cliente ve sus últimos movimientos en lenguaje natural.

Origen (traza real): «ayer me cobraron algo pero no me acuerdo» terminó en una propuesta de bloquear la tarjeta y fraude prioridad 1 sin
mostrarle un solo movimiento. Un cliente que no recuerda suele acordarse al verlos; bloquear o escalar por una falsa alarma le complica la vida.
El flujo: (1) no recuerda → (2) se le muestran sus últimos movimientos → (3) «ya me acordé» cierra con amabilidad → (4) solo si ninguno es suyo
se sigue; y si tampoco da con el cargo después de dar sus datos, lo atiende una persona (nunca otra vuelta)."""
import pytest

from servicio.llm.cliente import ModeloFalso
from servicio.orquestador.orquestador import Entrada, procesar
from tests.apoyo import Guion, admin
from tests.orquestador.test_caminos import conv, iniciar_con_sesion, sesion

pytestmark = pytest.mark.db

SIN_DATOS = "IDIOMA: es\nCOMANDO: iniciar | disputas.reportar_cargo\nRECONOCE: no_seguro\nCARGO: nuevo\nFIN_CARGO"
MONTO_QUE_NO_EXISTE = "IDIOMA: es\nCOMANDO: iniciar | disputas.reportar_cargo\nCARGO: nuevo\nMONTO: 123456789\nMONEDA: USD\nFIN_CARGO"
UN_SOLO_ALIAS = lambda opciones: "COINCIDEN: " + next(iter(opciones))


def _opciones(s):
    return next(u for u in s.ui if u["tipo"] == "opciones")


def _hasta_los_ultimos(guion):
    token, cid = sesion("DEMO-1001")
    c = conv()
    m = ModeloFalso(Guion(guion, comparar=UN_SOLO_ALIAS))
    iniciar_con_sesion(c, token, m)
    s = procesar(c, Entrada(texto="me cobraron algo pero no me acuerdo qué fue"), token, m)
    return token, cid, c, m, s


def test_sin_datos_se_muestran_los_ultimos_movimientos_con_ninguno_de_estos():
    _, cid, _, _, s = _hasta_los_ultimos([SIN_DATOS])
    o = _opciones(s)
    assert s.nodo == "N4" and 1 <= len(o["opciones"]) <= 5 and o["ninguno"] is True
    assert all(x["fecha"] and x["monto"] and x["movimiento"] for x in o["opciones"])      # en palabras del cliente, no códigos
    assert not any(u["tipo"] == "confirmacion" for u in s.ui)                           # nada se propone antes de que reconozca uno
    with admin() as a:
        assert a.execute("select count(*) from atencion.bloqueos where customer_id = %s", (cid,)).fetchone()[0] == 0


def test_ya_me_acorde_cierra_sin_reclamo_ni_bloqueo():
    token, cid, c, m, s = _hasta_los_ultimos([SIN_DATOS])
    s = procesar(c, Entrada(evento={"tipo": "elegir", "alias": _opciones(s)["opciones"][0]["alias"]}), token, m)
    assert s.nodo == "N5"
    s = procesar(c, Entrada(evento={"tipo": "reconoce", "valor": "si"}), token, m)
    assert s.nodo == "N12"
    with admin() as a:
        assert a.execute("select count(*) from atencion.reclamos where customer_id = %s", (cid,)).fetchone()[0] == 0
        assert a.execute("select count(*) from atencion.bloqueos where customer_id = %s", (cid,)).fetchone()[0] == 0


def test_ninguno_pide_datos_y_si_con_ellos_tampoco_aparece_pasa_a_una_persona():
    token, cid, c, m, s = _hasta_los_ultimos([SIN_DATOS, MONTO_QUE_NO_EXISTE])
    s = procesar(c, Entrada(evento={"tipo": "elegir", "alias": "ninguno"}), token, m)
    assert s.nodo == "N4" and not any(u["tipo"] == "opciones" for u in s.ui)            # pide monto, fecha o descripción; no repite la lista
    s = procesar(c, Entrada(texto="fue de un monto enorme"), token, m)
    assert s.nodo == "N11" and not any(u["tipo"] == "opciones" for u in s.ui)           # una persona, no otra vuelta


def test_ninguno_dos_veces_pasa_a_una_persona():
    token, cid, c, m, s = _hasta_los_ultimos([SIN_DATOS])
    procesar(c, Entrada(evento={"tipo": "elegir", "alias": "ninguno"}), token, m)
    s = procesar(c, Entrada(evento={"tipo": "elegir", "alias": "ninguno"}), token, m)       # sin opciones mostradas: no hay nada que descartar
    assert s.nodo != "N7"


def test_si_habla_de_hoy_no_se_le_muestran_otros_movimientos():
    """E4, hallado con el puente: «un cargo de hoy en la mañana» no tiene registro porque los cargos del día pueden no estar cargados todavía. Mostrarle los
    últimos movimientos lo empuja a elegir uno que no es y dar por existente un cargo equivocado: se pide el dato, como antes."""
    hoy = "IDIOMA: es\nCOMANDO: iniciar | disputas.reportar_cargo\nRECONOCE: no\nCARGO: nuevo\nCUANDO: relativa hoy\nFIN_CARGO"
    token, cid = sesion("DEMO-1001")
    c = conv()
    m = ModeloFalso(Guion([hoy], comparar=UN_SOLO_ALIAS))
    iniciar_con_sesion(c, token, m)
    s = procesar(c, Entrada(texto="no reconozco un cargo que me hicieron hoy en la mañana"), token, m)
    assert s.nodo == "N4" and not any(u["tipo"] in ("opciones", "tarjeta_cargo", "confirmacion") for u in s.ui)
