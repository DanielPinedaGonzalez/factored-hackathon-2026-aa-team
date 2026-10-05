"""Lo que el sistema no sabe o no puede, lo dice y ofrece una persona; y no hace repetir lo que el cliente ya dijo.

Origen: el caso de una clienta cuyo desembolso de crédito le cobraron pero nunca llegó a su saldo. Lora solo ve y reclama cargos: un desembolso es
otra gestión. Antes terminaba en «fuera de alcance» con un artículo y sin ofrecer una persona, o volvía a pedir el monto y la descripción que ya
había dado. Principio: detectar lo que no se sabe, decirlo con honestidad, ofrecer una persona y no inventar ni asumir."""
import json

import pytest

from servicio.llm.cliente import ModeloFalso
from servicio.orquestador.orquestador import Entrada, procesar
from tests.apoyo import redactor_falso
from tests.orquestador.test_caminos import conv, iniciar_con_sesion, sesion

pytestmark = pytest.mark.db

MSG = "Hola, tengo problemas con un desembolso de 500 mil pesos en septiembre de un crédito que lo amplié"


def _correr(lectura, mensaje=MSG):
    visto = {}

    def guion(sistema, usuario, proposito):
        if proposito == "interpretar":
            return lectura
        if proposito == "comparar":
            bloque = usuario.split("<<<OPCIONES\n", 1)[1].split("\nOPCIONES>>>", 1)[0]
            return "COINCIDEN: " + ", ".join(dict(l.split(": ", 1) for l in bloque.splitlines()))
        visto["estado"] = json.loads(usuario.split("ESTADO COMUNICABLE:\n", 1)[1])
        return redactor_falso(usuario)

    token, _ = sesion("DEMO-1001")
    c, m = conv(), ModeloFalso(guion)
    iniciar_con_sesion(c, token, m)
    s = procesar(c, Entrada(texto=mensaje), token, m)
    return s, visto["estado"]


def test_fuera_de_alcance_nunca_es_un_callejon_sin_salida_ni_escala_solo():
    """Dice que es otra gestión y, o responde con un artículo (cuya suficiencia declara el Redactor, que si no alcanza ofrece una persona), o
    ofrece una persona. No se ofrece una persona de más cuando el artículo responde, y no escala por su cuenta (B3 y P2 piden no escalar)."""
    s, estado = _correr("IDIOMA: es\nCOMANDO: fuera_de_alcance | credito")
    hechos = [e.get("hecho") for e in estado]; clases = [e.get("clase") for e in estado]
    assert "fuera_de_alcance" in hechos and ("RESPONDER" in clases or "persona_disponible" in hechos)
    assert s.traspaso is None


def test_datos_que_faltan_nunca_incluye_lo_que_el_cliente_ya_dijo():
    from contratos.modelos import CargoReferido, Cuando
    from servicio.orquestador.grafo import _datos_que_faltan
    nada = CargoReferido()
    assert _datos_que_faltan(nada) == ["monto", "cuando", "descripcion"]
    solo_fecha = CargoReferido(cuando=Cuando(tipo="relativa", valor="hoy"))
    assert _datos_que_faltan(solo_fecha) == ["monto", "descripcion"]
    solo_descripcion = CargoReferido(comercio_texto="desembolso de un crédito")
    assert _datos_que_faltan(solo_descripcion) == ["monto", "cuando"]


def test_si_habla_de_hoy_se_le_pide_lo_que_falta_y_no_la_fecha_que_ya_dio():
    hoy = "IDIOMA: es\nCOMANDO: iniciar | disputas.reportar_cargo\nRECONOCE: no\nCARGO: nuevo\nCUANDO: relativa hoy\nFIN_CARGO"
    s, estado = _correr(hoy, "no reconozco un cargo que me hicieron hoy en la mañana")
    pregunta = next(e for e in estado if e.get("pregunta") == "dato_faltante")
    assert pregunta["campos"] == ["monto", "descripcion"]


def test_sin_monto_ni_fecha_no_se_dice_que_los_movimientos_con_el_monto_y_la_fecha_tienen_otra_descripcion():
    """Caso real de la clienta: «necesito saber cuándo entró mi dinero» (desembolso). No dio monto ni fecha; el Comparador no ve ninguna coincidencia.
    Antes el sistema afirmaba `descripcion_distinta` («con el monto y la fecha dichos…») y le pedía elegir entre dos cargos sin relación."""
    lectura = ("IDIOMA: es\nCOMANDO: iniciar | movimientos.consultar\nCARGO: nuevo\nDESCRIPCION: desembolso del crédito\nFIN_CARGO")
    visto = {}

    def guion(sistema, usuario, proposito):
        if proposito == "interpretar":
            return lectura
        if proposito == "comparar":
            return "COINCIDEN: ninguna"
        visto["estado"] = json.loads(usuario.split("ESTADO COMUNICABLE:\n", 1)[1])
        return redactor_falso(usuario)

    token, _ = sesion("DEMO-1001")
    c, m = conv(), ModeloFalso(guion)
    iniciar_con_sesion(c, token, m)
    procesar(c, Entrada(texto="necesito saber cuándo entró mi dinero"), token, m)
    hechos = [e.get("hecho") for e in visto["estado"]]
    assert "descripcion_distinta" not in hechos
