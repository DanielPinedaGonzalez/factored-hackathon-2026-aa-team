"""Un archivo del cliente solo se describe con lo verificado: nunca se promete que alguien lo esté mirando (ARQUITECTURA §8.9).

Quién lo verá depende del estado real: un traspaso activo (entra al paquete del asesor), un reclamo abierto (se propone agregarlo,
con confirmación) o nada (queda guardado y nadie lo revisa por ahora, sin hora de revisión)."""
import secrets

import pytest

from servicio.llm.cliente import ModeloFalso
from servicio.orquestador.orquestador import Entrada, procesar
from tests.apoyo import Guion, admin, limpiar_cliente, token_de

pytestmark = pytest.mark.db

ARCHIVO = {"tipo": "adjunto", "adjunto_id": "adj_prueba", "tipo_archivo": "image/png", "tamano": 1200}


def _hechos(m: ModeloFalso) -> set[str]:
    ultima = [x for x in m.llamadas if x["proposito"] == "redactar"][-1]
    return {h for h in ("adjunto_recibido", "adjunto_sin_revision") if h in ultima["usuario"]}


def test_sin_reclamo_ni_traspaso_se_dice_que_nadie_lo_revisa_por_ahora():
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    m = ModeloFalso(Guion([]))
    procesar("c_" + secrets.token_hex(6), Entrada(evento=ARCHIVO), token, m)
    assert _hechos(m) == {"adjunto_recibido", "adjunto_sin_revision"}          # nunca "lo está revisando una persona"


def test_un_archivo_que_llega_con_el_caso_ya_en_la_fila_entra_al_paquete_del_asesor():
    """Antes quedaba guardado pero fuera del paquete (armado antes): el asesor nunca lo veía."""
    token, cid = token_de("DEMO-1001")
    limpiar_cliente(cid)
    conv = "c_" + secrets.token_hex(6)
    procesar(conv, Entrada(texto="quiero hablar con una persona"), token, ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: pedir_persona"])))
    m = ModeloFalso(Guion([]))
    s = procesar(conv, Entrada(evento={**ARCHIVO, "adjunto_id": "adj_en_fila"}), token, m)
    assert not m.llamadas and s.ui and s.ui[0]["tipo"] == "aviso_espera"        # sin modelo: la interfaz muestra la fila real
    with admin() as c:
        paquete = c.execute("select paquete from atencion.traspasos where conversation_id = %s", (conv,)).fetchone()[0]
    assert "adj_en_fila" in paquete["adjuntos"]


def test_el_catalogo_no_promete_una_revision_que_nadie_verifico():
    from contratos import catalogo
    textos = " ".join(catalogo.cargar()["hechos"][k] for k in ("adjunto_recibido", "adjunto_sin_revision")).lower()
    assert "lo revisa una persona" not in textos and "lo está revisando" not in textos
