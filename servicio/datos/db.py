"""Acceso a la base (INV-RLS): cada transacción asume un rol con SET LOCAL ROLE y fija el sujeto con SET LOCAL.

El sujeto sale del token, nunca del modelo ni del mensaje. La conexión es de `app_api`, que no hereda privilegios:
sin SET LOCAL ROLE no puede leer nada.
"""
from __future__ import annotations

import contextlib
import os
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

URL = os.environ.get("DATABASE_URL", "postgresql://app_api:app_api_local@127.0.0.1:5433/aa_team")
URL_ADMIN = os.environ.get("DATABASE_URL_ADMIN", "postgresql://aa_admin:aa_admin_local@127.0.0.1:5433/aa_team")   # migraciones, preparación
ROLES = {"app_ejecucion", "app_identidad", "app_asesor", "app_supervisor", "app_observador", "app_enrutador"}
_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(URL, min_size=1, max_size=int(os.environ.get("DB_POOL", "5")), open=True,
                               kwargs={"row_factory": dict_row, "autocommit": False})
    return _pool


@contextlib.contextmanager
def transaccion(rol: str, customer_id: str | None = None, conversation_id: str | None = None,
                asesor_id: str | None = None) -> Iterator[psycopg.Connection]:
    if rol not in ROLES:
        raise ValueError(f"rol desconocido: {rol}")
    with pool().connection() as c:
        with c.transaction():
            c.execute(f"SET LOCAL ROLE {rol}")
            c.execute("SELECT set_config('app.customer_id', %s, true), set_config('app.conversation_id', %s, true), "
                      "set_config('app.asesor_id', %s, true), set_config('app.origen', %s, true)",
                      (customer_id or "", conversation_id or "", asesor_id or "", os.environ.get("REGISTRO_ORIGEN", "operacion")))
            yield c
