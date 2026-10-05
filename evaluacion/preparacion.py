"""Deja la base en el estado que el perfil del caso necesita (reclamos previos, bloqueos) antes de conversar.

Solo para evaluación local; lo corre el rol de migraciones. No importa la política (INV-EVAL).
"""
from __future__ import annotations

import secrets

import psycopg

from servicio.datos.db import URL_ADMIN as ADMIN


def limpiar(c, customer_id: str) -> None:
    for t in ("reclamo_eventos", "reclamo_notas"):
        c.execute(f"delete from atencion.{t} where customer_id = %s", (customer_id,))
    c.execute("delete from atencion.reclamos where customer_id = %s", (customer_id,))
    c.execute("delete from atencion.bloqueo_eventos where customer_id = %s", (customer_id,))
    c.execute("delete from atencion.bloqueos where customer_id = %s", (customer_id,))
    c.execute("""delete from atencion.traspaso_eventos where traspaso_id in
                 (select traspaso_id from atencion.traspasos where customer_id = %s)""", (customer_id,))
    c.execute("delete from atencion.mensajes_asesor where customer_id = %s", (customer_id,))
    c.execute("delete from atencion.traspasos where customer_id = %s", (customer_id,))


def _reclamo(c, customer_id: str, estado: str, explicacion: str | None = None, abono: str | None = None) -> str:
    tx = c.execute("""select transaction_id, product_id from servicio.transacciones where customer_id = %s
                      and tipo in ('Purchase','Payment') and estado = 'Approved' order by fecha desc
                      offset (select count(*) from atencion.reclamos where customer_id = %s) limit 1""",
                   (customer_id, customer_id)).fetchone()
    rid = "rec_" + secrets.token_hex(6)
    numero = "R-" + str(c.execute("select nextval('atencion.reclamo_numero')").fetchone()[0]).zfill(6)
    c.execute("""insert into atencion.reclamos (reclamo_id, numero, customer_id, transaction_id, product_id, tipo_disputa, estado,
                   plazo_vence, explicacion, documentos, referencia_abono)
                 values (%s,%s,%s,%s,%s,'no_autorizada',%s, current_date + 30, %s, %s, %s)""",
              (rid, numero, customer_id, tx[0], tx[1], estado, explicacion,
               ["estado de cuenta", "registro de la transacción"] if explicacion else None, abono))
    c.execute("""insert into atencion.reclamo_eventos (reclamo_id, customer_id, estado_anterior, estado_nuevo, autor_tipo, motivo)
                 values (%s,%s,null,%s,'asesor','preparación del caso de evaluación')""", (rid, customer_id, estado))
    return numero


def _bloqueo(c, customer_id: str, origen: str, motivo: str) -> None:
    p = c.execute("""select product_id from servicio.productos where customer_id = %s and tipo in ('Tarjeta Crédito','Tarjeta Débito')
                     and estado = 'Active' limit 1""", (customer_id,)).fetchone()
    bid = "blq_" + secrets.token_hex(6)
    c.execute("""insert into atencion.bloqueos (bloqueo_id, customer_id, product_id, origen, motivo) values (%s,%s,%s,%s,%s)""",
              (bid, customer_id, p[0], origen, motivo))
    c.execute("""insert into atencion.bloqueo_eventos (bloqueo_id, customer_id, estado_anterior, estado_nuevo, autor_tipo, motivo)
                 values (%s,%s,'activo','bloqueado_temporal',%s,%s)""", (bid, customer_id, "cliente" if origen == "cliente" else "sistema", motivo))


def preparar(customer_id: str, perfil: dict) -> dict:
    with psycopg.connect(ADMIN, autocommit=True) as c:
        limpiar(c, customer_id)
        tipo = perfil["tipo"]
        hechos: dict = {}
        if tipo == "con_reclamo_abierto":
            hechos["reclamos"] = [_reclamo(c, customer_id, "abierto") for _ in range(perfil.get("reclamos", 1))]
        elif tipo == "con_reclamo_resuelto":
            hechos["reclamos"] = [_reclamo(c, customer_id, "resuelto_a_favor", abono="ABONO-DEMO-1")]
        elif tipo == "con_reclamo_en_contra":
            hechos["reclamos"] = [_reclamo(c, customer_id, "resuelto_en_contra",
                                           explicacion="La compra se hizo con la tarjeta física y el código de seguridad.")]
        elif tipo == "con_reclamo_a_favor_sin_abono":
            hechos["reclamos"] = [_reclamo(c, customer_id, "resuelto_a_favor")]
        elif tipo == "con_bloqueo_por_riesgo":
            _bloqueo(c, customer_id, "riesgo", "riesgo")
        elif tipo == "con_bloqueo_del_cliente":
            _bloqueo(c, customer_id, "cliente", None)
        return hechos
