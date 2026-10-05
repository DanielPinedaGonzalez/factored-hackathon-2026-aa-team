"""Una transferencia no reconocida: se encuentra por lo que dijo el cliente, se nombra por su tipo y el asesor recibe
el plazo en la fecha real del cliente. Candado del error "Transfer" mostrado como comercio."""
import secrets

import pytest

from servicio.llm.cliente import ModeloFalso
from servicio.orquestador.orquestador import Entrada, procesar
from tests.apoyo import Guion, admin, limpiar_cliente, token_de

pytestmark = pytest.mark.db

TRANSFERENCIA = """IDIOMA: es
COMANDO: iniciar | disputas.reportar_cargo
RECONOCE: no
TIPO_DISPUTA: no_autorizada
CARGO: nuevo
MONTO: 8703
MONEDA: USD
CUANDO: relativa ayer
DESCRIPCION: transferencia
FIN_CARGO"""


def _solo(tipo):
    return lambda opciones: "COINCIDEN: " + (", ".join(a for a, d in opciones.items() if d.startswith(tipo)) or "ninguna")


def test_transferencia_no_reconocida_se_encuentra_y_se_nombra_por_su_tipo():
    token, cid = token_de("DEMO-1003")
    limpiar_cliente(cid)
    conv = "c_" + secrets.token_hex(6)
    m = ModeloFalso(Guion([TRANSFERENCIA], comparar=_solo("transferencia")))
    s = procesar(conv, Entrada(texto="no reconozco una transferencia de 8703 dólares de ayer, yo no la hice"), token, m)
    llamadas_del_primer_turno = len(m.llamadas)
    tarjeta = next(u for u in s.ui if u["tipo"] == "tarjeta_cargo")
    assert tarjeta["movimiento"] == "transferencia" and tarjeta["comercio"] is None
    assert "Transfer " not in s.texto and "Transfer (" not in s.texto and "—" not in s.texto
    assert "comparar" in [x["proposito"] for x in m.llamadas]
    procesar(conv, Entrada(evento={"tipo": "reconoce", "valor": "no"}), token, m)                    # dice que no la reconoce: monto alto → persona
    with admin() as c:
        paquete = c.execute("select paquete from atencion.traspasos where conversation_id = %s", (conv,)).fetchone()[0]
        reg = c.execute("select registro from operacion.registro_turnos where conversation_id = %s order by n limit 1", (conv,)).fetchone()[0]
    h = paquete["hechos_verificados"][0]
    assert h["movimiento"] == "transferencia" and "comercio" not in h
    assert paquete["plazo_normativo"]["vence_cliente"].endswith(tarjeta["fecha"][-4:])     # fecha real, no la de los datos
    assert any(p["componente"] == "comparador" and p["estado"] == "ok" for p in reg["pasos"])
    assert reg["tokens"]["llamadas"] == llamadas_del_primer_turno


def test_si_la_descripcion_no_coincide_y_hay_uno_solo_se_muestra_y_se_pregunta_si_lo_reconoce():
    """5-oct: con un único movimiento del monto y la fecha dichos no hay nada que elegir; se le muestra y se le pregunta si lo reconoce."""
    token, cid = token_de("DEMO-1003")
    limpiar_cliente(cid)
    conv = "c_" + secrets.token_hex(6)
    s = procesar(conv, Entrada(texto="no reconozco un pago de 8703 de ayer"), token,
                 ModeloFalso(Guion([TRANSFERENCIA.replace("transferencia", "pago")], comparar=_solo("pago"))))
    assert s.nodo == "N5" and not any(u["tipo"] == "opciones" for u in s.ui)
    assert next(u for u in s.ui if u["tipo"] == "tarjeta_cargo")["movimiento"] == "transferencia"


def test_presupuesto_de_la_conversacion_agotado_pasa_a_una_persona_sin_llamar_al_modelo():
    """A12: los tokens de cada turno se suman en el estado; con el presupuesto agotado no se llama más al modelo y la
    conversación sigue con una persona (no se corta), con el motivo que lo dice."""
    from servicio.orquestador import orquestador
    token, cid = token_de("DEMO-1003")
    limpiar_cliente(cid)
    conv = "c_" + secrets.token_hex(6)
    m = ModeloFalso(Guion([TRANSFERENCIA], comparar=_solo("transferencia")))
    procesar(conv, Entrada(texto="no reconozco una transferencia de 8703 dólares de ayer"), token, m)
    with admin() as c:
        gastado = c.execute("select (estado->>'tokens_consumidos')::int from atencion.estado_conversacion where conversation_id = %s",
                            (conv,)).fetchone()[0]
        c.execute("update atencion.traspasos set estado = 'resuelto' where conversation_id = %s", (conv,))
    assert gastado > 0
    import pytest
    mp = pytest.MonkeyPatch()
    mp.setattr(orquestador, "presupuesto_tokens_conversacion", lambda c: gastado)
    try:
        llamadas_antes = len(m.llamadas)
        s = procesar(conv, Entrada(texto="y otra cosa más"), token, m)
    finally:
        mp.undo()
    assert len(m.llamadas) == llamadas_antes and any(u["tipo"] == "aviso_espera" for u in s.ui)
    with admin() as c:
        motivos = c.execute("""select paquete->'motivo_traspaso' from atencion.traspasos where conversation_id = %s
                               order by llegada desc limit 1""", (conv,)).fetchone()[0]
    assert "presupuesto_conversacion" in motivos and "sin_modelo" not in motivos
