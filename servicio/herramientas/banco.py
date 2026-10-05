"""A6 — Servicio bancario: herramientas con contrato (CONTRATOS, "Herramientas").

Cada función recibe una conexión abierta con `transaccion(...)`: el sujeto ya está fijado por el token y la RLS
aplica. Cada escritura es condicional y deja su evento en la misma transacción; ninguna herramienta borra. Los
errores son tipados. `NO_AUTORIZADO` y `NO_ENCONTRADO` se ven idénticos hacia el cliente.
"""
from __future__ import annotations

import secrets
from datetime import date, timedelta

import psycopg

from servicio.politica.motor import cargar as _politica

# Qué es un cargo lo declara la política, en un solo lugar (`politica/comun.yaml`): la búsqueda de movimientos lee de ahí, así que lo que el
# asistente busca y lo que se puede reclamar no pueden separarse.
TIPOS_CARGO = tuple(_politica()["comun"]["tipos_operacion_reclamables"])
ACTIVOS = ("abierto", "en_revision", "esperando_cliente")


class ErrorHerramienta(Exception):
    def __init__(self, codigo: str, detalle: str = "", datos: dict | None = None):
        super().__init__(f"{codigo}: {detalle}")
        self.codigo, self.detalle, self.datos = codigo, detalle, datos or {}


def _id(prefijo: str) -> str:
    return f"{prefijo}_{secrets.token_hex(8)}"


# ---------- Lecturas ----------

def listar_transacciones(c: psycopg.Connection, desde: date, hasta: date, solo_cargos: bool = True) -> list[dict]:
    tipos = "and t.tipo = any(%s)" if solo_cargos else ""
    params = [desde, hasta + timedelta(days=1)] + ([list(TIPOS_CARGO)] if solo_cargos else [])
    filas = c.execute(f"""
        select t.transaction_id, t.fecha, t.monto, t.moneda, t.amount_usd, t.comercio, t.ciudad, t.canal, t.estado,
               t.tipo, t.product_id, t.fraud_score, t.moneda_pais_coherente, p.tipo as tipo_producto, p.ultimos4
        from servicio.transacciones t left join servicio.productos p using (product_id)
        where t.fecha >= %s and t.fecha < %s {tipos} order by t.fecha desc""", params).fetchall()
    return [{**f, "hora": f["fecha"].strftime("%H:%M"), "fecha": f["fecha"].date(), "fecha_hora": f["fecha"].replace(tzinfo=None),
             "monto": float(f["monto"]) if f["monto"] is not None else None,
             "amount_usd": float(f["amount_usd"]) if f["amount_usd"] is not None else None} for f in filas]


def obtener_transaccion(c: psycopg.Connection, transaction_id: str) -> dict:
    f = c.execute("""select t.*, p.tipo as tipo_producto, p.ultimos4 from servicio.transacciones t
                     left join servicio.productos p using (product_id) where t.transaction_id = %s""", (transaction_id,)).fetchone()
    if f is None:
        raise ErrorHerramienta("NO_ENCONTRADO")
    return f


def cliente(c: psycopg.Connection) -> dict:
    f = c.execute("select customer_id, pais, segmento, nombre_pila from servicio.clientes").fetchone()
    if f is None:
        raise ErrorHerramienta("NO_AUTORIZADO")
    return f


def listar_productos(c: psycopg.Connection) -> list[dict]:
    return c.execute("""select p.product_id, p.tipo, p.estado, p.ultimos4, b.bloqueo_id, b.origen as bloqueo_origen,
                               b.motivo as bloqueo_motivo, b.estado as bloqueo_estado
                        from servicio.productos p left join atencion.bloqueos b
                          on b.product_id = p.product_id and b.estado = 'bloqueado_temporal'
                        order by p.tipo""").fetchall()


def estado_producto(c: psycopg.Connection, product_id: str) -> dict:
    for p in listar_productos(c):
        if p["product_id"] == product_id:
            return {**p, "estado_visible": "bloqueado_temporal" if p["bloqueo_id"] else p["estado"]}
    raise ErrorHerramienta("NO_ENCONTRADO")


