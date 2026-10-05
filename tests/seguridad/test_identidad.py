"""SEG-1, SEG-2, S-5: el documento no basta; misma respuesta exista o no; tres intentos."""
import time

import psycopg
import pytest

from servicio.identidad.identidad import leer_token, pedir_codigo, verificar_codigo

pytestmark = pytest.mark.db
from servicio.datos.db import URL_ADMIN as ADMIN


def _codigo(customer_id):
    with psycopg.connect(ADMIN) as c:
        return c.execute("select mensaje from atencion.buzon_sandbox where customer_id = %s order by id desc limit 1",
                         (customer_id,)).fetchone()[0]


def _demo():
    with psycopg.connect(ADMIN) as c:
        c.execute("delete from atencion.desafios_otp where ip not like 'evaluacion%' and ip <> 'enumeracion'")
        return c.execute("select customer_id, documento_demo from atencion.identidades_demo where documento_demo = 'DEMO-1001'").fetchone()


def test_documento_sin_codigo_no_da_acceso_y_codigo_correcto_si():
    cid, doc = _demo()
    d = pedir_codigo(doc, "10.0.0.1")
    assert not verificar_codigo(d["desafio_id"], "000000", "10.0.0.1")["ok"]
    r = verificar_codigo(d["desafio_id"], _codigo(cid), "10.0.0.1")
    assert r["ok"] and leer_token(r["token"])["sub"] == cid


def test_misma_respuesta_exista_o_no_el_documento():
    _demo()
    t0 = time.monotonic(); a = pedir_codigo("DEMO-1001", "10.0.0.2"); ta = time.monotonic() - t0
    t0 = time.monotonic(); b = pedir_codigo("NO-EXISTE-99", "10.0.0.2"); tb = time.monotonic() - t0
    assert a.keys() == b.keys() and a["estado"] == b["estado"] and abs(ta - tb) < 0.15


def test_tres_intentos_fallidos_bloquean():
    _demo()
    d = pedir_codigo("DEMO-1001", "10.0.0.3")
    for _ in range(3):
        r = verificar_codigo(d["desafio_id"], "111111", "10.0.0.3")
    assert r["bloqueado"] and not verificar_codigo(d["desafio_id"], "111111", "10.0.0.3")["ok"]


def test_token_alterado_no_vale():
    cid, doc = _demo()
    d = pedir_codigo(doc, "10.0.0.4")
    tok = verificar_codigo(d["desafio_id"], _codigo(cid), "10.0.0.4")["token"]
    assert leer_token(tok[:-2] + "00") is None


def test_codigo_llega_a_todos_los_canales():
    cid, doc = _demo()
    pedir_codigo(doc, "10.0.0.5")
    with psycopg.connect(ADMIN) as c:
        canales = c.execute("select count(distinct canal) from atencion.buzon_sandbox where customer_id = %s", (cid,)).fetchone()[0]
    assert canales == 2


def test_las_identidades_demo_publicas_no_se_bloquean_por_documento_pero_las_demas_si():
    """R-01: DEMO-* se publica en el README y la comparten todos los que prueban la demo; conserva el límite por IP."""
    cid, doc = _demo()
    for i in range(8):                                   # más que el límite por documento (5), cada una desde otra IP
        d = pedir_codigo(doc, f"10.1.0.{i}")
        assert verificar_codigo(d["desafio_id"], _codigo(cid), f"10.1.0.{i}")["ok"], f"la solicitud {i + 1} de DEMO-1001 se bloqueó"
    for i in range(6):                                   # un documento que no es de la demo sigue limitado por documento
        pedir_codigo("OTRO-DOC-1", f"10.2.0.{i}")
    with psycopg.connect(ADMIN) as c:
        limites = c.execute("select count(*) from operacion.eventos_seguridad where tipo = 'limite_alcanzado' and ip like '10.2.0.%'").fetchone()[0]
    assert limites >= 1


def test_el_limite_por_ip_sigue_aplicando_a_las_identidades_demo():
    from servicio.identidad.identidad import CONFIG
    limite = CONFIG["max_desafios_por_ip"]                # sale de config/identidad.yaml, no de un número escrito aquí
    cid, doc = _demo()
    resultados = [verificar_codigo(pedir_codigo(doc, "10.3.0.1")["desafio_id"], _codigo(cid), "10.3.0.1")["ok"] for _ in range(limite + 2)]
    assert resultados[:limite].count(True) == limite and not any(resultados[limite:])
