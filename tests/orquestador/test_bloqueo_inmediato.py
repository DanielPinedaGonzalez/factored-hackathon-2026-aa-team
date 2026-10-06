"""Bloqueo a pedido: lo decide el banco con un parámetro de operación (`bloqueo_inmediato_a_pedido`).

5-oct, Daniel: «si digo "necesito que me bloqueen esta tarjeta", el sistema lo hace ya mismo, no me da vueltas». Con 0 (por defecto) el cliente confirma con un
toque; con 1 se bloquea en el mismo turno, por el mismo camino (intención, idempotencia, relectura). Lo que el sistema ofrece por su cuenta siempre pide confirmar."""
import secrets

import pytest

from servicio.llm.cliente import ModeloFalso
from servicio.orquestador.orquestador import Entrada, procesar
from servicio.registro import parametros
from tests.apoyo import Guion, admin, limpiar_cliente, token_de

pytestmark = pytest.mark.db
PIDE = "IDIOMA: es\nCOMANDO: iniciar | tarjetas.bloquear"


@pytest.fixture
def parametro():
    def poner(valor):
        with admin() as c:
            parametros.cambiar(c, "bloqueo_inmediato_a_pedido", valor, "prueba", "prueba del bloqueo a pedido")
    yield poner
    poner(0)


def _pedir_bloqueo():
    token, cid = token_de("DEMO-1001")                      # una sola tarjeta
    limpiar_cliente(cid)
    return procesar("c_" + secrets.token_hex(6), Entrada(texto="necesito que me bloqueen esta tarjeta"), token, ModeloFalso(Guion([PIDE])))


def test_por_defecto_el_cliente_confirma_antes_de_bloquear(parametro):
    parametro(0)
    s = _pedir_bloqueo()
    assert s.nodo == "N7" and any(u["tipo"] == "confirmacion" for u in s.ui)


def test_si_el_banco_lo_decide_se_bloquea_en_el_mismo_turno(parametro):
    parametro(1)
    s = _pedir_bloqueo()
    assert s.nodo == "N10" and not any(u["tipo"] == "confirmacion" for u in s.ui)
    with admin() as c:
        assert c.execute("select count(*) from atencion.bloqueo_eventos").fetchone()[0] >= 1
