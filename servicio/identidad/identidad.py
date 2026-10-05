"""Identidad (N1, ARQUITECTURA §8.10; SEGURIDAD S-1, S-2, S-5).

Formulario seguro: lo escrito va directo aquí, nunca al historial ni al modelo. El código de un solo uso llega a la
vez a todos los canales registrados (en la demo, los buzones del sandbox). La respuesta es idéntica, y en tiempo
similar, exista o no el documento (anti-enumeración), con límites por IP y por documento. El teléfono y el correo
registrados nunca se cambian aquí. El token es firmado y dura lo que dice `config/identidad.yaml`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from servicio.datos.db import transaccion

CONFIG = yaml.safe_load((Path(__file__).resolve().parents[2] / "config" / "identidad.yaml").read_text())
SECRETO = os.environ.get("TOKEN_SECRETO", "solo-desarrollo-cambiar-en-produccion").encode()


def _h(texto: str) -> str:
    return hashlib.sha256((texto.strip().upper()).encode()).hexdigest()


def _evento(c, tipo: str, ip: str | None, detalle: dict) -> None:
    c.execute("insert into operacion.eventos_seguridad (tipo, ip, detalle) values (%s,%s,%s)",
              (tipo, ip, json.dumps(detalle)))


def pedir_codigo(documento: str, ip: str) -> dict:
    """Crea el desafío. Misma respuesta siempre: {desafio_id, mensaje_para_interfaz}."""
    t0 = time.monotonic()
    desafio = "d_" + secrets.token_urlsafe(12)
    doc_h = _h(documento)
    ventana = datetime.now(timezone.utc) - timedelta(minutes=CONFIG["ventana_limites_minutos"])
    with transaccion("app_identidad") as c:
        por_ip = c.execute("select count(*) n from atencion.desafios_otp where ip = %s and creado > %s", (ip, ventana)).fetchone()["n"]
        por_doc = c.execute("select count(*) n from atencion.desafios_otp where documento_hash = %s and creado > %s",
                            (doc_h, ventana)).fetchone()["n"]
        # Las identidades DEMO-* se publican en el README y las comparten todos los que prueban la demo: el límite por documento
        # no las protege de nada y bloquea a quien llega después. Conservan el límite por IP.
        es_demo = documento.strip().upper().startswith("DEMO-")
        limitado = por_ip >= CONFIG["max_desafios_por_ip"] or (por_doc >= CONFIG["max_desafios_por_documento"] and not es_demo)
        ident = None if limitado else c.execute(
            "select customer_id, canales from atencion.identidades_demo where upper(documento_demo) = upper(%s)",
            (documento.strip(),)).fetchone()
        codigo = f"{secrets.randbelow(10**6):06d}"
        c.execute("""insert into atencion.desafios_otp (desafio_id, documento_hash, customer_id, codigo_hash, ip, vence)
                     values (%s,%s,%s,%s,%s,%s)""",
                  (desafio, doc_h, ident["customer_id"] if ident else None, _h(codigo) if ident else None, ip,
                   datetime.now(timezone.utc) + timedelta(minutes=CONFIG["codigo_minutos"])))
        if ident:
            for canal in ident["canales"]:
                c.execute("insert into atencion.buzon_sandbox (customer_id, canal, mensaje) values (%s,%s,%s)",
                          (ident["customer_id"], canal, codigo))
        if limitado:
            _evento(c, "limite_alcanzado", ip, {"por_ip": por_ip, "por_documento": por_doc})
    # tiempo similar exista o no: se completa hasta un mínimo fijo
    faltante = CONFIG["tiempo_minimo_respuesta_s"] - (time.monotonic() - t0)
    if faltante > 0:
        time.sleep(faltante)
    return {"desafio_id": desafio, "estado": "codigo_enviado_si_el_documento_existe"}


def firmar(datos: dict) -> str:
    cuerpo = base64.urlsafe_b64encode(json.dumps(datos, separators=(",", ":")).encode()).decode().rstrip("=")
    firma = hmac.new(SECRETO, cuerpo.encode(), hashlib.sha256).hexdigest()
    return f"{cuerpo}.{firma}"


def leer_token(token: str | None) -> dict | None:
    """Verifica firma y vigencia. Devuelve {sub, sid, rol, exp} o None."""
    if not token or "." not in token:
        return None
    cuerpo, firma = token.rsplit(".", 1)
    if not hmac.compare_digest(firma, hmac.new(SECRETO, cuerpo.encode(), hashlib.sha256).hexdigest()):
        return None
    datos = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
    if datos.get("exp", 0) < time.time():
        return None
    return datos


def verificar_codigo(desafio_id: str, codigo: str, ip: str) -> dict:
    """Devuelve {ok, token?, intentos_restantes, bloqueado}. Tres intentos fallidos → traspaso de seguridad (N1 → N11)."""
    with transaccion("app_identidad") as c:
        d = c.execute("select * from atencion.desafios_otp where desafio_id = %s", (desafio_id,)).fetchone()
        maximo = CONFIG["max_intentos_codigo"]
        if d is None or d["consumido"] or d["vence"] < datetime.now(timezone.utc):
            return {"ok": False, "intentos_restantes": 0, "bloqueado": True}
        if d["customer_id"] and d["codigo_hash"] and hmac.compare_digest(d["codigo_hash"], _h(codigo)):
            c.execute("update atencion.desafios_otp set consumido = true where desafio_id = %s and not consumido", (desafio_id,))
            sid = "s_" + secrets.token_urlsafe(12)
            vence = datetime.now(timezone.utc) + timedelta(minutes=CONFIG["sesion_minutos"])
            c.execute("insert into atencion.sesiones (session_id, customer_id, vence) values (%s,%s,%s)",
                      (sid, d["customer_id"], vence))
            token = firmar({"sub": d["customer_id"], "sid": sid, "rol": "cliente", "exp": int(vence.timestamp())})
            return {"ok": True, "token": token, "intentos_restantes": maximo - d["intentos"]}
        intentos = d["intentos"] + 1
        c.execute("update atencion.desafios_otp set intentos = %s where desafio_id = %s", (intentos, desafio_id))
        if intentos >= maximo:
            c.execute("update atencion.desafios_otp set consumido = true where desafio_id = %s", (desafio_id,))
        _evento(c, "codigo_fallido", ip, {"intentos": intentos})
        return {"ok": False, "intentos_restantes": max(0, maximo - intentos), "bloqueado": intentos >= maximo}


def token_equipo(employee_code: str, rol: str, horas: int | None = None) -> str:
    """Token del equipo humano (asesor, supervisor, observador). En producción: inicio de sesión único con doble factor."""
    exp = time.time() + 3600 * (horas or CONFIG["sesion_equipo_horas"])
    return firmar({"sub": employee_code, "rol": rol, "exp": int(exp)})
