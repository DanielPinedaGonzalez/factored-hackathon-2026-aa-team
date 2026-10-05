"""A13 — Registro de cada llamada a un modelo y de cada incidente (diseño de un sistema propio del autor).

- `registrar_llamada`: una fila por llamada, exitosa o fallida, en `operacion.consumo_modelos`, con la razón real del
  fallo (código HTTP, mensaje del proveedor, cabeceras de límite, error de red). La llave nunca: solo su índice.
- `registrar_incidente`: lo inesperado (una excepción no prevista en la API o en un turno), con dónde, qué, el
  rastro y el contexto, en `operacion.incidentes`. Al cliente le llega un error genérico; el sistema guarda la razón.
- El contexto (conversación, turno, llave) viaja en una variable de contexto que fija el orquestador.
- Nunca lanza: si la base no responde, lo deja en el log del proceso. Escribe en su propia transacción, así lo
  registrado queda aunque el turno se revierta.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import traceback

from servicio.datos.db import transaccion

log = logging.getLogger("registro")
_contexto: contextvars.ContextVar[dict] = contextvars.ContextVar("contexto_registro", default={})


def fijar_contexto(**valores) -> contextvars.Token:
    return _contexto.set({**_contexto.get(), **{k: v for k, v in valores.items() if v is not None}})


def restaurar_contexto(token: contextvars.Token) -> None:
    _contexto.reset(token)


def contexto() -> dict:
    return dict(_contexto.get())


def _hash(texto: str | None) -> str | None:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12] if texto else None


def registrar_llamada(*, proveedor: str, modelo: str, proposito: str, exito: bool, latencia_ms: float = 0.0,
                      tokens_entrada: int = 0, tokens_salida: int = 0, espera_s: float = 0.0, request_id: str | None = None,
                      llave: int | None = None, cupo: dict | None = None, sistema: str | None = None,
                      error: str | None = None, http_estado: int | None = None, tamano_mensaje: int | None = None) -> None:
    ctx = contexto()
    try:
        with transaccion("app_ejecucion", conversation_id=ctx.get("conversation_id")) as c:
            c.execute("""insert into operacion.consumo_modelos (conversation_id, turn_id, proveedor, modelo, proposito,
                           tokens_entrada, tokens_salida, cupo_restante, tamano_mensaje, latencia_ms, espera_s, resultado,
                           hash_prompt, request_id, llave, error, http_estado)
                         values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (ctx.get("conversation_id"), ctx.get("turn_id"), proveedor, modelo, proposito or "sin_clasificar",
                       tokens_entrada, tokens_salida, json.dumps(cupo or {}), tamano_mensaje, latencia_ms, espera_s,
                       "ok" if exito else "fallo", _hash(sistema), request_id, llave, (error or None) and error[:500],
                       http_estado))
    except Exception:                                   # el registro nunca tumba la conversación
        log.exception("no se pudo registrar la llamada al modelo: %s %s %s", proveedor, modelo, error)


def enfriamientos_vigentes(proveedor: str) -> dict[int, float]:
    """Por llave, los segundos que faltan de la última espera que pidió el proveedor ("reintentar en Ns"), leídos del
    registro: el estado de las llaves sobrevive a un reinicio del proceso. Nunca lanza."""
    import re
    try:
        with transaccion("app_ejecucion") as c:
            filas = c.execute("""select distinct on (llave) llave, resultado, error,
                                        extract(epoch from (now() - creado)) hace_s
                                 from operacion.consumo_modelos where proveedor = %s and llave is not null
                                   and creado > now() - interval '1 day' order by llave, id desc""", (proveedor,)).fetchall()
    except Exception:
        log.exception("no se pudieron leer los enfriamientos del registro")
        return {}
    salida = {}
    for f in filas:
        m = re.search(r"reintentar en (\d+)s", f["error"] or "")
        if f["resultado"] == "fallo" and m and int(m.group(1)) > float(f["hace_s"]):
            salida[f["llave"]] = int(m.group(1)) - float(f["hace_s"])
    return salida


def registrar_incidente(donde: str, excepcion: BaseException | None = None, *, tipo: str | None = None,
                        mensaje: str | None = None, severidad: str = "error", **detalle) -> int | None:
    """Devuelve el número del incidente, para darlo como referencia sin mostrar la razón."""
    ctx = contexto()
    try:
        rastro = "".join(traceback.format_exception(excepcion))[-4000:] if excepcion else None
        with transaccion("app_ejecucion", conversation_id=ctx.get("conversation_id")) as c:
            return c.execute("""insert into operacion.incidentes (donde, tipo, mensaje, severidad, rastro, conversation_id, turn_id, detalle)
                         values (%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                      (donde, tipo or (type(excepcion).__name__ if excepcion else "incidente"),
                       (mensaje or (str(excepcion) if excepcion else ""))[:1000], severidad, rastro,
                       ctx.get("conversation_id"), ctx.get("turn_id"), json.dumps(detalle, default=str))).fetchone()["id"]
    except Exception:
        log.exception("no se pudo registrar el incidente en %s", donde)
        return None


def registrar_evento_seguridad(tipo: str, ip: str | None = None, **detalle) -> None:
    """Un rechazo de la API (límite, sesión, rol) con su razón; nunca lanza."""
    try:
        with transaccion("app_ejecucion") as c:
            c.execute("insert into operacion.eventos_seguridad (tipo, ip, detalle) values (%s,%s,%s)",
                      (tipo, ip, json.dumps(detalle, default=str)))
    except Exception:
        log.exception("no se pudo registrar el evento de seguridad %s", tipo)
