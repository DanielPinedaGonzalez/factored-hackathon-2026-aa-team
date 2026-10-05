"""A7 — Verificador de acciones (CONTRATOS A7): nunca escribe, solo relee por `action_intent_id`.

Nada se comunica como hecho sin estado `completada` releído (INV-VERIFICA). Un tiempo agotado deja la acción
`desconocida`: se relee por la clave de idempotencia y nunca se escribe dos veces a ciegas.
"""
from __future__ import annotations

import psycopg


def releer(c: psycopg.Connection, accion: str, action_intent_id: str, esperado: dict) -> tuple[str, dict]:
    """Devuelve ('completada' | 'fallida', lo releído)."""
    if accion == "abrir_reclamo":
        f = c.execute("select numero, estado, plazo_vence, tipo_disputa from atencion.reclamos where action_intent_id = %s",
                      (action_intent_id,)).fetchone()
        return ("completada", dict(f)) if f and f["estado"] == "abierto" else ("fallida", dict(f or {}))
    if accion == "agregar_informacion_reclamo":
        f = c.execute("select id, reclamo_id from atencion.reclamo_notas where action_intent_id = %s", (action_intent_id,)).fetchone()
        return ("completada", dict(f)) if f else ("fallida", {})
    if accion == "retirar_reclamo":
        f = c.execute("select numero, estado from atencion.reclamos where reclamo_id = %s", (esperado["reclamo_id"],)).fetchone()
        return ("completada", dict(f)) if f and f["estado"] == "retirado" else ("fallida", dict(f or {}))
    if accion == "bloquear_producto":
        f = c.execute("select estado from atencion.bloqueos where product_id = %s and estado = 'bloqueado_temporal'",
                      (esperado["product_id"],)).fetchone()
        return ("completada", {"estado": "bloqueado_temporal"}) if f else ("fallida", {})
    if accion == "desbloquear_producto":
        f = c.execute("select 1 from atencion.bloqueos where product_id = %s and estado = 'bloqueado_temporal'",
                      (esperado["product_id"],)).fetchone()
        return ("fallida", {"estado": "bloqueado_temporal"}) if f else ("completada", {"estado": "activo"})
    raise ValueError(f"acción sin verificador: {accion}")