def listar_reclamos(c: psycopg.Connection) -> list[dict]:
    return c.execute("""select r.reclamo_id, r.numero, r.estado, r.tipo_disputa, r.plazo_vence, r.transaction_id,
                               r.explicacion, r.documentos, r.referencia_abono, r.creado, r.version,
                               t.monto, t.moneda, t.comercio, t.tipo as tipo_movimiento, t.fecha as fecha_cargo
                        from atencion.reclamos r left join servicio.transacciones t using (transaction_id)
                        order by r.creado desc""").fetchall()


def reclamos_previos(c: psycopg.Connection, hoy: date, dias: int = 90) -> int:
    return c.execute("select count(*) n from atencion.reclamos where creado::date >= %s",
                     (hoy - timedelta(days=dias),)).fetchone()["n"]


# ---------- Escrituras (idempotentes por action_intent_id) ----------

def abrir_reclamo(c: psycopg.Connection, customer_id: str, transaction_id: str, tipo: str, action_intent_id: str,
                  conversation_id: str, plazo: dict | None, prioridad: int = 4, habilidad: str = "reclamos",
                  grupo: str | None = None) -> dict:
    previo = c.execute("select * from atencion.reclamos where action_intent_id = %s", (action_intent_id,)).fetchone()
    if previo:
        return previo                                     # reenvío: el resultado ya registrado
    tx = obtener_transaccion(c, transaction_id)           # RLS: si no es del sujeto, NO_ENCONTRADO
    existente = c.execute("select numero, estado from atencion.reclamos where transaction_id = %s and estado = any(%s)",
                          (transaction_id, list(ACTIVOS))).fetchone()
    if existente:
        raise ErrorHerramienta("YA_EXISTE", datos=existente)
    numero = "R-" + str(c.execute("select nextval('atencion.reclamo_numero') n").fetchone()["n"]).zfill(6)
    rid = _id("rec")
    try:
        with c.transaction():
            c.execute("""insert into atencion.reclamos (reclamo_id, numero, customer_id, transaction_id, product_id,
                           tipo_disputa, prioridad, plazo_vence, plazo_fuente, grupo, habilidad, conversation_id, action_intent_id)
                         values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (rid, numero, customer_id, transaction_id, tx["product_id"], tipo, prioridad,
                       (plazo or {}).get("vence"), (plazo or {}).get("fuente"), grupo, habilidad, conversation_id,
                       action_intent_id))
            c.execute("""insert into atencion.reclamo_eventos (reclamo_id, customer_id, estado_anterior, estado_nuevo, autor_tipo, motivo)
                         values (%s,%s,null,'abierto','cliente','abierto por el cliente en la conversación')""", (rid, customer_id))
    except psycopg.errors.UniqueViolation:
        raise ErrorHerramienta("YA_EXISTE")
    return c.execute("select * from atencion.reclamos where reclamo_id = %s", (rid,)).fetchone()


def agregar_informacion_reclamo(c: psycopg.Connection, customer_id: str, reclamo_id: str, texto: str | None,
                                adjunto_id: str | None, action_intent_id: str) -> dict:
    previo = c.execute("select * from atencion.reclamo_notas where action_intent_id = %s", (action_intent_id,)).fetchone()
    if previo:
        return previo
    r = c.execute("select estado, version from atencion.reclamos where reclamo_id = %s", (reclamo_id,)).fetchone()
    if r is None:
        raise ErrorHerramienta("NO_ENCONTRADO")
    if r["estado"] not in ACTIVOS:
        raise ErrorHerramienta("NO_PERMITIDO", f"reclamo {r['estado']}")
    c.execute("""insert into atencion.reclamo_notas (reclamo_id, customer_id, autor_tipo, texto, adjunto_id, action_intent_id)
                 values (%s,%s,'cliente',%s,%s,%s)""", (reclamo_id, customer_id, texto, adjunto_id, action_intent_id))
    if adjunto_id:
        c.execute("update atencion.adjuntos set reclamo_id = %s where adjunto_id = %s", (reclamo_id, adjunto_id))
    if r["estado"] == "esperando_cliente":
        c.execute("select atencion.transicion_reclamo(%s,'en_revision','cliente',null,'el cliente respondió',%s)",
                  (reclamo_id, r["version"]))
    return c.execute("select * from atencion.reclamo_notas where action_intent_id = %s", (action_intent_id,)).fetchone()


def retirar_reclamo(c: psycopg.Connection, reclamo_id: str, motivo: str, action_intent_id: str) -> dict:
    r = c.execute("select estado, version from atencion.reclamos where reclamo_id = %s", (reclamo_id,)).fetchone()
    if r is None:
        raise ErrorHerramienta("NO_ENCONTRADO")
    if r["estado"] == "retirado":
        return {"reclamo_id": reclamo_id, "estado": "retirado"}
    try:
        with c.transaction():
            c.execute("select atencion.transicion_reclamo(%s,'retirado','cliente',null,%s,%s)", (reclamo_id, motivo, r["version"]))
    except psycopg.errors.RaiseException as e:
        raise ErrorHerramienta("NO_PERMITIDO" if "NO_PERMITIDO" in str(e) else "TEMPORAL", str(e).split("\n")[0])
    return {"reclamo_id": reclamo_id, "estado": "retirado"}


def bloquear_producto(c: psycopg.Connection, customer_id: str, product_id: str, origen: str, motivo: str | None,
                      action_intent_id: str) -> dict:
    previo = c.execute("select * from atencion.bloqueos where action_intent_id = %s", (action_intent_id,)).fetchone()
    if previo:
        return previo
    estado_producto(c, product_id)                          # RLS: solo productos del sujeto
    activo = c.execute("select * from atencion.bloqueos where product_id = %s and estado = 'bloqueado_temporal'",
                       (product_id,)).fetchone()
    if activo:
        return activo                                       # ya bloqueado: el estado pedido ya se cumple
    bid = _id("blq")
    try:
        with c.transaction():
            c.execute("""insert into atencion.bloqueos (bloqueo_id, customer_id, product_id, origen, motivo, action_intent_id)
                         values (%s,%s,%s,%s,%s,%s)""", (bid, customer_id, product_id, origen, motivo, action_intent_id))
            c.execute("""insert into atencion.bloqueo_eventos (bloqueo_id, customer_id, estado_anterior, estado_nuevo, autor_tipo, motivo)
                         values (%s,%s,'activo','bloqueado_temporal','cliente',%s)""", (bid, customer_id, motivo))
    except psycopg.errors.UniqueViolation:
        pass
    return c.execute("select * from atencion.bloqueos where product_id = %s and estado = 'bloqueado_temporal'", (product_id,)).fetchone()


def desbloquear_producto(c: psycopg.Connection, customer_id: str, product_id: str, action_intent_id: str,
                         hay_senal_riesgo: bool) -> dict:
    b = c.execute("select * from atencion.bloqueos where product_id = %s and estado = 'bloqueado_temporal'", (product_id,)).fetchone()
    if b is None:
        return {"product_id": product_id, "estado": "activo"}
    if b["origen"] != "cliente" or b["motivo"] == "riesgo" or hay_senal_riesgo:
        raise ErrorHerramienta("NO_PERMITIDO", "desbloqueo tras riesgo: solo un asesor de fraude")
    with c.transaction():
        n = c.execute("""update atencion.bloqueos set estado = 'activo', version = version + 1
                         where bloqueo_id = %s and version = %s and estado = 'bloqueado_temporal'""",
                      (b["bloqueo_id"], b["version"])).rowcount
        if n == 0:
            raise ErrorHerramienta("TEMPORAL", "conflicto de versión")
        c.execute("""insert into atencion.bloqueo_eventos (bloqueo_id, customer_id, estado_anterior, estado_nuevo, autor_tipo, motivo)
                     values (%s,%s,'bloqueado_temporal','activo','cliente',%s)""", (b["bloqueo_id"], customer_id, action_intent_id))
    return {"product_id": product_id, "estado": "activo"}
