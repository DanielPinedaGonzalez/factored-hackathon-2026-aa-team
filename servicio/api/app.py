"""API (FastAPI): autenticación, límites y rutas de las tres interfaces (INTERFACES.md).

El sujeto sale del token; el rol se verifica en cada ruta y la base lo vuelve a verificar con su RLS. Todo texto al
cliente sale del orquestador; aquí no hay frases.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import time
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from contratos.modelos import EstadoConversacion
from servicio.asistencia_asesor import asistencia
from servicio.conocimiento import conocimiento
from servicio.datos.db import transaccion
from servicio.enrutador import enrutador
from servicio.identidad import identidad
from servicio.llm.cliente import modelo_desde_entorno
from servicio.orquestador.orquestador import Conflicto, Entrada, procesar
from servicio.redactor import formato

RAIZ = Path(__file__).resolve().parents[2]
app = FastAPI(title="AA TEAM · no reconozco este cargo", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("ORIGENES", "*").split(","), allow_methods=["*"],
                   allow_headers=["*"])
_modelo = None
DEMO_CODIGO = os.environ.get("DEMO_CODIGO")          # protege el enlace público; no es la autorización
TIPOS_ADJUNTO = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png", b"%PDF": "application/pdf",
                 b"OggS": "audio/ogg", b"ID3": "audio/mpeg"}
MAX_ADJUNTO, MAX_ADJUNTOS_CONVERSACION = 5 * 2**20, 3


def modelo():
    global _modelo
    if _modelo is None:
        _modelo = modelo_desde_entorno("sistema")
    return _modelo


# ---------------------------------------------------------------- límites y acceso

_ventanas: dict[str, deque] = defaultdict(deque)


def limite(clave: str, maximo: int, segundos: int = 60):
    ahora = time.monotonic()
    v = _ventanas[clave]
    while v and v[0] < ahora - segundos:
        v.popleft()
    if len(v) >= maximo:
        from servicio.registro.consumo import registrar_evento_seguridad
        registrar_evento_seguridad("limite_api", clave.split(":", 1)[-1] if clave.startswith("ip:") else None,
                                   clave=clave.split(":", 1)[0], maximo=maximo, segundos=segundos)
        raise HTTPException(429, "limite")
    v.append(ahora)


def acceso_demo(request: Request, x_demo_codigo: str | None = Header(default=None)):
    if DEMO_CODIGO and x_demo_codigo != DEMO_CODIGO:
        raise HTTPException(401, "codigo_de_demo")
    limite(f"ip:{request.client.host}", int(os.environ.get("LIMITE_IP_MINUTO", "60")))


def _token(authorization: str | None) -> str | None:
    return authorization.split(" ", 1)[1] if authorization and authorization.lower().startswith("bearer ") else None


def cliente_opcional(authorization: str | None = Header(default=None)) -> dict:
    tok = _token(authorization)
    claims = identidad.leer_token(tok)
    return {"token": tok if claims and claims.get("rol") == "cliente" else None, "claims": claims}


def cliente(request: Request, authorization: str | None = Header(default=None)) -> dict:
    claims = identidad.leer_token(_token(authorization))
    if not claims or claims.get("rol") != "cliente":
        from servicio.registro.consumo import registrar_evento_seguridad
        registrar_evento_seguridad("sesion_invalida", request.client.host, ruta=request.url.path,
                                   motivo="sin token" if not authorization else "token vencido, inválido o de otro rol")
        raise HTTPException(401, "sesion")
    return claims


def equipo(*roles: str):
    def dep(request: Request, authorization: str | None = Header(default=None)) -> dict:
        claims = identidad.leer_token(_token(authorization))
        if not claims or claims.get("rol") not in roles:
            from servicio.registro.consumo import registrar_evento_seguridad
            registrar_evento_seguridad("rol_negado", request.client.host, ruta=request.url.path, requeridos=list(roles),
                                       rol=(claims or {}).get("rol"), persona=(claims or {}).get("sub"))
            raise HTTPException(403, "rol")
        return claims
    return dep


@app.exception_handler(Exception)
async def incidente_no_previsto(request: Request, e: Exception):
    """Lo no previsto queda con su razón real, dónde y el rastro; al cliente, un error genérico con la referencia."""
    from servicio.registro.consumo import registrar_incidente
    ref = getattr(e, "referencia", None) if getattr(e, "registrado", False) else \
        registrar_incidente(f"api {request.method} {request.url.path}", e, severidad="critica")
    return JSONResponse({"error": "interno", "referencia": ref}, status_code=500)


class ErrorInterfaz(BaseModel):
    ruta: str
    mensaje: str
    detalle: str | None = None


@app.post("/registro/error-interfaz", dependencies=[Depends(acceso_demo)])
def error_interfaz(e: ErrorInterfaz, request: Request):
    """Lo que falla en el navegador (una llamada rechazada, un error de JavaScript) también queda con su razón."""
    limite(f"errores:{request.client.host}", 30)
    from servicio.registro.consumo import registrar_incidente
    return {"referencia": registrar_incidente(f"interfaz {e.ruta[:80]}", tipo="interfaz", severidad="advertencia",
                                              mensaje=e.mensaje[:500], detalle=(e.detalle or "")[:1500])}


# ---------------------------------------------------------------- salud

def _commit() -> str:
    if os.environ.get("RENDER_GIT_COMMIT"):
        return os.environ["RENDER_GIT_COMMIT"][:7]
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=RAIZ).stdout.strip()
    except OSError:
        return ""


@app.get("/version")
def version():
    return {"commit": _commit()}


@app.get("/health")
def salud():
    from servicio.politica import motor
    from servicio.riesgo import senal
    with transaccion("app_ejecucion") as c:
        version = c.execute("show server_version_num").fetchone()["server_version_num"]
        datos = c.execute("select data_as_of, hash_manifest from servicio.datos_version").fetchone()
        rol = c.execute("select rolbypassrls, rolsuper from pg_roles where rolname = current_user").fetchone()
    m1 = senal.artefacto() or {}
    sin_bypass = not rol["rolbypassrls"] and not rol["rolsuper"]
    return {"ok": int(version) >= 160015 and sin_bypass and bool(datos), "postgres": version, "rol_sin_bypass": sin_bypass,
            "commit": _commit(), "data_as_of": str(datos["data_as_of"]) if datos else None,
            "manifest": datos and datos["hash_manifest"], "politica": motor.version_politica(),
            "hash_politica": motor.hash_politica(), "m1": m1.get("version"), "modelo": os.environ.get("MODELO_MODO", "puente")}


# ---------------------------------------------------------------- identidad (formulario seguro)

class Desafio(BaseModel):
    documento: str


class Verificacion(BaseModel):
    desafio_id: str
    codigo: str


@app.post("/identidad/desafio", dependencies=[Depends(acceso_demo)])
def desafio(d: Desafio, request: Request):
    return identidad.pedir_codigo(d.documento, request.client.host)


@app.post("/identidad/verificar", dependencies=[Depends(acceso_demo)])
def verificar(v: Verificacion, request: Request):
    limite(f"verificar:{request.client.host}", 20)
    return identidad.verificar_codigo(v.desafio_id, v.codigo, request.client.host)


@app.get("/demo/buzon/{documento}", dependencies=[Depends(acceso_demo)])
def buzon(documento: str):
    """El 'celular' y el 'correo' del sandbox: solo para identidades de demo."""
    if not documento.upper().startswith(("DEMO-", "EVAL-")):
        raise HTTPException(404)
    with transaccion("app_identidad") as c:
        filas = c.execute("""select b.canal, b.mensaje, b.creado from atencion.buzon_sandbox b
                             join atencion.identidades_demo i using (customer_id)
                             where upper(i.documento_demo) = upper(%s) order by b.id desc limit 4""", (documento,)).fetchall()
    return filas


@app.post("/demo/reiniciar", dependencies=[Depends(acceso_demo)])
def reiniciar_demo():
    """Deja las identidades DEMO-* sin reclamos, bloqueos ni traspasos, para volver a probar desde cero."""
    limite("reiniciar", 6)
    with transaccion("app_identidad") as c:
        n = c.execute("select atencion.reiniciar_demo() n").fetchone()["n"]
    return {"reiniciadas": n}


@app.get("/demo/identidades", dependencies=[Depends(acceso_demo)])
def identidades():
    return json.loads((RAIZ / "evaluacion" / "identidades_demo.json").read_text())


# ---------------------------------------------------------------- conversación

class Turno(BaseModel):
    conversation_id: str | None = None
    texto: str | None = None
    evento: dict | None = None
    mensaje_cliente_id: str | None = None


@app.post("/conversacion/turno", dependencies=[Depends(acceso_demo)])
def turno(t: Turno, request: Request, quien: dict = Depends(cliente_opcional)):
    cid = t.conversation_id or "c_" + secrets.token_urlsafe(10)
    limite(f"conv:{cid}", int(os.environ.get("LIMITE_CONVERSACION_MINUTO", "20")))
    if t.texto is None and t.evento is None:
        raise HTTPException(422, "vacio")
    try:
        s = procesar(cid, Entrada(t.texto, t.evento, t.mensaje_cliente_id), quien["token"], modelo())
    except Conflicto:
        raise HTTPException(409, "conflicto")
    except PermissionError:
        raise HTTPException(404, "conversacion")
    return s.__dict__


@app.get("/conversacion/{conversation_id}", dependencies=[Depends(acceso_demo)])
def conversacion(conversation_id: str, desde: int = 0, quien: dict = Depends(cliente_opcional)):
    """Recupera la conversación desde la base (reconexión) y las respuestas del asesor."""
    claims = quien["claims"] if quien["token"] else None
    with transaccion("app_ejecucion", customer_id=claims and claims["sub"], conversation_id=conversation_id) as c:
        turnos = c.execute("""select n, rol, texto, respuesta, creado from atencion.turnos where conversation_id = %s and n > %s
                              order by n""", (conversation_id, desde)).fetchall()
        asesor = c.execute("""select id, texto, creado from atencion.mensajes_asesor where conversation_id = %s order by id""",
                           (conversation_id,)).fetchall()
        tr = c.execute("""select * from atencion.traspasos where conversation_id = %s
                          and estado in ('en_cola','asignado','en_atencion','esperando_cliente')""", (conversation_id,)).fetchone()
        aviso = enrutador.posicion_y_espera_con(c, tr) if tr else None
    salida = []
    for t in turnos:
        r = t["respuesta"] or {}
        if t["rol"] == "cliente":            # su propio texto, ya sin tarjetas ni secretos (A17)
            salida.append({"n": t["n"], "rol": "cliente", "texto": t["texto"]})
        else:
            salida.append({"n": t["n"], "rol": t["rol"], "texto": r.get("texto_final", ""), "ui": (r.get("salida") or {}).get("ui", [])})
    return {"turnos": salida, "asesor": [{"id": a["id"], "texto": a["texto"], "creado": a["creado"]} for a in asesor],
            "aviso_espera": aviso and {"numero": tr["numero"], **aviso}}


@app.get("/movimientos", dependencies=[Depends(acceso_demo)])
def movimientos(claims: dict = Depends(cliente), idioma: str = "es"):
    from servicio.herramientas import banco
    from servicio.orquestador.orquestador import _reloj
    with transaccion("app_ejecucion", customer_id=claims["sub"]) as c:
        hasta = c.execute("select data_as_of from servicio.datos_version").fetchone()["data_as_of"]
        reloj = _reloj(c, None, hasta, claims["sub"])            # fechas en la fecha real del cliente
        txs = [t for t in banco.listar_transacciones(c, date.fromordinal(hasta.toordinal() - 45), hasta)
               if t["fecha_hora"] <= reloj.ahora_datos]
    return [{"ref": t["transaction_id"], "movimiento": formato.movimiento(t["tipo"], idioma), "comercio": t["comercio"], "fecha": formato.fecha(reloj.a_local(t["fecha"]), idioma),
             "hora": t["hora"], "monto": formato.monto(t["monto"], t["moneda"]),
             "producto": formato.producto(t["tipo_producto"], t["ultimos4"], idioma), "estado": t["estado"]} for t in txs[:40]]


@app.post("/adjuntos", dependencies=[Depends(acceso_demo)])
async def adjuntar(conversation_id: str, archivo: UploadFile = File(...), quien: dict = Depends(cliente_opcional)):
    datos = await archivo.read(MAX_ADJUNTO + 1)
    if len(datos) > MAX_ADJUNTO:
        raise HTTPException(413, "tamano")
    tipo = next((t for firma, t in TIPOS_ADJUNTO.items() if datos.startswith(firma)), None)   # por el contenido real
    if tipo is None:
        raise HTTPException(415, "tipo")
    claims = quien["claims"] if quien["token"] else None
    aid = "adj_" + secrets.token_hex(8)
    with transaccion("app_ejecucion", customer_id=claims and claims["sub"], conversation_id=conversation_id) as c:
        n = c.execute("select count(*) n from atencion.adjuntos where conversation_id = %s", (conversation_id,)).fetchone()["n"]
        if n >= MAX_ADJUNTOS_CONVERSACION:
            raise HTTPException(429, "adjuntos")
        from servicio.canal import metadatos
        try:
            datos = metadatos.limpiar(datos, tipo)          # sin ubicación, cámara ni fecha (SEGURIDAD T-4)
        except metadatos.ArchivoIlegible:
            raise HTTPException(415, "tipo")
        c.execute("""insert into atencion.adjuntos (adjunto_id, customer_id, conversation_id, tipo, tamano, hash, contenido)
                     values (%s,%s,%s,%s,%s,%s,%s)""",
                  (aid, claims and claims["sub"], conversation_id, tipo, len(datos), hashlib.sha256(datos).hexdigest(),
                   None if tipo.startswith("audio") else datos))
    return {"adjunto_id": aid, "tipo_archivo": tipo, "tamano": len(datos)}


# ---------------------------------------------------------------- vista en vivo (rol observador)

@app.get("/traza/{conversation_id}", dependencies=[Depends(acceso_demo)])
def traza(conversation_id: str, _: dict = Depends(equipo("observador", "supervisor"))):
    with transaccion("app_observador") as c:
        return [r["registro"] for r in c.execute(
            "select registro from operacion.registro_turnos where conversation_id = %s order by n", (conversation_id,))]


MIN_CASOS_PARA_RECORRER = 5


@app.get("/corridas", dependencies=[Depends(acceso_demo)])
def corridas():
    """Corridas grabadas de la evaluación, para el modo "paso a paso" (no gasta cupo)."""
    carpeta = RAIZ / "evaluacion" / "corridas"
    salida = []
    for f in sorted(carpeta.glob("*.json"), reverse=True):
        d = json.loads(f.read_text())
        if len(d["resultados"]) < MIN_CASOS_PARA_RECORRER:       # una repetición de un caso no sirve para recorrer
            continue
        if len(salida) >= 20:
            break
        salida.append({"archivo": f.name, "sistema": d["sistema"], "conjunto": d["conjunto"], "fecha": d["fecha"],
                       "casos": [{"caso": r["caso"], "paso": r["paso"]} for r in d["resultados"]]})
    return salida


@app.get("/corridas/{archivo}/{caso}", dependencies=[Depends(acceso_demo)])
def corrida_caso(archivo: str, caso: str):
    f = RAIZ / "evaluacion" / "corridas" / Path(archivo).name
    if not f.exists():
        raise HTTPException(404)
    d = json.loads(f.read_text())
    r = next((x for x in d["resultados"] if x["caso"] == caso), None)
    conv = d["conversaciones"].get(caso) or {}
    if isinstance(conv, list):
        conv = {"salidas": conv, "registros": []}
    import yaml
    esperado = next((c for c in yaml.safe_load((RAIZ / "evaluacion" / "ground_truth_cases.yaml").read_text())["casos"]
                     if c["id"] == caso), {})
    return {"resultado": r, "salidas": conv["salidas"], "registros": conv["registros"],
            "esperado": {k: esperado.get(k) for k in ("meta", "expected_tool_calls", "expected_state", "must_escalate",
                                                      "forbidden_actions", "protocolo", "primer_mensaje")}}


class Personaje(BaseModel):
    caso: str


@app.post("/demo/personaje", dependencies=[Depends(acceso_demo)])
def personaje(p: Personaje):
    """Solo en local (PERSONAJES=1): un personaje conversa solo con el sistema para la vista en vivo y el video."""
    if os.environ.get("PERSONAJES") != "1":
        raise HTTPException(404)
    import yaml
    from evaluacion import personajes
    from servicio.llm.cliente import modelo_desde_entorno as mde
    caso = next(c for c in yaml.safe_load((RAIZ / "evaluacion" / "ground_truth_cases.yaml").read_text())["casos"] if c["id"] == p.caso)
    datos = json.loads((RAIZ / "evaluacion" / "manifest_casos.json").read_text())["casos"][p.caso]["desarrollo"]
    modo = os.environ.get("MODELO_MODO")
    os.environ["MODELO_MODO"] = "simulador"
    simulador = mde("simulador")
    os.environ["MODELO_MODO"] = modo or "groq"
    return {"id": personajes.iniciar(caso, datos, modelo(), simulador, f"EVAL-{p.caso}-DES")}


@app.get("/demo/personaje/{pid}", dependencies=[Depends(acceso_demo)])
def personaje_avance(pid: str):
    from evaluacion import personajes
    if pid not in personajes.CORRIDAS:
        raise HTTPException(404)
    return personajes.CORRIDAS[pid]


# ---------------------------------------------------------------- equipo humano

class Entrar(BaseModel):
    employee_code: str
    rol: str = "asesor"


@app.post("/equipo/entrar", dependencies=[Depends(acceso_demo)])
def entrar(e: Entrar):
    """Entrada de la demo para el equipo (declarada): en producción, inicio de sesión único con doble factor."""
    if e.rol not in ("asesor", "supervisor", "observador"):
        raise HTTPException(422)
    if e.rol == "asesor":
        with transaccion("app_supervisor") as c:
            a = c.execute("select * from atencion.asesores where employee_code = %s and demo", (e.employee_code,)).fetchone()
        if not a:
            raise HTTPException(403, "no es una identidad de demo")
    return {"token": identidad.token_equipo(e.employee_code, e.rol)}


class Presencia(BaseModel):
    presencia: str
    capacidad: int = 2


@app.post("/equipo/presencia")
def presencia(p: Presencia, claims: dict = Depends(equipo("asesor"))):
    with transaccion("app_asesor", asesor_id=claims["sub"]) as c:
        c.execute("insert into atencion.asesor_presencia_eventos (employee_code, presencia, capacidad) values (%s,%s,%s)",
                  (claims["sub"], p.presencia, p.capacidad))
    return {"asignados": enrutador.asignar()}


@app.get("/equipo/cola")
def cola_equipo(claims: dict = Depends(equipo("asesor", "supervisor", "observador"))):
    enrutador.asignar()
    rol = {"asesor": "app_asesor", "supervisor": "app_supervisor", "observador": "app_observador"}[claims["rol"]]
    with transaccion(rol, asesor_id=claims["sub"]) as c:
        cola = c.execute("select * from atencion.cola_enmascarada order by prioridad, llegada").fetchall()
        mios = c.execute("""select traspaso_id, numero, habilidad, idioma, prioridad, estado, llegada, primera_respuesta_vence
                            from atencion.traspasos where asesor = %s and estado in ('asignado','en_atencion','esperando_cliente')""",
                         (claims["sub"],)).fetchall() if claims["rol"] == "asesor" else []
        yo = c.execute("""select a.employee_code, a.habilidad, a.idiomas, a.turno, a.pais, coalesce(p.presencia, 'desconectado') as presencia
                          from atencion.asesores a left join lateral (select presencia from atencion.asesor_presencia_eventos e
                          where e.employee_code = a.employee_code order by id desc limit 1) p on true
                          where a.employee_code = %s""", (claims["sub"],)).fetchone() if claims["rol"] == "asesor" else None
    return {"cola": cola, "mios": mios, "yo": yo}


@app.get("/equipo/caso/{traspaso_id}")
def caso(traspaso_id: str, refresco: bool = False, claims: dict = Depends(equipo("asesor", "supervisor"))):
    rol = "app_asesor" if claims["rol"] == "asesor" else "app_supervisor"
    with transaccion(rol, asesor_id=claims["sub"]) as c:
        t = c.execute("select * from atencion.traspasos where traspaso_id = %s", (traspaso_id,)).fetchone()
        if not t:
            raise HTTPException(404)
        if not refresco:             # la apertura queda auditada; el refresco de la misma pantalla no la repite
            c.execute("insert into operacion.accesos_pii (persona, rol, traspaso_id, motivo) values (%s,%s,%s,'caso asignado')",
                      (claims["sub"], claims["rol"], traspaso_id))
        turnos = c.execute("select n, rol, texto, respuesta from atencion.turnos where conversation_id = %s order by n",
                           (t["conversation_id"],)).fetchall()
        mensajes = c.execute("select texto, origen, creado from atencion.mensajes_asesor where traspaso_id = %s order by id",
                             (traspaso_id,)).fetchall()
    conversacion_ = [{"n": x["n"], "rol": x["rol"], "texto": x["texto"] if x["rol"] == "cliente" else (x["respuesta"] or {}).get("texto_final", x["texto"]),
                      "es_cita_del_cliente": x["rol"] == "cliente"} for x in turnos]
    return {"traspaso": {k: t[k] for k in ("traspaso_id", "numero", "habilidad", "idioma", "prioridad", "estado",
                                           "primera_respuesta_vence", "nivel_desborde")},
            "paquete": t["paquete"], "conversacion": conversacion_, "mensajes": mensajes, "guia": asistencia.guia(t["paquete"])}


@app.post("/equipo/caso/{traspaso_id}/tomar")
def tomar(traspaso_id: str, claims: dict = Depends(equipo("asesor"))):
    with transaccion("app_asesor", asesor_id=claims["sub"]) as c:
        n = c.execute("""update atencion.traspasos set estado = 'en_atencion', version = version + 1
                         where traspaso_id = %s and asesor = %s and estado = 'asignado'""", (traspaso_id, claims["sub"])).rowcount
        if n:
            c.execute("insert into atencion.traspaso_eventos (traspaso_id, evento, autor) values (%s,'tomado',%s)", (traspaso_id, claims["sub"]))
    return {"ok": bool(n)}


class Mensaje(BaseModel):
    texto: str
    origen: str = "escrito"


@app.post("/equipo/caso/{traspaso_id}/mensaje")
def mensaje(traspaso_id: str, m: Mensaje, claims: dict = Depends(equipo("asesor"))):
    if m.origen not in ("escrito", "sugerido_sin_editar", "sugerido_editado"):
        raise HTTPException(422)
    with transaccion("app_asesor", asesor_id=claims["sub"]) as c:
        t = c.execute("select conversation_id, customer_id from atencion.traspasos where traspaso_id = %s", (traspaso_id,)).fetchone()
        if not t:
            raise HTTPException(404)
        c.execute("""insert into atencion.mensajes_asesor (traspaso_id, conversation_id, customer_id, asesor, texto, origen)
                     values (%s,%s,%s,%s,%s,%s)""", (traspaso_id, t["conversation_id"], t["customer_id"], claims["sub"], m.texto, m.origen))
        c.execute("update atencion.traspasos set estado = 'en_atencion' where traspaso_id = %s and estado = 'asignado'", (traspaso_id,))
    return {"ok": True}


@app.post("/equipo/caso/{traspaso_id}/sugerir")
def sugerir(traspaso_id: str, claims: dict = Depends(equipo("asesor"))):
    with transaccion("app_asesor", asesor_id=claims["sub"]) as c:
        t = c.execute("select * from atencion.traspasos where traspaso_id = %s", (traspaso_id,)).fetchone()
        if not t:
            raise HTTPException(404)
        est = c.execute("select estado from atencion.estado_conversacion where conversation_id = %s", (t["conversation_id"],)).fetchone()
    estado = EstadoConversacion.model_validate(est["estado"]) if est else EstadoConversacion(conversation_id=t["conversation_id"])
    r = asistencia.borrador(modelo(), estado, t["paquete"], t["idioma"])
    with transaccion("app_asesor", asesor_id=claims["sub"]) as c:      # quién pidió la sugerencia, con qué modelo y prompt
        c.execute("insert into atencion.traspaso_eventos (traspaso_id, evento, autor, detalle) values (%s,'sugerencia_ia',%s,%s)",
                  (traspaso_id, claims["sub"], json.dumps({"ok": r["ok"], "hash_prompt": r.get("origen_prompt"),
                                                           "motivo": r.get("motivo"), "llamadas": r["llamadas"]})))
    return r


class Transferencia(BaseModel):
    habilidad: str
    nota: str


@app.post("/equipo/caso/{traspaso_id}/transferir")
def transferir(traspaso_id: str, tr: Transferencia, claims: dict = Depends(equipo("asesor", "supervisor"))):
    if not tr.nota.strip() or tr.habilidad not in ("fraude", "reclamos", "general"):
        raise HTTPException(422, "no existe la transferencia sin nota")
    rol = "app_asesor" if claims["rol"] == "asesor" else "app_supervisor"
    import psycopg
    try:
        with transaccion(rol, asesor_id=claims["sub"]) as c:
            c.execute("select atencion.transferir(%s, %s, %s, %s, %s)",
                      (traspaso_id, tr.habilidad, tr.nota, claims["sub"], claims["rol"] == "supervisor"))
    except psycopg.errors.RaiseException as e:
        from servicio.registro.consumo import registrar_evento_seguridad
        registrar_evento_seguridad("transferencia_negada", None, traspaso=traspaso_id, persona=claims["sub"],
                                   habilidad=tr.habilidad, razon=str(e).split("\n")[0])
        raise HTTPException(404 if "NO_ENCONTRADO" in str(e) or "NO_AUTORIZADO" in str(e) else 422, str(e).split("\n")[0])
    enrutador.asignar()
    return {"ok": True}


@app.post("/equipo/caso/{traspaso_id}/desbloquear")
def desbloquear_tras_riesgo(traspaso_id: str, claims: dict = Depends(equipo("asesor"))):
    """Acción reservada a la habilidad `fraude` (ROLES_Y_ACCESOS §2), validada aquí y no solo en la interfaz."""
    with transaccion("app_asesor", asesor_id=claims["sub"]) as c:
        a = c.execute("select habilidad from atencion.asesores where employee_code = %s", (claims["sub"],)).fetchone()
        permitido = bool(a and a["habilidad"] == "fraude")
        if not permitido:            # el evento queda aunque la acción se niegue
            c.execute("insert into operacion.eventos_seguridad (tipo, detalle) values ('rol_negado', %s)",
                      (json.dumps({"accion": "desbloquear_tras_riesgo", "asesor": claims["sub"]}),))
    if not permitido:
        raise HTTPException(403, "NO_PERMITIDO")
    with transaccion("app_asesor", asesor_id=claims["sub"]) as c:
        t = c.execute("select customer_id from atencion.traspasos where traspaso_id = %s", (traspaso_id,)).fetchone()
        if not t:
            raise HTTPException(404)
        b = c.execute("select * from atencion.bloqueos where customer_id = %s and estado = 'bloqueado_temporal'",
                      (t["customer_id"],)).fetchone()
        if not b:
            return {"ok": True, "estado": "activo"}
        c.execute("update atencion.bloqueos set estado = 'activo', version = version + 1 where bloqueo_id = %s and version = %s",
                  (b["bloqueo_id"], b["version"]))
        c.execute("""insert into atencion.bloqueo_eventos (bloqueo_id, customer_id, estado_anterior, estado_nuevo, autor_tipo, autor, motivo)
                     values (%s,%s,'bloqueado_temporal','activo','asesor',%s,'desbloqueo tras riesgo revisado')""",
                  (b["bloqueo_id"], t["customer_id"], claims["sub"]))
    return {"ok": True, "estado": "activo"}


class Cierre(BaseModel):
    nota: str
    devolver: bool = False


@app.post("/equipo/caso/{traspaso_id}/cerrar")
def cerrar(traspaso_id: str, ci: Cierre, claims: dict = Depends(equipo("asesor"))):
    with transaccion("app_asesor", asesor_id=claims["sub"]) as c:
        t = c.execute("select * from atencion.traspasos where traspaso_id = %s", (traspaso_id,)).fetchone()
        if not t:
            raise HTTPException(404)
        nuevo = "devuelto_al_sistema" if ci.devolver else "resuelto"
        n = c.execute("""update atencion.traspasos set estado = %s, version = version + 1 where traspaso_id = %s
                         and asesor = %s and estado in ('asignado','en_atencion','esperando_cliente')""",
                      (nuevo, traspaso_id, claims["sub"])).rowcount
        if n == 0:                   # ya cerrado, transferido o de otro asesor: la carga no se toca dos veces
            raise HTTPException(409, "NO_ASIGNADO")
        c.execute("update atencion.asesor_carga set carga = greatest(carga - 1, 0) where employee_code = %s", (claims["sub"],))
        c.execute("insert into atencion.traspaso_eventos (traspaso_id, evento, autor, detalle) values (%s,%s,%s,%s)",
                  (traspaso_id, nuevo, claims["sub"], json.dumps({"nota": ci.nota})))
        c.execute("update atencion.conversaciones set estado = %s where conversation_id = %s",
                  ("abierta" if ci.devolver else "cerrada", t["conversation_id"]))
    return {"ok": True}


@app.get("/equipo/caso/{traspaso_id}/adjunto/{adjunto_id}")
def ver_adjunto(traspaso_id: str, adjunto_id: str, claims: dict = Depends(equipo("asesor", "supervisor"))):
    """El adjunto es evidencia para la persona (la IA no lo lee); cada vista queda en accesos_pii."""
    from fastapi.responses import Response
    rol = "app_asesor" if claims["rol"] == "asesor" else "app_supervisor"
    with transaccion(rol, asesor_id=claims["sub"]) as c:
        t = c.execute("select conversation_id from atencion.traspasos where traspaso_id = %s", (traspaso_id,)).fetchone()
        a = t and c.execute("select tipo, contenido from atencion.adjuntos where adjunto_id = %s and conversation_id = %s",
                            (adjunto_id, t["conversation_id"])).fetchone()
        if not a or a["contenido"] is None:
            raise HTTPException(404)
        c.execute("insert into operacion.accesos_pii (persona, rol, traspaso_id, motivo) values (%s,%s,%s,'adjunto del caso')",
                  (claims["sub"], claims["rol"], traspaso_id))
    # El PDF solo como descarga (nunca se abre en el navegador del asesor); la imagen, en línea. Sin sniffing y con una política que no deja ejecutar nada.
    descarga = a["tipo"] == "application/pdf"
    return Response(bytes(a["contenido"]), media_type=a["tipo"], headers={
        "Content-Disposition": f'{"attachment" if descarga else "inline"}; filename="adjunto-{adjunto_id[-6:]}.{"pdf" if descarga else a["tipo"].split("/")[1]}"',
        "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; img-src 'self' data: blob:; sandbox"})


@app.get("/equipo/conocimiento")
def buscar_conocimiento(q: str, claims: dict = Depends(equipo("asesor", "supervisor"))):
    rol = "app_asesor" if claims["rol"] == "asesor" else "app_supervisor"
    with transaccion(rol, asesor_id=claims["sub"]) as c:
        pub = conocimiento.buscar(c, q, None, "es", date.today(), "publico", 3)
        inter = conocimiento.buscar(c, q, None, "es", date.today(), "interno", 3)
    return [{"id": a["id"], "titulo": a["titulo"], "cuerpo": a["cuerpo"]} for a in inter + pub]


# ---------------------------------------------------------------- investigación en back-office (PROCESOS §P3)

def _reloj_equipo(c):
    from servicio.resolutor.reloj import Reloj
    data_as_of = c.execute("select data_as_of from servicio.datos_version").fetchone()["data_as_of"]
    return Reloj.vivo(enrutador.config()["zona_horaria_por_defecto"], data_as_of)


def _fecha_equipo(c, d) -> str | None:
    """Una fecha del marco de los datos (plazos), en la fecha real, como la ve el cliente (ARQUITECTURA §8.10)."""
    from servicio.redactor import formato
    return None if d is None else formato.fecha(_reloj_equipo(c).a_local(d), "es")


def _plazo_de_investigacion(c, f: dict) -> dict:
    """PROCESOS §P3: el plazo del país, o el interno declarado si la regla del país es desconocida; los días hábiles
    que quedan y la alarma (2 o menos, o vencido)."""
    from datetime import timedelta
    from servicio.redactor import formato
    from servicio.resolutor.calendario import dias_habiles_entre
    reloj = _reloj_equipo(c)
    if f.get("plazo_vence"):
        vence, origen = reloj.a_local(f["plazo_vence"]), "regla del país"
    else:
        vence = f["creado"].date() + timedelta(days=enrutador.config()["plazo_interno_investigacion_dias"])
        origen = "plazo interno"
    hoy = reloj.hoy_local
    quedan = -dias_habiles_entre(vence, hoy, f.get("pais") or "CO") if vence < hoy else dias_habiles_entre(hoy, vence, f.get("pais") or "CO")
    return {"plazo": formato.fecha(vence, "es"), "plazo_origen": origen, "dias_habiles_restantes": quedan, "alarma": quedan <= 2}


def _error_de_base(e: Exception) -> HTTPException:
    texto = str(e).split("\n")[0]
    return HTTPException(409 if "CONFLICTO" in texto else 422 if "NO_PERMITIDO" in texto else 404, texto)


@app.get("/equipo/reclamos")
def cola_de_reclamos(claims: dict = Depends(equipo("asesor", "supervisor"))):
    """La cola de su habilidad, sin datos del cliente, y los reclamos que ya tomó."""
    rol = "app_asesor" if claims["rol"] == "asesor" else "app_supervisor"
    with transaccion(rol, asesor_id=claims["sub"]) as c:
        a = c.execute("select habilidad, demo from atencion.asesores where employee_code = %s", (claims["sub"],)).fetchone()
        # La demo declara que sus identidades reciben casos de cualquier habilidad (config/atencion_humana.yaml): también en el back-office.
        cualquiera = bool(a and a["demo"] and enrutador.config().get("asesores_demo_cualquier_habilidad", False))
        habilidades = [a["habilidad"]] if a and claims["rol"] == "asesor" and not cualquiera else ["fraude", "reclamos"]
        cola = [dict(f) for h in habilidades for f in c.execute("select * from atencion.cola_reclamos(%s)", (h,)).fetchall()]
        mios = c.execute("""select r.reclamo_id, r.numero, r.tipo_disputa, r.prioridad, r.estado, r.plazo_vence, r.creado, cl.pais
                            from atencion.reclamos r left join servicio.clientes cl using (customer_id)
                            where r.asesor = %s and r.estado not in ('cerrado','retirado') order by r.prioridad, r.creado""",
                         (claims["sub"],)).fetchall()
        for f in cola + mios:
            f.update(_plazo_de_investigacion(c, f))
            for k in ("plazo_vence", "creado", "pais"):
                f.pop(k, None)
    return {"cola": cola, "mios": mios, "por_vencer": sum(1 for f in cola + mios if f["alarma"])}


@app.post("/equipo/reclamos/siguiente")
def tomar_siguiente(claims: dict = Depends(equipo("asesor"))):
    import psycopg
    try:
        with transaccion("app_asesor", asesor_id=claims["sub"]) as c:
            demo = c.execute("select demo from atencion.asesores where employee_code = %s", (claims["sub"],)).fetchone()
            cualquiera = bool(demo and demo["demo"] and enrutador.config().get("asesores_demo_cualquier_habilidad", False))
            rid = c.execute("select atencion.tomar_siguiente_reclamo(%s, %s) r", (claims["sub"], cualquiera)).fetchone()["r"]
    except psycopg.errors.RaiseException as e:
        raise _error_de_base(e)
    return {"reclamo_id": rid}


@app.get("/equipo/reclamos/{reclamo_id}")
def reclamo_en_investigacion(reclamo_id: str, claims: dict = Depends(equipo("asesor", "supervisor"))):
    """El reclamo, su movimiento, sus notas, sus eventos y sus adjuntos. El asesor lo ve solo si lo tomó (RLS)."""
    from servicio.redactor import formato
    rol = "app_asesor" if claims["rol"] == "asesor" else "app_supervisor"
    with transaccion(rol, asesor_id=claims["sub"]) as c:
        r = c.execute("select * from atencion.reclamos where reclamo_id = %s", (reclamo_id,)).fetchone()
        if not r:
            raise HTTPException(404)
        c.execute("insert into operacion.accesos_pii (persona, rol, traspaso_id, motivo) values (%s,%s,null,%s)",
                  (claims["sub"], claims["rol"], f"investigación de {r['numero']}"))
        t = c.execute("""select t.*, p.tipo as tipo_producto, p.ultimos4 from servicio.transacciones t
                         left join servicio.productos p using (product_id) where t.transaction_id = %s""", (r["transaction_id"],)).fetchone()
        notas = c.execute("select autor_tipo, texto, adjunto_id, creado from atencion.reclamo_notas where reclamo_id = %s order by id",
                          (reclamo_id,)).fetchall()
        eventos = c.execute("""select estado_anterior, estado_nuevo, autor_tipo, autor, motivo, creado from atencion.reclamo_eventos
                               where reclamo_id = %s order by id""", (reclamo_id,)).fetchall()
        adjuntos = c.execute("select adjunto_id, tipo, tamano from atencion.adjuntos where reclamo_id = %s", (reclamo_id,)).fetchall()
        plazo = _fecha_equipo(c, r["plazo_vence"])
    movimiento = t and {"movimiento": formato.movimiento(t["tipo"], "es"), "comercio": t["comercio"], "ciudad": t["ciudad"],
                        "monto": formato.monto(float(t["monto"]) if t["monto"] is not None else None, t["moneda"]),
                        "producto": formato.producto(t["tipo_producto"], t["ultimos4"], "es"), "canal": t["canal"],
                        "estado": t["estado"], "fraud_score": t["fraud_score"]}
    return {"reclamo": {k: r[k] for k in ("reclamo_id", "numero", "estado", "tipo_disputa", "prioridad", "habilidad",
                                           "explicacion", "documentos", "referencia_abono", "version")} | {"plazo": plazo},
            "movimiento": movimiento, "notas": notas, "eventos": eventos, "adjuntos": adjuntos}


class PedirInformacion(BaseModel):
    nota: str


class Decision(BaseModel):
    decision: str
    explicacion: str = ""
    documentos: list[str] = []


class Abono(BaseModel):
    referencia: str


def _transicion(rol: str, claims: dict, reclamo_id: str, nuevo: str, motivo: str, antes=None) -> None:
    """Cambio de estado del reclamo por la función de la base (escritura condicional, evento y aviso al cliente)."""
    import psycopg
    try:
        with transaccion(rol, asesor_id=claims["sub"]) as c:
            r = c.execute("select version, asesor from atencion.reclamos where reclamo_id = %s", (reclamo_id,)).fetchone()
            if not r or (claims["rol"] == "asesor" and r["asesor"] != claims["sub"]):
                raise HTTPException(404)
            if antes:
                antes(c)
            c.execute("select atencion.transicion_reclamo(%s, %s, 'asesor', %s, %s, %s)",
                      (reclamo_id, nuevo, claims["sub"], motivo, r["version"]))
    except (psycopg.errors.RaiseException, psycopg.errors.CheckViolation) as e:
        raise _error_de_base(e) if isinstance(e, psycopg.errors.RaiseException) else HTTPException(422, "negativa sin explicación")


@app.post("/equipo/reclamos/{reclamo_id}/pedir-informacion")
def pedir_informacion(reclamo_id: str, p: PedirInformacion, claims: dict = Depends(equipo("asesor"))):
    """Pasa a esperando_cliente con la nota; el cliente recibe el aviso. El plazo lo decide el banco (parámetro)."""
    if not p.nota.strip():
        raise HTTPException(422, "la solicitud necesita una nota")

    def nota(c):
        cliente = c.execute("select customer_id from atencion.reclamos where reclamo_id = %s", (reclamo_id,)).fetchone()["customer_id"]
        c.execute("insert into atencion.reclamo_notas (reclamo_id, customer_id, autor_tipo, texto) values (%s,%s,'asesor',%s)",
                  (reclamo_id, cliente, p.nota.strip()))
    _transicion("app_asesor", claims, reclamo_id, "esperando_cliente", p.nota.strip(), nota)
    return {"ok": True}


@app.post("/equipo/reclamos/{reclamo_id}/decidir")
def decidir_reclamo(reclamo_id: str, d: Decision, claims: dict = Depends(equipo("asesor"))):
    """El fondo lo decide una persona. Una negativa exige explicación y documentos (la base lo impone)."""
    if d.decision not in ("resuelto_a_favor", "resuelto_en_contra", "no_procede"):
        raise HTTPException(422, "decisión desconocida")
    if d.decision != "resuelto_a_favor" and not (d.explicacion.strip() and d.documentos):
        raise HTTPException(422, "una negativa necesita explicación y documentos")

    def fundamento(c):
        c.execute("update atencion.reclamos set explicacion = %s, documentos = %s where reclamo_id = %s",
                  (d.explicacion.strip() or None, d.documentos or None, reclamo_id))
    _transicion("app_asesor", claims, reclamo_id, d.decision, d.explicacion.strip() or "decisión del asesor", fundamento)
    return {"ok": True}


@app.post("/equipo/reclamos/{reclamo_id}/abono")
def registrar_abono(reclamo_id: str, a: Abono, claims: dict = Depends(equipo("asesor"))):
    """El dinero lo mueve el back-office del banco, fuera del sistema; aquí se registra su referencia."""
    with transaccion("app_asesor", asesor_id=claims["sub"]) as c:
        n = c.execute("""update atencion.reclamos set referencia_abono = %s where reclamo_id = %s and asesor = %s
                         and estado = 'resuelto_a_favor'""", (a.referencia.strip(), reclamo_id, claims["sub"])).rowcount
    if not n or not a.referencia.strip():
        raise HTTPException(422, "el abono se registra solo en un reclamo resuelto a favor y propio")
    return {"ok": True}


@app.post("/equipo/reclamos/{reclamo_id}/cerrar")
def cerrar_reclamo(reclamo_id: str, claims: dict = Depends(equipo("asesor"))):
    """Solo un reclamo decidido y propio; la función de la base deja el evento y el aviso al cliente."""
    import psycopg
    try:
        with transaccion("app_asesor", asesor_id=claims["sub"]) as c:
            c.execute("select atencion.cerrar_reclamo_decidido(%s, %s)", (reclamo_id, claims["sub"]))
    except psycopg.errors.RaiseException as e:
        raise _error_de_base(e)
    return {"ok": True}


class CorreccionTipo(BaseModel):
    tipo_disputa: str
    motivo: str


@app.post("/equipo/reclamos/{reclamo_id}/tipo")
def corregir_tipo(reclamo_id: str, ct: CorreccionTipo, claims: dict = Depends(equipo("asesor"))):
    """El tipo de disputa lo confirma una persona; pasar a no_autorizada o estafa_autorizada es de la habilidad fraude
    (ROLES_Y_ACCESOS §2). Queda como nota del reclamo, con el tipo anterior y el motivo."""
    from contratos import catalogo
    if ct.tipo_disputa not in catalogo.cargar()["tipos_disputa"] or not ct.motivo.strip():
        raise HTTPException(422, "tipo desconocido o sin motivo")
    with transaccion("app_asesor", asesor_id=claims["sub"]) as c:
        a = c.execute("select habilidad from atencion.asesores where employee_code = %s", (claims["sub"],)).fetchone()
        if ct.tipo_disputa in ("no_autorizada", "estafa_autorizada") and (not a or a["habilidad"] != "fraude"):
            raise HTTPException(403, "NO_PERMITIDO: confirmar ese tipo es de la habilidad fraude")
        r = c.execute("select tipo_disputa, customer_id from atencion.reclamos where reclamo_id = %s and asesor = %s",
                      (reclamo_id, claims["sub"])).fetchone()
        if not r:
            raise HTTPException(404)
        c.execute("update atencion.reclamos set tipo_disputa = %s, version = version + 1 where reclamo_id = %s", (ct.tipo_disputa, reclamo_id))
        c.execute("insert into atencion.reclamo_notas (reclamo_id, customer_id, autor_tipo, texto) values (%s,%s,'asesor',%s)",
                  (reclamo_id, r["customer_id"], f"tipo corregido de {r['tipo_disputa']} a {ct.tipo_disputa}: {ct.motivo.strip()}"))
    return {"ok": True}


class Reapertura(BaseModel):
    motivo: str


@app.post("/supervisor/reclamos/{reclamo_id}/reabrir")
def reabrir_reclamo(reclamo_id: str, r: Reapertura, claims: dict = Depends(equipo("supervisor"))):
    """Revisión pedida por el cliente o hallazgo nuevo: vuelve a en_revision con motivo (MODELO_DATOS §3.1)."""
    if not r.motivo.strip():
        raise HTTPException(422, "reabrir exige motivo")
    if reclamo_id.startswith("R-"):          # el supervisor escribe el número que ve en pantalla
        with transaccion("app_supervisor", asesor_id=claims["sub"]) as c:
            f = c.execute("select reclamo_id from atencion.reclamos where numero = %s", (reclamo_id,)).fetchone()
        if not f:
            raise HTTPException(404, "no existe")
        reclamo_id = f["reclamo_id"]
    _transicion("app_supervisor", claims, reclamo_id, "en_revision", r.motivo.strip())
    return {"ok": True}


class Reasignacion(BaseModel):
    asesor: str
    nota: str


@app.post("/supervisor/caso/{traspaso_id}/reasignar")
def reasignar(traspaso_id: str, ra: Reasignacion, claims: dict = Depends(equipo("supervisor"))):
    """El supervisor asigna un caso en vivo a un asesor concreto, con nota; la carga de los dos se ajusta en la misma
    transacción y queda el evento. El asesor destino debe hablar el idioma del caso."""
    if not ra.nota.strip():
        raise HTTPException(422, "no existe la reasignación sin nota")
    with transaccion("app_enrutador") as c:
        t = c.execute("""select * from atencion.traspasos where (traspaso_id = %s or numero = %s)
                         and estado in ('en_cola','asignado','en_atencion','esperando_cliente')""", (traspaso_id, traspaso_id)).fetchone()
        a = c.execute("select * from atencion.asesores where employee_code = %s", (ra.asesor,)).fetchone()
        if not t or not a:
            raise HTTPException(404)
        if t["idioma"] not in a["idiomas"]:
            raise HTTPException(422, "el asesor no habla el idioma del caso")
        if t["asesor"]:
            c.execute("update atencion.asesor_carga set carga = greatest(carga - 1, 0) where employee_code = %s", (t["asesor"],))
        c.execute("update atencion.asesor_carga set carga = carga + 1, ultima_asignacion = now() where employee_code = %s", (ra.asesor,))
        c.execute("""update atencion.traspasos set asesor = %s, estado = 'asignado', asignado_en = now(), version = version + 1
                     where traspaso_id = %s""", (ra.asesor, t["traspaso_id"]))
        c.execute("insert into atencion.traspaso_eventos (traspaso_id, evento, autor, detalle) values (%s,'reasignado',%s,%s)",
                  (t["traspaso_id"], claims["sub"], json.dumps({"de": t["asesor"], "a": ra.asesor, "nota": ra.nota.strip()})))
    return {"ok": True}


class PresenciaDeOtro(BaseModel):
    presencia: str
    capacidad: int = 2


@app.post("/supervisor/asesor/{employee_code}/presencia")
def cambiar_presencia(employee_code: str, p: PresenciaDeOtro, claims: dict = Depends(equipo("supervisor"))):
    """El supervisor cambia la presencia de un asesor (pausa, desconexión); queda el evento como cualquier cambio."""
    if p.presencia not in ("desconectado", "disponible", "en_pausa", "ausente") or not 1 <= p.capacidad <= 3:
        raise HTTPException(422, "presencia o capacidad fuera de rango")
    with transaccion("app_supervisor", asesor_id=claims["sub"]) as c:
        if not c.execute("select 1 from atencion.asesores where employee_code = %s", (employee_code,)).fetchone():
            raise HTTPException(404)
        c.execute("insert into atencion.asesor_presencia_eventos (employee_code, presencia, capacidad) values (%s,%s,%s)",
                  (employee_code, p.presencia, p.capacidad))
    return {"asignados": enrutador.asignar()}


class Marca(BaseModel):
    marca: str
    nota: str = ""
    traspaso_id: str | None = None


@app.post("/equipo/conocimiento/{articulo}/marca")
def marcar_articulo(articulo: str, m: Marca, claims: dict = Depends(equipo("asesor", "supervisor"))):
    """PROCESOS §P7: el asesor marca un artículo incorrecto, incompleto o que falta, con el caso de ejemplo."""
    if m.marca not in ("incorrecto", "incompleto", "falta"):
        raise HTTPException(422, "marca desconocida")
    rol = "app_asesor" if claims["rol"] == "asesor" else "app_supervisor"
    with transaccion(rol, asesor_id=claims["sub"]) as c:
        c.execute("insert into atencion.conocimiento_marcas (articulo, asesor, marca, traspaso_id, nota) values (%s,%s,%s,%s,%s)",
                  (articulo, claims["sub"], m.marca, m.traspaso_id, m.nota.strip() or None))
    return {"ok": True}


@app.get("/supervisor/indicadores")
def indicadores_operacion(horas: int = 24, evaluacion: bool = False, pruebas: bool = False,
                          claims: dict = Depends(equipo("supervisor", "observador"))):
    """Colas, alarma sin modelo e indicadores de las últimas horas, calculados del registro (A13) y de A14."""
    from servicio.registro import indicadores, parametros
    rol = "app_supervisor" if claims["rol"] == "supervisor" else "app_observador"
    datos = indicadores.leer(rol, max(1, min(horas, 24 * 30)), evaluacion, incluir_pruebas=pruebas)
    with transaccion(rol) as c:
        datos["parametros"] = parametros.listar(c)
    return datos


@app.get("/sistema")
def sistema(horas: int = 24, claims: dict = Depends(equipo("supervisor", "observador"))):
    """La cabina: ¿está sano?, pool de llaves y cupo, consumo y gasto, fallos y lo que necesita atención."""
    from servicio.registro import sistema as cab
    modelo()                                 # crea el pool si todavía no hubo turnos (no llama al proveedor)
    return cab.cabina("app_supervisor" if claims["rol"] == "supervisor" else "app_observador", max(1, min(horas, 24 * 30)))


class CambioParametro(BaseModel):
    valor: int
    motivo: str


@app.put("/supervisor/parametros/{clave}")
def cambiar_parametro(clave: str, p: CambioParametro, claims: dict = Depends(equipo("supervisor"))):
    """Un parámetro de operación lo decide el banco (PROCESOS §P9): lo cambia un supervisor, con motivo; queda el evento."""
    from servicio.registro import parametros as par
    with transaccion("app_supervisor", asesor_id=claims["sub"]) as c:
        try:
            par.cambiar(c, clave, p.valor, claims["sub"], p.motivo)
        except par.ValorInvalido as e:
            raise HTTPException(422, str(e))
        return {"parametros": par.listar(c)}


@app.get("/supervisor/auditoria/{ref}")
def auditoria(ref: str, claims: dict = Depends(equipo("supervisor"))):
    """Quién hizo qué, dónde, cuándo y con qué resultado en una conversación (A13). El acceso queda registrado."""
    from servicio.registro import auditoria as aud
    cid = aud.resolver_referencia(ref)
    if cid is None:
        raise HTTPException(404)
    with transaccion("app_supervisor", asesor_id=claims["sub"]) as c:
        c.execute("insert into operacion.accesos_pii (persona, rol, traspaso_id, motivo) values (%s,%s,null,%s)",
                  (claims["sub"], claims["rol"], f"auditoría de {cid}"))
    return aud.linea_de_tiempo(cid)


# ---------------------------------------------------------------- interfaces estáticas (un sitio, tres rutas)

WEB = RAIZ / "apps" / "web"
if WEB.exists():
    class EstaticosQueSeRevalidan(StaticFiles):
        """Sin esto el navegador adivina cuánto guardar cada archivo y, tras un despliegue, muestra la versión vieja hasta una recarga forzada.
        `no-cache` no impide guardar: obliga a preguntar si cambió (el ETag responde 304 si no cambió)."""
        async def get_response(self, path, scope):
            r = await super().get_response(path, scope)
            r.headers["Cache-Control"] = "no-cache"
            return r

    app.mount("/app", EstaticosQueSeRevalidan(directory=WEB, html=True), name="web")
