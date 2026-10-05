"""Nada se propone sobre un cargo que el cliente no ha visto, y una confirmación por texto no se ejecuta si trae algo más.

Hallado en la demo, dos veces con la traza a mano:
1. "no sé dónde salió ese pago de ayer" / "no me acuerdo… compré un televisor": el Intérprete leyó RECONOCE: no (el catálogo tiene
   `no_seguro` para eso) y un atajo del código mostraba el cargo y proponía abrir un reclamo en el mismo turno. Ahora el cargo se
   muestra siempre y es el cliente quien dice si lo reconoce (N5).
2. "listo, ese es bueno, chao" se leyó como `confirmar` + `charla` y abrió el reclamo R-000441, que el cliente no quería. Ahora una
   acción con efectos se ejecuta por texto solo si el Intérprete leyó únicamente una confirmación; si no, se recuerda lo pendiente."""
import pytest

from servicio.llm.cliente import ModeloFalso
from servicio.orquestador.orquestador import Entrada, procesar
from tests.apoyo import Guion, admin
from tests.orquestador.test_caminos import conv, iniciar_con_sesion, sesion

pytestmark = pytest.mark.db

SOLO_DESCRIPCION = "IDIOMA: es\nCOMANDO: iniciar | disputas.reportar_cargo\nRECONOCE: no\nCARGO: nuevo\nDESCRIPCION: una compra\nFIN_CARGO"
CON_FECHA = "IDIOMA: es\nCOMANDO: iniciar | disputas.reportar_cargo\nRECONOCE: no\nCARGO: nuevo\nCUANDO: relativa ayer\nDESCRIPCION: una compra\nFIN_CARGO"
UN_SOLO_ALIAS = lambda opciones: "COINCIDEN: " + next(iter(opciones))          # el Comparador deja un único candidato


def _tipos(s):
    return [u["tipo"] for u in s.ui]


def _reclamos(cid):
    with admin() as a:
        return a.execute("select count(*) from atencion.reclamos where customer_id = %s", (cid,)).fetchone()[0]


@pytest.mark.parametrize("interpretacion", [SOLO_DESCRIPCION, CON_FECHA])
def test_aunque_diga_que_no_reconoce_primero_se_muestra_el_cargo_y_se_pregunta(interpretacion):
    token, cid = sesion("DEMO-1001")
    c = conv()
    m = ModeloFalso(Guion([interpretacion], comparar=UN_SOLO_ALIAS))
    iniciar_con_sesion(c, token, m)
    s = procesar(c, Entrada(texto="no sé de dónde salió ese pago"), token, m)
    if s.nodo == "N4":                                       # varios movimientos ese día: elige uno
        s = procesar(c, Entrada(evento={"tipo": "elegir", "alias": s.ui[-1]["opciones"][0]["alias"]}), token, m)
    assert s.nodo == "N5" and "tarjeta_cargo" in _tipos(s)
    assert "confirmacion" not in _tipos(s)                  # ninguna propuesta de reclamo antes de que lo vea y responda
    s = procesar(c, Entrada(evento={"tipo": "reconoce", "valor": "no"}), token, m)
    assert s.nodo == "N7" and "confirmacion" in _tipos(s)   # solo ahora, con su respuesta, se propone


def _hasta_la_propuesta(m):
    token, cid = sesion("DEMO-1001")
    c = conv()
    iniciar_con_sesion(c, token, m)
    s = procesar(c, Entrada(texto="no reconozco un cargo de ayer"), token, m)
    if s.nodo == "N4":
        s = procesar(c, Entrada(evento={"tipo": "elegir", "alias": s.ui[-1]["opciones"][0]["alias"]}), token, m)
    procesar(c, Entrada(evento={"tipo": "reconoce", "valor": "no"}), token, m)
    return token, cid, c


def test_una_confirmacion_con_algo_mas_no_abre_el_reclamo():
    m = ModeloFalso(Guion([CON_FECHA, "IDIOMA: es\nCOMANDO: confirmar\nCOMANDO: charla\nBORRADOR: Listo."], comparar=UN_SOLO_ALIAS))
    token, cid, c = _hasta_la_propuesta(m)
    s = procesar(c, Entrada(texto="a listo, ese es bueno, chao"), token, m)
    assert _reclamos(cid) == 0 and s.nodo == "N7"            # sigue pendiente: nada se ejecutó


def test_una_confirmacion_sola_si_abre_el_reclamo():
    m = ModeloFalso(Guion([CON_FECHA, "IDIOMA: es\nCOMANDO: confirmar"], comparar=UN_SOLO_ALIAS))
    token, cid, c = _hasta_la_propuesta(m)
    s = procesar(c, Entrada(texto="sí, ábrelo"), token, m)
    assert _reclamos(cid) == 1 and s.nodo == "N10"


def test_si_el_cliente_ya_dijo_ayer_el_sistema_busca_y_no_vuelve_a_preguntar_la_fecha():
    """Hallado en la demo: «ayer me cobraron algo pero no me acuerdo» (dicho dos veces) terminó en «¿podrías indicarme el monto, la fecha y una descripción?»:
    el Intérprete dio la fecha como campo suelto (`dar_dato | cuando | ayer`) y se descartaba sin avisar."""
    token, cid = sesion("DEMO-1001")                       # tiene un movimiento «de ayer» en los datos
    c = conv()
    m = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: iniciar | movimientos.consultar\nCOMANDO: dar_dato | cuando | ayer"], comparar=UN_SOLO_ALIAS))
    iniciar_con_sesion(c, token, m)
    s = procesar(c, Entrada(texto="ayer me cobraron algo pero no me acuerdo"), token, m)
    assert s.nodo == "N5" and "tarjeta_cargo" in _tipos(s)       # buscó, encontró el cargo de ayer y se lo muestra para que diga si lo reconoce
