"""A2 — El grafo de la conversación (ARQUITECTURA §6): nodos, guardas y rutas por intención.

Cada transición pasa por su guarda. El modelo solo describe el mensaje (comandos, datos, señales); aquí el código
decide con hechos verificados, la política (A4) y las herramientas (A6), y arma el estado comunicable. Ninguna
salida del modelo tiene autoridad (INV-AUTORIDAD); ninguna frase al cliente vive aquí (INV-TEXTO).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from contratos.modelos import (AccionPendiente, CargoEnDiscusion, CargoReferido, EstadoConversacion,
                               HechosVerificados, Interpretacion, Nodo)
from servicio.conocimiento import conocimiento
from servicio.herramientas import banco, intenciones
from servicio.herramientas.banco import ErrorHerramienta
from servicio.politica import motor
from servicio.redactor import formato
from servicio.redactor.estado_comunicable import Constructor
from servicio.resolutor import comparador
from servicio.resolutor.calendario import expresion_de_cuando
from servicio.resolutor.resolutor import _clase as clase, resolver
from servicio.riesgo import senal as riesgo
from servicio.traspaso.traspaso import SEGURIDAD, dinero_en_juego
from servicio.verificacion.acciones import releer

VENTANA_BUSQUEDA_DIAS = 120
MAX_SIN_PROGRESO = {"defecto": 3, Nodo.N4: 5, Nodo.N5: 5}
TIPOS_TARJETA = ("Tarjeta Crédito", "Tarjeta Débito")
INTENCIONES_CON_CUENTA = {"disputas.reportar_cargo", "disputas.consultar_reclamo", "disputas.agregar_informacion",
                          "disputas.retirar_reclamo", "tarjetas.bloquear", "tarjetas.desbloquear",
                          "tarjetas.consultar_estado", "movimientos.consultar"}


class TimeoutEscritura(Exception):
    """Falla inyectada por el corredor de evaluación: la escritura se hizo, pero la respuesta no llegó."""


@dataclass
class Contexto:
    c: object                          # conexión con el sujeto fijado (RLS)
    estado: EstadoConversacion
    customer_id: str | None
    session_id: str | None
    hoy: date                          # reloj del sandbox de esta conversación
    data_as_of: date
    idioma: str
    ec: Constructor
    fallas: dict = field(default_factory=dict)
    ui: list[dict] = field(default_factory=list)
    pasos: list[dict] = field(default_factory=list)
    traspaso: dict | None = None       # {motivos, ...} si el turno termina con una persona
    completadas: set[str] = field(default_factory=set)
    acciones_realizadas: list[dict] = field(default_factory=list)
    decision: dict | None = None
    cambio: bool = False               # hubo progreso (dato nuevo, cargo, acción): para el estancamiento
    cliente: dict | None = None
    senal_evidencia: dict = field(default_factory=dict)
    t_ultimo: float | None = None      # para la latencia de cada paso (CONTRATOS A13, PasoRegistro.latencia_ms)
    reloj: object | None = None        # reloj de la persona (servicio/resolutor/reloj.py); None en pruebas sin reloj
    modelo: object | None = None       # para el Comparador (A3b); el Intérprete y el Redactor lo reciben del orquestador
    llamadas: list = field(default_factory=list)   # llamadas al modelo hechas dentro del grafo (Comparador)


# ---------------------------------------------------------------- utilidades

def _paso(ctx: Contexto, componente: str, estado: str, **detalle):
    import time
    ahora = time.monotonic()
    latencia = round((ahora - ctx.t_ultimo) * 1000, 1) if ctx.t_ultimo is not None else None
    ctx.t_ultimo = ahora
    ctx.pasos.append({"componente": componente, "estado": estado, "detalle": detalle, "latencia_ms": latencia})


def _cliente(ctx: Contexto) -> dict:
    if ctx.cliente is None:
        ctx.cliente = banco.cliente(ctx.c)
    return ctx.cliente


def _fecha(ctx: Contexto, d) -> str:
    """Una fecha de los datos, dicha en la fecha real del cliente (servicio/resolutor/reloj.py)."""
    return formato.fecha(ctx.reloj.a_local(d) if ctx.reloj else d, ctx.idioma)


def _valores_cargo(tx: dict, idioma: str, reloj=None) -> dict:
    """Los valores del movimiento para sus marcadores. El tipo siempre; el comercio y la ciudad solo si existen: un
    dato que el movimiento no tiene se omite, nunca se reemplaza por otro."""
    v = {"MOVIMIENTO": formato.movimiento(tx.get("tipo"), idioma) or tx.get("tipo"),
         "FECHA": formato.fecha(reloj.a_local(tx["fecha"]) if reloj else tx["fecha"], idioma),
         "HORA": tx.get("hora"), "COMERCIO": tx.get("comercio"), "CIUDAD": tx.get("ciudad"),
         "MONTO": formato.monto(tx.get("monto"), tx.get("moneda")),
         "PRODUCTO": formato.producto(tx.get("tipo_producto"), tx.get("ultimos4"), idioma)}
    return {k: x for k, x in v.items() if x}


def _tarjeta_ui(alias: str, tx: dict, idioma: str, reloj=None) -> dict:
    v = _valores_cargo(tx, idioma, reloj)
    return {"tipo": "tarjeta_cargo", "alias": alias, "movimiento": v.get("MOVIMIENTO"), "comercio": v.get("COMERCIO"),
            "fecha": v["FECHA"], "hora": v.get("HORA"), "ciudad": v.get("CIUDAD"), "monto": v["MONTO"],
            "producto": v["PRODUCTO"], "estado": tx.get("estado")}


def _nuevo_alias(estado: EstadoConversacion, prefijo: str = "C") -> str:
    usados = {c.alias for c in estado.cargos}
    n = 1
    while f"{prefijo}{n}" in usados:
        n += 1
    return f"{prefijo}{n}"


def _cargo(estado: EstadoConversacion, alias: str) -> CargoEnDiscusion | None:
    return next((c for c in estado.cargos if c.alias == alias), None)


def _cargo_actual(estado: EstadoConversacion) -> CargoEnDiscusion | None:
    """El cargo mostrado; o el que se está proponiendo reclamar (el cliente aún puede decir que lo reconoce)."""
    mostrados = [c for c in estado.cargos if c.estado == "mostrado"]
    if mostrados:
        return mostrados[-1]
    p = estado.accion_pendiente
    if p and p.codigo == "abrir_reclamo" and p.alias:
        return _cargo(estado, p.alias)
    return None


def _transacciones(ctx: Contexto) -> list[dict]:
    txs = banco.listar_transacciones(ctx.c, ctx.hoy - timedelta(days=VENTANA_BUSQUEDA_DIAS), ctx.hoy)
    if ctx.reloj:                    # lo posterior a la hora actual del cliente todavía no ocurrió
        txs = [t for t in txs if t.get("fecha_hora") is None or t["fecha_hora"] <= ctx.reloj.ahora_datos]
    _paso(ctx, "herramienta", "ok", herramienta="listar_transacciones", filas=len(txs))
    return txs


def tema_actual(estado: EstadoConversacion) -> str | None:
    return estado.pila_temas[-1]["tema"] if estado.pila_temas else None


def apilar(estado: EstadoConversacion, tema: str, datos: dict | None = None):
    if tema_actual(estado) != tema:
        estado.pila_temas.append({"tema": tema, "estado_guardado": datos or {}})


def desapilar(estado: EstadoConversacion):
    if estado.pila_temas:
        estado.pila_temas.pop()


# ---------------------------------------------------------------- identidad y traspaso

def pedir_identidad(ctx: Contexto, tema: str | None, cargos: list[CargoReferido] | None = None):
    """N0 → N1: el formulario seguro; el pedido queda guardado para retomarlo al verificar."""
    if tema:
        apilar(ctx.estado, tema, {"cargos_referidos": [c.model_dump() for c in (cargos or [])]})
    ctx.estado.nodo = Nodo.N1
    ctx.ec.afirmar("identidad_requerida")
    ctx.ui.append({"tipo": "formulario_identidad"})


def pedir_traspaso(ctx: Contexto, motivos: list[str], preguntas: list[str] | None = None, supera_umbral: bool = False,
                   plazo: dict | None = None):
    ctx.traspaso = {"motivos": motivos, "preguntas": preguntas or [], "supera_umbral": supera_umbral, "plazo": plazo}
    ctx.estado.nodo = Nodo.N11
    ctx.cambio = True


def productos_para_proteger(ctx: Contexto) -> list[dict]:
    return [p for p in banco.listar_productos(ctx.c) if p["tipo"] in TIPOS_TARJETA and p["estado"] == "Active"
            and not p["bloqueo_id"]]


# ---------------------------------------------------------------- acciones: proponer y ejecutar

def proponer(ctx: Contexto, accion: str, recurso: str, parametros: dict, alias: str | None, valores: dict | None = None,
             traspaso_despues: list[str] | None = None, datos_ui: dict | None = None, traspaso_extra: dict | None = None):
    """N7: la acción exacta, con su intención de un solo uso. `valores` van al estado comunicable como marcadores;
    `datos_ui`, solo a la tarjeta de confirmación de la interfaz. `traspaso_despues` son los motivos del traspaso que sigue a la
    acción y `traspaso_extra` lo que el traspaso necesita de este turno: de la política, `supera_umbral` y `plazo` (la prioridad), y,
    para el paquete del asesor, la `senal` de M1 y la `decision`. Se guardan con la intención porque el traspaso se pide al
    confirmar, en otro turno, y el contexto del turno ya no existe."""
    aid, expira = intenciones.proponer(ctx.c, ctx.estado.conversation_id, ctx.customer_id, ctx.session_id,
                                       ctx.estado.version + 1, accion, recurso,
                                       {**parametros, "traspaso_despues": traspaso_despues,
                                        **({"traspaso_extra": traspaso_extra} if traspaso_extra else {})})
    ctx.estado.accion_pendiente = AccionPendiente(codigo=accion, alias=alias, action_intent_id=aid,
                                                  session_id=ctx.session_id, expira=expira)
    ctx.estado.nodo = Nodo.N7
    ctx.ec.ofrecer(accion, alias, valores)
    ctx.ec.preguntar("confirmar_accion", alias)
    ctx.ui.append({"tipo": "confirmacion", "action_intent_id": aid, "accion": accion, "sobre": alias, **(valores or {}),
                   **(datos_ui or {})})
    ctx.cambio = True


def ejecutar_pendiente(ctx: Contexto, action_intent_id: str | None = None):
    """N7 → N8 → N9: confirma (INV-CONFIRMA), ejecuta con la clave de idempotencia y relee (INV-VERIFICA)."""
    p = ctx.estado.accion_pendiente
    aid = action_intent_id or (p.action_intent_id if p else None)
    if not aid:
        ctx.ec.preguntar("que_necesita")
        return
    try:
        i = intenciones.confirmar(ctx.c, aid, ctx.session_id, ctx.estado.version)
    except intenciones.ConfirmacionInvalida as e:
        _paso(ctx, "confirmacion", "fallo", motivo=str(e))
        vieja = ctx.c.execute("select * from atencion.intenciones_accion where action_intent_id = %s", (aid,)).fetchone()
        ctx.estado.accion_pendiente = None
        if vieja and vieja["estado"] in ("propuesta", "descartada"):
            # la confirmación vieja no vale (otra sesión, otra versión o vencida): se muestra y se pide otra vez
            params = vieja["parametros"] if isinstance(vieja["parametros"], dict) else json.loads(vieja["parametros"])
            intenciones.marcar(ctx.c, aid, "descartada")
            proponer(ctx, vieja["accion"], vieja["recurso"],
                     {k: v for k, v in params.items() if k not in ("traspaso_despues", "traspaso_extra")},
                     params.get("alias"), None, params.get("traspaso_despues"), traspaso_extra=params.get("traspaso_extra"))
        else:
            ctx.ec.preguntar("que_necesita")
        return
    params = i["parametros"] if isinstance(i["parametros"], dict) else json.loads(i["parametros"])
    accion = i["accion"]
    if i["estado"] in ("completada",):
        estado_final, releido = "completada", (i.get("resultado") or {})
    else:
        intenciones.marcar(ctx.c, aid, "ejecutando")
        ctx.estado.nodo = Nodo.N8
        estado_final, releido = _ejecutar(ctx, accion, params, aid)
    ctx.estado.accion_pendiente = None
    ctx.cambio = True
    if estado_final == "completada":
        intenciones.marcar(ctx.c, aid, "completada", releido)
        ctx.completadas.add(accion)
        ctx.acciones_realizadas.append({"accion": accion, "resultado": releido})
        ctx.estado.nodo = Nodo.N10
        _comunicar_resultado(ctx, accion, params, releido)
    else:
        intenciones.marcar(ctx.c, aid, estado_final, releido)
        ctx.ec.afirmar("accion_desconocida" if estado_final == "desconocida" else "accion_fallida", sobre=accion)
        pedir_traspaso(ctx, ["accion_estado_desconocido"], [f"verificar {accion} clave {aid}"])
        return
    if params.get("traspaso_despues"):
        extra = dict(params.get("traspaso_extra") or {})
        ctx.senal_evidencia = extra.pop("senal", None) or ctx.senal_evidencia
        ctx.decision = extra.pop("decision", None) or ctx.decision
        pedir_traspaso(ctx, params["traspaso_despues"], **extra)


def _ejecutar(ctx: Contexto, accion: str, p: dict, aid: str) -> tuple[str, dict]:
    try:
        with ctx.c.transaction():
            if accion == "abrir_reclamo":
                banco.abrir_reclamo(ctx.c, ctx.customer_id, p["transaction_id"], p["tipo"], aid,
                                    ctx.estado.conversation_id, p.get("plazo"), p.get("prioridad", 4), p.get("habilidad", "reclamos"))
            elif accion == "bloquear_producto":
                banco.bloquear_producto(ctx.c, ctx.customer_id, p["product_id"], p.get("origen", "cliente"), p.get("motivo"), aid)
            elif accion == "desbloquear_producto":
                banco.desbloquear_producto(ctx.c, ctx.customer_id, p["product_id"], aid, bool(ctx.estado.senales_riesgo))
            elif accion == "agregar_informacion_reclamo":
                banco.agregar_informacion_reclamo(ctx.c, ctx.customer_id, p["reclamo_id"], p.get("texto"), p.get("adjunto_id"), aid)
            elif accion == "retirar_reclamo":
                banco.retirar_reclamo(ctx.c, p["reclamo_id"], p.get("motivo") or "retiro pedido por el cliente", aid)
        if ctx.fallas.get("timeout_escritura") == accion and not ctx.fallas.get("_timeout_usado"):
            ctx.fallas["_timeout_usado"] = True        # la escritura quedó hecha; lo que se pierde es la respuesta
            raise TimeoutEscritura()
        _paso(ctx, "herramienta", "ok", herramienta=accion)
    except TimeoutEscritura:
        _paso(ctx, "herramienta", "fallo", herramienta=accion, motivo="tiempo agotado: estado desconocido")
    except ErrorHerramienta as e:
        _paso(ctx, "herramienta", "fallo", herramienta=accion, error=e.codigo)
        if e.codigo == "YA_EXISTE":
            return "completada", {"ya_existia": True, **{k: str(v) for k, v in e.datos.items()}}
        if e.codigo == "NO_PERMITIDO":
            ctx.ec.afirmar("accion_no_permitida", sobre=accion, motivo=e.detalle)
        return "fallida", {"error": e.codigo}
    estado, releido = releer(ctx.c, accion, aid, p)                 # A7: nunca se escribe dos veces
    _paso(ctx, "verificacion_accion", "ok" if estado == "completada" else "fallo", accion=accion, releido=estado)
    return estado, releido


def _comunicar_resultado(ctx: Contexto, accion: str, p: dict, r: dict):
    ec = ctx.ec
    if accion == "abrir_reclamo":
        if r.get("ya_existia"):                 # un reclamo por cargo: se informa el que ya estaba abierto
            ec.resultado("accion_completada", accion)
            ec.exacto("numero_caso", {"CASO": r.get("numero", "—")})
            ctx.ui.append({"tipo": "estado_caso", "numero": r.get("numero", "—"), "estado": r.get("estado", "abierto"), "plazo": None})
        else:
            ec.resultado("accion_completada", accion)
            plazo = _fecha(ctx, r.get("plazo_vence")) if r.get("plazo_vence") else None
            ec.exacto("numero_caso", {"CASO": r["numero"], **({"PLAZO": plazo} if plazo else {})})
            ctx.estado.reclamos_abiertos.append(r["numero"])
            ctx.ui.append({"tipo": "estado_caso", "numero": r["numero"], "estado": "abierto", "plazo": plazo})
        ec.afirmar("abrir_no_asegura_devolucion")
        c = _cargo(ctx.estado, p.get("alias") or "")
        if c:
            c.estado = "reclamado"
    elif accion == "bloquear_producto":
        ec.resultado("accion_completada", accion, {"PRODUCTO": p.get("producto_texto", "—")})
    elif accion == "desbloquear_producto":
        ec.resultado("accion_completada", accion, {"PRODUCTO": p.get("producto_texto", "—")})
    elif accion == "agregar_informacion_reclamo":
        ec.resultado("accion_completada", accion, {"CASO": p.get("numero", "—")})
    elif accion == "retirar_reclamo":
        ec.resultado("accion_completada", accion, {"CASO": p.get("numero", "—")})
    if not ctx.traspaso and not p.get("traspaso_despues"):
        ec.preguntar("otra_ayuda")


# ---------------------------------------------------------------- disputas: encontrar, mostrar, evaluar

def mostrar_cargo(ctx: Contexto, tx: dict, alias: str | None = None, preguntar: bool = True):
    """N5: los hechos del cargo, releídos de la base, y la pregunta de si lo reconoce."""
    alias = alias or _nuevo_alias(ctx.estado)
    existente = _cargo(ctx.estado, alias)
    if existente is None:
        ctx.estado.cargos.append(CargoEnDiscusion(alias=alias, atributos={"estado": tx["estado"]}, estado="mostrado",
                                                  transaction_ref_interno=tx["transaction_id"]))
    else:
        existente.estado = "mostrado"
    for c in ctx.estado.cargos:
        if c.alias != alias and c.estado == "mostrado":
            c.estado = "candidato"
    ctx.estado.opciones_mostradas = []
    ctx.estado.nodo = Nodo.N5
    ctx.ec.afirmar("cargo", alias, _valores_cargo(tx, ctx.idioma, ctx.reloj))
    if tx["estado"] in ("Declined", "Reversed"):
        ctx.ec.afirmar("cargo_sin_cobro", alias)
    elif tx["estado"] == "Pending":
        ctx.ec.afirmar("cargo_pendiente", alias)
    if preguntar:
        ctx.ec.preguntar("reconoce_cargo", alias)
    ctx.ui.append(_tarjeta_ui(alias, tx, ctx.idioma, ctx.reloj))
    ctx.cambio = True


ULTIMOS_A_MOSTRAR = 5


def _ultimos_descartados(ctx: Contexto) -> bool:
    return ctx.estado.datos_dados.get("_ultimos_descartados") == "si"


def registrar_reconocido_con_senal(ctx: Contexto, cargo: CargoEnDiscusion):
    """El cliente dijo «lo reconozco» sobre un cargo cuyo score supera el umbral certificado. Nada cambia para él (no se le acusa ni se le
    agrega un paso: confirmar es su derecho, y por texto no hay forma de saber si lo dice presionado), pero la traza deja una marca que se puede
    buscar después: `registro_turnos.registro -> pasos -> detalle.marca`. Es solo para auditoría: no entra al estado comunicable."""
    tx = banco.obtener_transaccion(ctx.c, cargo.transaction_ref_interno)
    s = riesgo.evaluar(tx.get("fraud_score"))
    if s.supera_umbral_certificado:
        _paso(ctx, "politica", "ok", marca="reconocido_con_senal_sobre_umbral", cargo=cargo.alias, version_m1=s.version)


def mostrar_ultimos(ctx: Contexto) -> bool:
    """N4: el cliente no da con el cargo (no dio datos, o con lo dicho no hay movimiento, salvo que hable de hoy: ver `buscar_cargo`). Un cliente que no recuerda suele acordarse al
    ver sus últimos movimientos, así que se le muestran, del más reciente al más antiguo, con la salida «ninguno de estos». Solo una vez por
    conversación: si ya los descartó, el que sigue es una persona. Devuelve False si no hay nada que mostrar."""
    if _ultimos_descartados(ctx):
        return False
    ultimos = _transacciones(ctx)[:ULTIMOS_A_MOSTRAR]
    if not ultimos:
        return False
    ctx.ec.afirmar("ultimos_movimientos")
    _listar_opciones(ctx, ultimos, con_ninguno=True)
    return True


def ninguno_de_los_mostrados(ctx: Contexto):
    """El cliente dice que ninguno de los movimientos mostrados es el suyo (botón «Ninguno de estos»)."""
    e = ctx.estado
    for alias in e.opciones_mostradas:
        cargo = _cargo(e, alias)
        if cargo:
            cargo.estado = "descartado"
    e.opciones_mostradas = []
    ctx.cambio = True
    ctx.ec.afirmar("ninguno_de_los_mostrados")
    if _ultimos_descartados(ctx):
        pedir_traspaso(ctx, ["revision_humana_politica"])
        return
    e.datos_dados["_ultimos_descartados"] = "si"
    e.nodo = Nodo.N4
    ctx.ec.preguntar("dato_faltante", campos=["monto", "cuando", "descripcion"])


def _datos_que_faltan(referido: CargoReferido) -> list[str]:
    """Solo lo que el cliente todavía no dijo. Pedirle de nuevo el monto o la descripción que ya dio lo hace repetir su historia (promesa P2)."""
    faltan = [c for c, v in (("monto", referido.monto), ("cuando", referido.cuando), ("descripcion", referido.descripcion)) if not v]
    return faltan or ["monto", "cuando", "descripcion"]


def buscar_cargo(ctx: Contexto, referido: CargoReferido):
    """N3: el resolutor sobre las transacciones del titular; 0, 1, 2-5 o más de 5 candidatos."""
    if not (referido.monto or referido.cuando or referido.descripcion):
        if mostrar_ultimos(ctx):
            return
        ctx.estado.nodo = Nodo.N4
        ctx.ec.preguntar("dato_faltante", campos=["monto", "cuando", "descripcion"])
        return
    txs = _transacciones(ctx)
    r = resolver(referido, txs, ctx.hoy, ctx.data_as_of, ctx.reloj)
    _paso(ctx, "resolutor", "ok", candidatos=r.clase, rango=[str(x) for x in r.rango] if r.rango else None)
    descripcion_distinta = False
    if referido.descripcion and r.candidatos:
        comp = comparador.comparar(ctx.modelo, referido.descripcion, r.candidatos, ctx.idioma)
        ctx.llamadas += comp.llamadas
        _paso(ctx, "comparador", "ok" if comp.candidatos is not None else "fallo", motivo=comp.motivo,
              entran=len(r.candidatos), coinciden=None if comp.candidatos is None else len(comp.candidatos))
        if comp.candidatos:
            r.candidatos, r.clase = comp.candidatos, clase(len(comp.candidatos))
        elif comp.candidatos == [] and r.clase in ("1", "2-5") and (referido.monto or referido.cuando):
            descripcion_distinta = True      # con el monto o la fecha dichos sí hay movimientos: el cliente elige el suyo. Sin ninguno de los dos no se
                                             # puede decir «con el monto y la fecha que diste»: no los dio (se supondría algo que no pasó)
        elif comp.candidatos == []:
            r.candidatos, r.clase = [], "0"
    if descripcion_distinta:
        ctx.ec.afirmar("descripcion_distinta")
        _listar_opciones(ctx, r.candidatos)
        return
    if r.clase == "1":
        # Siempre se muestra el cargo y el cliente dice si lo reconoce: nada se propone sobre un cargo que no ha visto. Antes, un
        # `reconoce: no` dicho en el primer mensaje saltaba este paso, y un "no sé de dónde salió" mal leído terminaba en una propuesta de reclamo.
        mostrar_cargo(ctx, r.candidatos[0])
    elif r.clase == "2-5":
        _listar_opciones(ctx, r.candidatos)
    elif r.clase == ">5":
        ctx.estado.nodo = Nodo.N4
        ctx.ec.afirmar("demasiados_candidatos", valores={"CANTIDAD": str(len(r.candidatos))})
        ctx.ec.preguntar("dato_faltante", campos=["monto", "cuando"])
    else:
        ctx.estado.nodo = Nodo.N4
        if r.posterior_a_datos:
            ctx.ec.afirmar("cargo_posterior_a_datos", valores={"DATOS_HASTA": _fecha(ctx, ctx.data_as_of)})
        elif r.fecha_no_entendida:
            ctx.ec.afirmar("fecha_no_entendida")
            ctx.ec.preguntar("dato_faltante", campos=["cuando"])
        else:
            ctx.ec.afirmar("sin_candidatos")
            if _ultimos_descartados(ctx):          # ya vio sus últimos movimientos y no era ninguno: no se le pide otra vuelta
                pedir_traspaso(ctx, ["revision_humana_politica"])
            elif referido.cuando and r.rango and r.rango[1] >= ctx.hoy:
                # Dijo una fecha que incluye hoy: los cargos del día pueden no estar cargados todavía (frescura de los datos). Que no haya registro
                # no dice que no exista, y mostrarle otros movimientos lo empuja a elegir uno que no es (E4). Se pide lo que falta, como antes.
                ctx.estado.nodo = Nodo.N4
                ctx.ec.preguntar("dato_faltante", campos=_datos_que_faltan(referido))
            elif not mostrar_ultimos(ctx):
                ctx.ec.preguntar("dato_faltante", campos=_datos_que_faltan(referido))


def _listar_opciones(ctx: Contexto, candidatos: list[dict], con_ninguno: bool = False):
    """N4: varios movimientos posibles; el cliente elige el suyo por su alias. Con `con_ninguno`, la interfaz agrega «Ninguno de estos»."""
    ctx.estado.nodo = Nodo.N4
    opciones = []
    for tx in candidatos:
        alias = _nuevo_alias(ctx.estado)
        ctx.estado.cargos.append(CargoEnDiscusion(alias=alias, atributos={"estado": tx["estado"]},
                                                  transaction_ref_interno=tx["transaction_id"]))
        ctx.ec.afirmar("candidatos", alias, _valores_cargo(tx, ctx.idioma, ctx.reloj))
        opciones.append(_tarjeta_ui(alias, tx, ctx.idioma, ctx.reloj))
    ctx.estado.opciones_mostradas = [o["alias"] for o in opciones]
    ctx.ec.preguntar("elegir_opcion", ctx.estado.opciones_mostradas)
    ctx.ui.append({"tipo": "opciones", "opciones": opciones, **({"ninguno": True} if con_ninguno else {})})
    ctx.cambio = True


def hechos_de(ctx: Contexto, accion: str, tx: dict | None, **extra) -> HechosVerificados:
    cli = _cliente(ctx)
    s = riesgo.evaluar(tx.get("fraud_score") if tx else None)
    ctx.senal_evidencia = {"p": s.p, "supera_umbral_certificado": s.supera_umbral_certificado, "cota_fdr": s.cota_fdr,
                           "version_m1": s.version}
    return HechosVerificados(
        autenticado=bool(ctx.customer_id), accion=accion, candidatos=1 if tx else 0, cargo_confirmado=bool(tx),
        estado_transaccion=tx.get("estado") if tx else None,
        monto_usd=float(tx["amount_usd"]) if tx and tx.get("amount_usd") is not None else None,
        dias_desde_transaccion=(ctx.hoy - (tx["fecha"].date() if isinstance(tx["fecha"], datetime) else tx["fecha"])).days if tx else None,
        jurisdiccion=cli.get("pais"), tipo_producto=tx.get("tipo_producto") if tx else None,
        tipo_disputa=ctx.estado.tipo_disputa, senal_riesgo_p=s.p if (not tx or tx.get("fraud_score") is not None) else None,
        supera_umbral_certificado=s.supera_umbral_certificado, cota_fdr=s.cota_fdr,
        reclamos_previos_90d=banco.reclamos_previos(ctx.c, ctx.hoy), senales_riesgo=sorted(ctx.estado.senales_riesgo),
        moneda_pais_coherente=bool(tx.get("moneda_pais_coherente", True)) if tx else True, **extra)


def _motivos_politica(d, tx_tipo: str | None) -> list[str]:
    motivos = []
    for m in d.motivos:
        if m == "senal_sobre_umbral":
            motivos.append("bloqueo_recomendado_por_riesgo")
        elif m == "senal_de_seguridad":
            continue
        elif m == "desbloqueo_tras_riesgo":
            motivos.append("desbloqueo_tras_riesgo")
        else:
            motivos.append("revision_humana_politica")
    if tx_tipo in ("no_autorizada", "estafa_autorizada"):
        motivos.append("fraude_no_automatizable")
    return list(dict.fromkeys(motivos)) or ["revision_humana_politica"]


def evaluar_no_reconocido(ctx: Contexto, cargo: CargoEnDiscusion):
    """N5 (no lo reconoce) → N6: política con hechos verificados → proponer, traspasar o aclarar."""
    cargo.estado = "no_reconocido"
    ctx.estado.tipo_disputa = ctx.estado.tipo_disputa or "no_autorizada"
    tx = banco.obtener_transaccion(ctx.c, cargo.transaction_ref_interno)
    tx = {**tx, "fecha": tx["fecha"]}
    ctx.estado.nodo = Nodo.N6
    h = hechos_de(ctx, "abrir_reclamo", tx)
    d = motor.decidir(h, ctx.hoy)
    ctx.decision = d.model_dump(mode="json")
    _paso(ctx, "politica", "ok", camino=d.camino, verificaciones={v.id: v.cumple for v in d.verificaciones}, motivos=d.motivos)
    ctx.cambio = True
    valores = _valores_cargo({**tx, "fecha": tx["fecha"].date(), "hora": tx["fecha"].strftime("%H:%M")}, ctx.idioma, ctx.reloj)
    if d.camino == "automatizable" and "abrir_reclamo" in d.acciones_permitidas:
        cli = _cliente(ctx)
        proponer(ctx, "abrir_reclamo", tx["transaction_id"],
                 {"transaction_id": tx["transaction_id"], "tipo": ctx.estado.tipo_disputa, "alias": cargo.alias,
                  "plazo": d.plazo_normativo, "habilidad": "fraude" if ctx.estado.tipo_disputa in ("no_autorizada", "estafa_autorizada") else "reclamos",
                  "prioridad": 3 if dinero_en_juego(tx["tipo"], tx["amount_usd"]) else 4},
                 cargo.alias, None, datos_ui={k: valores[k] for k in ("MOVIMIENTO", "COMERCIO", "MONTO") if k in valores})
        ctx.ec.afirmar("abrir_no_asegura_devolucion")
    elif d.camino == "automatizable":          # sin cobro: no hay reclamo de cobro por defecto, sí revisión y bloqueo
        ctx.ec.afirmar("cargo_sin_cobro", cargo.alias)
        ctx.ec.afirmar("persona_disponible")
        ctx.ec.preguntar("otra_ayuda")
        ctx.estado.nodo = Nodo.N10
    elif d.camino == "abstencion":
        ctx.estado.nodo = Nodo.N4
        ctx.ec.preguntar("elegir_opcion", ctx.estado.opciones_mostradas or [cargo.alias])
    else:
        motivos = _motivos_politica(d, ctx.estado.tipo_disputa)
        productos = productos_para_proteger(ctx) if h.supera_umbral_certificado else []
        prod = next((p for p in productos if p["product_id"] == tx["product_id"]), None)
        if prod:                               # recomendación de bloqueo con umbral certificado: primero proteger
            hb = hechos_de(ctx, "bloquear_producto", tx, recomendacion_del_sistema=True)
            db = motor.decidir(hb, ctx.hoy)
            if db.camino == "automatizable":
                texto = formato.producto(prod["tipo"], prod["ultimos4"], ctx.idioma)
                proponer(ctx, "bloquear_producto", prod["product_id"],
                         {"product_id": prod["product_id"], "origen": "riesgo", "motivo": "riesgo", "producto_texto": texto},
                         None, {"PRODUCTO": texto}, traspaso_despues=motivos,
                         traspaso_extra={"supera_umbral": h.supera_umbral_certificado, "plazo": d.plazo_normativo,
                                         "senal": ctx.senal_evidencia, "decision": ctx.decision})
                return
        pedir_traspaso(ctx, motivos, supera_umbral=h.supera_umbral_certificado, plazo=d.plazo_normativo)


def ofrecer_proteccion_y_traspaso(ctx: Contexto, motivos: list[str]) -> bool:
    """Guarda N2/N5 → N11 con señal de seguridad: si hay un producto que proteger, primero se ofrece el bloqueo."""
    productos = productos_para_proteger(ctx)
    ya_ofrecido = ctx.estado.datos_dados.get("_bloqueo_ofrecido") == "si"
    if productos and not ya_ofrecido:
        ctx.estado.datos_dados["_bloqueo_ofrecido"] = "si"
        if len(productos) == 1:
            p = productos[0]
            texto = formato.producto(p["tipo"], p["ultimos4"], ctx.idioma)
            proponer(ctx, "bloquear_producto", p["product_id"],
                     {"product_id": p["product_id"], "origen": "cliente", "motivo": ",".join(motivos), "producto_texto": texto},
                     None, {"PRODUCTO": texto}, traspaso_despues=motivos)
        else:
            elegir_producto(ctx, productos, "tarjetas.bloquear", traspaso_despues=motivos)
        return True
    pedir_traspaso(ctx, motivos)
    return False


def elegir_producto(ctx: Contexto, productos: list[dict], tema: str, traspaso_despues: list[str] | None = None):
    ctx.estado.nodo = Nodo.N4
    opciones = []
    for i, p in enumerate(productos, 1):
        alias = f"P{i}"
        texto = formato.producto(p["tipo"], p["ultimos4"], ctx.idioma)
        ctx.ec.afirmar("productos", alias, {"PRODUCTO": texto}, bloqueado=bool(p["bloqueo_id"]))
        opciones.append({"alias": alias, "producto": texto, "product_id_oculto": None})
        ctx.estado.datos_dados[f"_producto_{alias}"] = p["product_id"]
    ctx.estado.opciones_mostradas = [o["alias"] for o in opciones]
    apilar(ctx.estado, tema, {"traspaso_despues": traspaso_despues})
    ctx.ec.preguntar("elegir_opcion", ctx.estado.opciones_mostradas)
    ctx.ui.append({"tipo": "opciones", "opciones": [{"alias": o["alias"], "producto": o["producto"]} for o in opciones]})
    ctx.cambio = True


# ---------------------------------------------------------------- rutas por intención (§6.2b)

def ruta(ctx: Contexto, intencion: str, interp: Interpretacion | None):
    apilar(ctx.estado, intencion)
    if intencion in ("disputas.reportar_cargo", "movimientos.consultar"):
        if interp and interp.tipo_disputa_propuesto and interp.tipo_disputa_propuesto != "reconocida":
            ctx.estado.tipo_disputa = interp.tipo_disputa_propuesto
        referidos = (interp.cargos_referidos if interp else []) or [CargoReferido(**_referido_de_datos(ctx.estado))]
        buscar_cargo(ctx, referidos[0])
    elif intencion == "disputas.consultar_reclamo":
        consultar_reclamos(ctx)
    elif intencion == "disputas.agregar_informacion":
        info = _dato(interp, "informacion") or ctx.estado.datos_dados.get("informacion")
        con_reclamo(ctx, "agregar_informacion_reclamo", {"texto": info})
    elif intencion == "disputas.retirar_reclamo":
        con_reclamo(ctx, "retirar_reclamo", {"motivo": _dato(interp, "motivo") or ctx.estado.datos_dados.get("motivo")})
    elif intencion == "tarjetas.bloquear":
        prods = productos_para_proteger(ctx)
        if not prods:
            ctx.ec.afirmar("productos", valores=None)
            ctx.ec.preguntar("otra_ayuda")
        elif len(prods) == 1:
            p = prods[0]
            texto = formato.producto(p["tipo"], p["ultimos4"], ctx.idioma)
            proponer(ctx, "bloquear_producto", p["product_id"], {"product_id": p["product_id"], "origen": "cliente",
                                                                "producto_texto": texto}, None, {"PRODUCTO": texto})
        else:
            elegir_producto(ctx, prods, "tarjetas.bloquear")
    elif intencion == "tarjetas.desbloquear":
        bloqueados = [p for p in banco.listar_productos(ctx.c) if p["bloqueo_id"]]
        if not bloqueados:
            ctx.ec.afirmar("productos")
            ctx.ec.preguntar("otra_ayuda")
        else:
            desbloquear(ctx, bloqueados[0])
    elif intencion == "tarjetas.consultar_estado":
        for i, p in enumerate(banco.listar_productos(ctx.c), 1):
            ctx.ec.afirmar("productos", f"P{i}", {"PRODUCTO": formato.producto(p["tipo"], p["ultimos4"], ctx.idioma)},
                           estado="bloqueado_temporal" if p["bloqueo_id"] else p["estado"])
        _paso(ctx, "herramienta", "ok", herramienta="estado_producto")
        ctx.ec.preguntar("otra_ayuda")
        desapilar(ctx.estado)


def _dato(interp: Interpretacion | None, campo: str) -> str | None:
    if not interp:
        return None
    for c in interp.comandos:
        if c.nombre in ("dar_dato", "corregir") and c.args and c.args[0] == campo and len(c.args) > 1:
            return c.args[1]
    return None


def _referido_de_datos(estado: EstadoConversacion) -> dict:
    d = estado.datos_dados
    ref: dict = {}
    if d.get("monto"):
        try:
            ref["monto"] = {"valor": float(d["monto"]), "aproximado": True}
        except ValueError:                   # el monto dado no es un número: se busca sin él y queda la razón
            from servicio.registro.consumo import registrar_incidente
            registrar_incidente("grafo.referido_de_datos", tipo="dato_no_numerico", severidad="advertencia",
                                mensaje=f"monto dado no numérico: {d['monto']!r}; se busca sin monto")
    if d.get("cuando"):
        # El Intérprete a veces escribe la fecha suelta («ayer») y no «relativa ayer». Antes se descartaba sin avisar y se le volvía a pedir al cliente lo que
        # ya había dicho; ahora se acepta si el calendario la reconoce, y si no, queda un incidente (como el monto).
        expresion = expresion_de_cuando(d["cuando"])
        if expresion:
            ref["cuando"] = {"tipo": expresion[0], "valor": expresion[1]}
        else:
            from servicio.registro.consumo import registrar_incidente
            registrar_incidente("grafo.referido_de_datos", tipo="dato_no_entendido", severidad="advertencia",
                                mensaje=f"fecha dada que el calendario no reconoce: {d['cuando']!r}; se busca sin fecha")
    if d.get("descripcion"):
        ref["descripcion"] = d["descripcion"]
    return ref


def desbloquear(ctx: Contexto, p: dict):
    h = hechos_de(ctx, "desbloquear_producto", None,
                  bloqueo_pedido_por_cliente=(p["bloqueo_origen"] == "cliente" and p["bloqueo_motivo"] in (None, "", "pedido")))
    d = motor.decidir(h, ctx.hoy)
    ctx.decision = d.model_dump(mode="json")
    _paso(ctx, "politica", "ok", camino=d.camino, motivos=d.motivos)
    texto = formato.producto(p["tipo"], p["ultimos4"], ctx.idioma)
    if d.camino == "automatizable":
        proponer(ctx, "desbloquear_producto", p["product_id"], {"product_id": p["product_id"], "producto_texto": texto},
                 None, {"PRODUCTO": texto})
    else:
        ctx.ec.afirmar("accion_no_permitida", sobre="desbloquear_producto", motivo="desbloqueo_tras_riesgo")
        pedir_traspaso(ctx, ["desbloqueo_tras_riesgo"])


def consultar_reclamos(ctx: Contexto):
    reclamos = banco.listar_reclamos(ctx.c)
    _paso(ctx, "herramienta", "ok", herramienta="listar_reclamos", filas=len(reclamos))
    ctx.c.execute("update atencion.avisos_cliente set leido = true where not leido")   # los vio al consultar (RLS: los suyos)
    if not reclamos:
        ctx.ec.afirmar("sin_reclamos")
        ctx.ec.preguntar("otra_ayuda")
        return
    for r in reclamos[:5]:
        valores = {"CASO": r["numero"], "PLAZO": _fecha(ctx, r["plazo_vence"]) if r["plazo_vence"] else "—",
                   "MONTO": formato.monto(float(r["monto"]) if r["monto"] is not None else None, r["moneda"]),
                   "MOVIMIENTO": formato.movimiento(r["tipo_movimiento"], ctx.idioma), "COMERCIO": r["comercio"],
                   "FECHA": _fecha(ctx, r["fecha_cargo"])}
        valores = {k: v for k, v in valores.items() if v}
        ctx.ec.afirmar("reclamo", r["numero"], valores, estado=r["estado"])
        if r["explicacion"]:
            ctx.ec.afirmar("reclamo_explicacion", r["numero"], {"EXPLICACION": r["explicacion"]},
                           documentos_disponibles=bool(r["documentos"]))
            ctx.ec.afirmar("persona_disponible")
            if r["estado"] in ("resuelto_en_contra", "no_procede") and ctx.ec.articulo is None:
                # PR-12: una negativa se explica y se dice a quién acudir; el artículo lo decide el estado del reclamo
                art = conocimiento.servir(ctx.c, "publico.si-no-quedas-conforme", _cliente(ctx).get("pais"), ctx.idioma, ctx.hoy)
                if art:
                    ctx.ec.responder(art)
                    _paso(ctx, "conocimiento", "ok", articulo=f"{art['id']}@{art['version']}", via="estado_del_reclamo")
        if r["estado"] == "resuelto_a_favor" and not r["referencia_abono"]:
            ctx.ec.afirmar("sin_abono_registrado", r["numero"])
        ctx.ui.append({"tipo": "estado_caso", "numero": r["numero"], "estado": r["estado"], "plazo": valores["PLAZO"]})
    ctx.estado.nodo = Nodo.N10
    ctx.ec.preguntar("otra_ayuda")
    desapilar(ctx.estado)


def con_reclamo(ctx: Contexto, accion: str, extra: dict):
    activos = [r for r in banco.listar_reclamos(ctx.c)]
    _paso(ctx, "herramienta", "ok", herramienta="listar_reclamos", filas=len(activos))
    if not activos:
        ctx.ec.afirmar("sin_reclamos")
        ctx.ec.preguntar("otra_ayuda")
        return
    r = activos[0] if len(activos) == 1 else next((x for x in activos if x["estado"] in banco.ACTIVOS), activos[0])
    if accion == "retirar_reclamo" and r["estado"] not in banco.ACTIVOS:
        ctx.ec.afirmar("reclamo", r["numero"], {"CASO": r["numero"]}, estado=r["estado"])
        ctx.ec.afirmar("accion_no_permitida", sobre=accion, motivo=f"reclamo {r['estado']}")
        ctx.ec.preguntar("otra_ayuda")
        _paso(ctx, "herramienta", "no_aplica", herramienta=accion, motivo="NO_PERMITIDO")
        return
    if accion == "retirar_reclamo" and not extra.get("motivo"):
        ctx.estado.nodo = Nodo.N4
        ctx.ec.afirmar("reclamo", r["numero"], {"CASO": r["numero"]}, estado=r["estado"])
        ctx.ec.preguntar("motivo_retiro", r["numero"])
        return
    if accion == "agregar_informacion_reclamo" and not (extra.get("texto") or extra.get("adjunto_id")):
        ctx.estado.nodo = Nodo.N4
        ctx.ec.preguntar("dato_faltante", campos=["informacion"])
        return
    proponer(ctx, accion, r["reclamo_id"], {"reclamo_id": r["reclamo_id"], "numero": r["numero"], **extra}, r["numero"],
             {"CASO": r["numero"]})
