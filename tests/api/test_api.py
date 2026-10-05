import secrets

import pytest
from fastapi.testclient import TestClient

from servicio.api import app as api
from servicio.llm.cliente import ModeloFalso
from tests.apoyo import Guion, admin, limpiar_cliente

pytestmark = pytest.mark.db
cli = TestClient(api.app)


def test_salud_verifica_postgres():
    r = cli.get("/health").json()
    assert r["ok"] and int(r["postgres"]) >= 160015


def test_flujo_por_la_api_con_formulario_y_movimientos(monkeypatch):
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    api._modelo = ModeloFalso(Guion(["IDIOMA: es\nCOMANDO: iniciar | movimientos.consultar"]))
    r = cli.post("/conversacion/turno", json={"texto": "quiero ver mis movimientos"}).json()
    assert r["nodo"] == "N1"
    with admin() as c:
        c.execute("delete from atencion.desafios_otp where ip not like 'evaluacion%' and ip <> 'enumeracion'")
        cid = c.execute("select customer_id from atencion.identidades_demo where documento_demo='DEMO-1002'").fetchone()[0]
    limpiar_cliente(cid)
    d = cli.post("/identidad/desafio", json={"documento": "DEMO-1002"}).json()
    codigo = cli.get("/demo/buzon/DEMO-1002").json()[0]["mensaje"]
    tok = cli.post("/identidad/verificar", json={"desafio_id": d["desafio_id"], "codigo": codigo}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    movs = cli.get("/movimientos", headers=h).json()
    assert movs and "ref" in movs[0]
    r2 = cli.post("/conversacion/turno", json={"conversation_id": r["conversation_id"], "evento": {"tipo": "identidad_verificada"}},
                  headers=h).json()
    assert r2["nodo"] in ("N4", "N5", "N2")
    hist = cli.get(f"/conversacion/{r['conversation_id']}", headers=h).json()
    assert len(hist["turnos"]) >= 3


def test_ruta_de_equipo_con_token_de_cliente_se_niega():
    assert cli.get("/equipo/cola", headers={"Authorization": "Bearer x.y"}).status_code == 403


def test_adjunto_por_contenido_real():
    r = cli.post(f"/adjuntos?conversation_id=c_{secrets.token_hex(4)}", files={"archivo": ("foto.jpg", b"MZ\x90\x00ejecutable", "image/jpeg")})
    assert r.status_code == 415
    r = cli.post(f"/adjuntos?conversation_id=c_{secrets.token_hex(4)}", files={"archivo": ("c.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, "image/png")})
    assert r.status_code == 415                           # firma de PNG con una estructura que no se puede recorrer
    import struct
    import zlib

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))
    r = cli.post(f"/adjuntos?conversation_id=c_{secrets.token_hex(4)}", files={"archivo": ("c.png", png, "image/png")})
    assert r.status_code == 200 and r.json()["tipo_archivo"] == "image/png"


def test_las_corridas_ofrecidas_para_recorrer_tienen_varios_casos():
    """Una repetición de un solo caso (un experimento) no sirve para recorrer "paso a paso"."""
    corridas = cli.get("/corridas").json()
    if not list((api.RAIZ / "evaluacion" / "corridas").glob("*.json")):     # el export público no lleva las corridas (datos derivados del organizador)
        assert corridas == []
        return
    assert corridas and all(len(c["casos"]) >= api.MIN_CASOS_PARA_RECORRER for c in corridas)


def test_el_selector_de_idioma_del_chat_llega_por_la_api_y_cambia_la_conversacion(monkeypatch):
    """El selector ES/PT del chat envía el evento `cambiar_idioma`: sin sesión, sin pasar por el modelo."""
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    from tests.orquestador.test_idioma import _modelo
    api._modelo = _modelo([])                                            # el Intérprete no debe llamarse: es un evento del canal
    r = cli.post("/conversacion/turno", json={"evento": {"tipo": "cambiar_idioma", "idioma": "pt"}})
    assert r.status_code == 200
    with admin() as c:
        idioma = c.execute("select idioma from atencion.conversaciones where conversation_id = %s", (r.json()["conversation_id"],)).fetchone()[0]
    assert idioma == "pt"
