"""Intenciones de acción (CONTRATOS, `action_intent_id`; MODELO_DATOS §3.5; INV-CONFIRMA).

Se generan en el servidor al proponer una acción, ligadas a la sesión, a la versión de la conversación, al recurso y
a la acción exacta. Se consumen una sola vez: una confirmación vieja, de otra sesión o de otra versión no vale.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

import psycopg

TTL_MINUTOS = 10


class ConfirmacionInvalida(Exception):
    pass


def _hash(accion: str, recurso: str, parametros: dict) -> str:
    return hashlib.sha256(json.dumps([accion, recurso, parametros], sort_keys=True, default=str).encode()).hexdigest()[:16]


def proponer(c: psycopg.Connection, conversation_id: str, customer_id: str, session_id: str, version: int,
             accion: str, recurso: str, parametros: dict) -> tuple[str, datetime]:
    aid = "ai_" + secrets.token_urlsafe(12)
    expira = datetime.now(timezone.utc) + timedelta(minutes=TTL_MINUTOS)
    c.execute("""update atencion.intenciones_accion set estado = 'descartada'
                 where conversation_id = %s and estado = 'propuesta'""", (conversation_id,))
    c.execute("""insert into atencion.intenciones_accion (action_intent_id, conversation_id, customer_id, session_id,
                   conversation_version, accion, recurso, parametros, hash_propuesta, expira)
                 values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
              (aid, conversation_id, customer_id, session_id, version, accion, recurso, json.dumps(parametros, default=str),
               _hash(accion, recurso, parametros), expira))
    return aid, expira


def confirmar(c: psycopg.Connection, action_intent_id: str, session_id: str, version: int) -> dict:
    """Valida y marca `confirmada` con escritura condicional. `version` = versión de la conversación al confirmar."""
    i = c.execute("select * from atencion.intenciones_accion where action_intent_id = %s", (action_intent_id,)).fetchone()
    if i is None:
        raise ConfirmacionInvalida("no existe")
    if i["estado"] in ("completada", "ejecutando", "desconocida", "fallida", "confirmada"):
        return i                                            # reenvío de la misma confirmación: no se ejecuta dos veces
    if i["estado"] != "propuesta":
        raise ConfirmacionInvalida(i["estado"])
    if i["session_id"] != session_id:
        raise ConfirmacionInvalida("otra sesión")
    if i["conversation_version"] != version:
        raise ConfirmacionInvalida("la conversación cambió desde la propuesta")
    if i["expira"] < datetime.now(timezone.utc):
        c.execute("update atencion.intenciones_accion set estado = 'descartada' where action_intent_id = %s", (action_intent_id,))
        raise ConfirmacionInvalida("vencida")
    n = c.execute("""update atencion.intenciones_accion set estado = 'confirmada'
                     where action_intent_id = %s and estado = 'propuesta'""", (action_intent_id,)).rowcount
    if n == 0:
        raise ConfirmacionInvalida("carrera")
    return {**i, "estado": "confirmada"}


def marcar(c: psycopg.Connection, action_intent_id: str, estado: str, resultado: dict | None = None) -> None:
    c.execute("update atencion.intenciones_accion set estado = %s, resultado = %s where action_intent_id = %s",
              (estado, json.dumps(resultado or {}, default=str), action_intent_id))


def descartar_pendientes(c: psycopg.Connection, conversation_id: str) -> None:
    c.execute("update atencion.intenciones_accion set estado = 'descartada' where conversation_id = %s and estado = 'propuesta'",
              (conversation_id,))
