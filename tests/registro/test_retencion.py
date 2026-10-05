"""MODELO_DATOS §5: la purga vacía el contenido vencido de conversaciones sin caso vivo y de adjuntos sin reclamo,
borra registros técnicos vencidos, nunca toca un reclamo ni una conversación con caso activo, y deja sus conteos."""
import secrets

import pytest

from tests.apoyo import ADMIN, admin

pytestmark = pytest.mark.db


def _conversacion(c, vieja: bool) -> str:
    cid = "c_" + secrets.token_hex(6)
    c.execute("insert into atencion.conversaciones (conversation_id) values (%s)", (cid,))
    c.execute("insert into atencion.estado_conversacion (conversation_id, version, estado) values (%s, 0, %s)",
              (cid, '{"conversation_id": "%s", "historial": [{"rol": "cliente", "texto_con_marcadores": "hola"}]}' % cid))
    c.execute("insert into atencion.turnos (conversation_id, n, rol, texto, creado) values (%s, 1, 'cliente', 'me robaron', %s)",
              (cid, "2020-01-01" if vieja else "now()"))
    return cid


def test_purga_respeta_los_casos_vivos_y_deja_sus_conteos():
    from scripts.purgar_retencion import purgar
    with admin() as c:
        vieja, reciente, con_caso = _conversacion(c, True), _conversacion(c, False), _conversacion(c, True)
        c.execute("""insert into atencion.traspasos (traspaso_id, numero, conversation_id, paquete, habilidad, idioma, prioridad,
                       primera_respuesta_vence, version_config) values (%s, %s, %s, '{}', 'general', 'es', 4, now(), 'x')""",
                  ("tr_" + secrets.token_hex(6), "T-P" + secrets.token_hex(3), con_caso))
    conteos = purgar(ADMIN)
    with admin() as c:
        texto = {cid: c.execute("select texto from atencion.turnos where conversation_id = %s", (cid,)).fetchone()[0]
                 for cid in (vieja, reciente, con_caso)}
        historial = c.execute("select estado->'historial' from atencion.estado_conversacion where conversation_id = %s",
                              (vieja,)).fetchone()[0]
        ultimo = c.execute("select conteos from operacion.purga_eventos order by id desc limit 1").fetchone()[0]
    assert texto == {vieja: "", reciente: "me robaron", con_caso: "me robaron"} and historial == []
    assert conteos["turnos_vaciados"] >= 1 and ultimo == conteos
