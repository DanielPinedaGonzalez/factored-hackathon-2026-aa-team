"""T6/T20 y SEG-4: la base niega aunque el código se equivoque."""
import psycopg
import pytest

from servicio.datos.db import URL, URL_ADMIN, transaccion

pytestmark = pytest.mark.db


def _dos_clientes():
    with psycopg.connect(URL_ADMIN) as c:
        return [r[0] for r in c.execute("select customer_id from servicio.clientes order by 1 limit 2")]


def test_sin_rol_la_conexion_no_ve_nada():
    with psycopg.connect(URL) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
        c.execute("select count(*) from servicio.transacciones")


def test_cliente_solo_ve_lo_suyo():
    a, b = _dos_clientes()
    with transaccion("app_ejecucion", customer_id=a) as c:
        filas = c.execute("select distinct customer_id from servicio.transacciones").fetchall()
        assert {f["customer_id"] for f in filas} == {a}
        assert c.execute("select count(*) n from servicio.transacciones where customer_id = %s", (b,)).fetchone()["n"] == 0


def test_sin_sujeto_no_ve_datos_de_cuenta():
    with transaccion("app_ejecucion") as c:
        assert c.execute("select count(*) n from servicio.transacciones").fetchone()["n"] == 0


def test_rol_de_ejecucion_no_puede_borrar_eventos():
    a, _ = _dos_clientes()
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with transaccion("app_ejecucion", customer_id=a) as c:
            c.execute("delete from atencion.reclamo_eventos")


def test_asesor_sin_asignacion_no_ve_filas():
    with transaccion("app_asesor", asesor_id="E30142") as c:
        assert c.execute("select count(*) n from servicio.transacciones").fetchone()["n"] == 0
        assert c.execute("select count(*) n from atencion.reclamos").fetchone()["n"] == 0


def test_roles_sin_bypass():
    with psycopg.connect(URL_ADMIN) as c:
        filas = c.execute("select rolname, rolsuper, rolbypassrls from pg_roles where rolname like 'app_%'").fetchall()
        assert filas and all(not s and not b for _, s, b in filas)
