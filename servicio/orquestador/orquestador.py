"""A2 — Orquestador: el orden de un turno (CONTRATOS A2 y A17).

A17 (números de tarjeta) → A1 → borrado de secretos → se guarda el turno → grafo (guardas, política, herramientas,
verificación) → A8 + A9 (o el borrador del Intérprete si no hay hechos nuevos) → se guarda el estado con bloqueo
optimista → registro del turno. Un evento del canal (botón, formulario, adjunto) no pasa por el Intérprete.
Sin modelo, la conversación pasa a una persona y el cliente ve el aviso de espera: ninguna frase fija.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from contratos import catalogo
from contratos.modelos import Adjunto, EstadoConversacion, Interpretacion, Nodo, Turno
from servicio.canal.filtro_sensible import borrar_secretos, borrar_tarjetas
from servicio.conocimiento import conocimiento
from servicio.datos.db import transaccion
from servicio.enrutador import enrutador
from servicio.herramientas import banco, intenciones
from servicio.identidad.identidad import leer_token
from servicio.interprete.interprete import InterpretacionFallida, interpretar
from servicio.llm.cliente import Modelo, RespuestaModelo
from servicio.orquestador import grafo
from servicio.orquestador.grafo import Contexto, SEGURIDAD
from servicio.politica import motor
from servicio.redactor.estado_comunicable import Constructor
from servicio.redactor.redactor import RedaccionFallida, redactar
from servicio.traspaso.traspaso import armar_paquete, dinero_en_juego, enrutar_sin_modelo
from servicio.verificacion.redaccion import reemplazar
from contratos.idiomas import es_soportado, normalizar

TEXTOS_LEGALES = yaml.safe_load((Path(__file__).resolve().parents[2] / "config" / "textos_legales.yaml").read_text(encoding="utf-8"))


class Conflicto(Exception):
    """Otra petición cambió la conversación en medio (bloqueo optimista)."""


@dataclass
class Entrada:
    texto: str | None = None
    evento: dict | None = None
    mensaje_cliente_id: str | None = None


@dataclass
class Salida:
    conversation_id: str
    version: int
    texto: str
    ui: list[dict]
    nodo: str
    sin_modelo: bool = False
    traspaso: dict | None = None
    turn_id: str | None = None
    repetido: bool = False


# ---------------------------------------------------------------- persistencia

def _cargar(c, conversation_id: str, customer_id: str | None, reloj: date | None) -> tuple[EstadoConversacion, dict]:
    conv = c.execute("select * from atencion.conversaciones where conversation_id = %s", (conversation_id,)).fetchone()
    if conv is None:
        c.execute("insert into atencion.conversaciones (conversation_id, customer_id, reloj) values (%s,%s,%s)",
                  (conversation_id, customer_id, reloj))           # nulo: en vivo, con el reloj de la persona
        estado = EstadoConversacion(conversation_id=conversation_id, identidad_verificada=bool(customer_id),
                                    nodo=Nodo.N2 if customer_id else Nodo.N0)
        c.execute("insert into atencion.estado_conversacion (conversation_id, customer_id, version, estado) values (%s,%s,0,%s)",
                  (conversation_id, customer_id, estado.model_dump_json()))
        conv = c.execute("select * from atencion.conversaciones where conversation_id = %s", (conversation_id,)).fetchone()
        return estado, conv
    fila = c.execute("select * from atencion.estado_conversacion where conversation_id = %s", (conversation_id,)).fetchone()
    if fila is None:
        raise PermissionError("conversación ajena")
    return EstadoConversacion.model_validate(fila["estado"]), conv


def _pregunta_del_turno(construido) -> dict | None:
    """La pregunta que este turno le hizo al cliente (CONTRATOS: `ultima_pregunta`): el código de la primera PREGUNTAR del estado comunicable,
    que ya pasó por el catálogo. Sin pregunta en el turno queda vacía: una pregunta vieja no se le muestra al Intérprete como si fuera la actual."""
    for el in construido.elementos:
        if el.clase == "PREGUNTAR":
            return {"codigo": json.loads(el.contenido)["pregunta"]}
    return None


def _guardar(c, estado: EstadoConversacion, version_leida: int, customer_id: str | None):
    estado.version = version_leida + 1
    n = c.execute("""update atencion.estado_conversacion set estado = %s, version = %s, customer_id = coalesce(customer_id, %s)
                     where conversation_id = %s and version = %s""",
                  (estado.model_dump_json(), estado.version, customer_id, estado.conversation_id, version_leida)).rowcount
    if n == 0:
        raise Conflicto(estado.conversation_id)
    c.execute("update atencion.conversaciones set version = %s, idioma = %s, customer_id = coalesce(customer_id, %s) where conversation_id = %s",
              (estado.version, normalizar(estado.idioma), customer_id, estado.conversation_id))


def _turno(c, estado: EstadoConversacion, rol: str, texto: str, customer_id: str | None, respuesta: dict | None = None,
           mensaje_cliente_id: str | None = None):
    n = len(estado.historial) + 1
    estado.historial.append(Turno(turno=n, rol=rol, texto_con_marcadores=texto))
    c.execute("""insert into atencion.turnos (conversation_id, n, customer_id, rol, texto, mensaje_cliente_id, respuesta)
                 values (%s,%s,%s,%s,%s,%s,%s)""",
              (estado.conversation_id, n, customer_id, rol, texto, mensaje_cliente_id, json.dumps(respuesta or {}, default=str)))


# ---------------------------------------------------------------- el turno

def procesar(conversation_id: str, entrada: Entrada, token: str | None, modelo: Modelo, reloj: date | None = None,
             fallas: dict | None = None) -> Salida:
    """Un turno. Todo lo que se registre dentro (cada llamada al modelo, cada incidente) lleva la conversación y el
    turno; cualquier falla queda con su razón real antes de subir (al cliente le llega un error genérico)."""
    from servicio.registro.consumo import fijar_contexto, registrar_incidente, restaurar_contexto
    turn_id = "t_" + secrets.token_hex(8)
    marca = fijar_contexto(conversation_id=conversation_id, turn_id=turn_id)
    try:
        return _procesar(conversation_id, entrada, token, modelo, reloj, fallas, turn_id)
    except Conflicto as e:
        registrar_incidente("orquestador.procesar", e, severidad="advertencia", mensaje="otra petición cambió la conversación en medio")
        raise
    except PermissionError as e:
        registrar_incidente("orquestador.procesar", e, severidad="critica", mensaje=f"acceso negado: {e}")
        raise
    except Exception as e:
        e.referencia = registrar_incidente("orquestador.procesar", e, severidad="critica",
                                           evento=(entrada.evento or {}).get("tipo"), con_texto=bool(entrada.texto))
        e.registrado = True
        rescate = _rescate(conversation_id, token, reloj, turn_id, e.referencia)
        if rescate is not None:
            return rescate
        raise
    finally:
        restaurar_contexto(marca)


def _procesar(conversation_id: str, entrada: Entrada, token: str | None, modelo: Modelo, reloj: date | None,
              fallas: dict | None, turn_id: str) -> Salida:
    t0 = time.monotonic()
    claims = leer_token(token)
    customer_id = claims["sub"] if claims and claims.get("rol") == "cliente" else None
    session_id = claims.get("sid") if claims else None
    with transaccion("app_ejecucion", customer_id=customer_id, conversation_id=conversation_id) as c:
        visible = c.execute("select 1 from atencion.conversaciones where conversation_id = %s", (conversation_id,)).fetchone()
        if not visible and c.execute("select atencion.conversacion_existe(%s) e", (conversation_id,)).fetchone()["e"]:
            # La conversación es de un cliente y la sesión venció (o es otra persona): nada se lee ni se escribe;
            # se pide identificarse otra vez y la acción pendiente se vuelve a confirmar después (INV-CONFIRMA).
            return _sesion_vencida(conversation_id, modelo, turn_id)
        estado, conv = _cargar(c, conversation_id, customer_id, reloj)
        if conv["customer_id"] and conv["customer_id"] != customer_id and customer_id:
            raise PermissionError("la conversación es de otro cliente")
        if entrada.mensaje_cliente_id:
            previo = c.execute("""select respuesta from atencion.turnos where conversation_id = %s and mensaje_cliente_id = %s""",
                               (conversation_id, entrada.mensaje_cliente_id)).fetchone()
            if previo and previo["respuesta"].get("salida"):
                return Salida(**{**previo["respuesta"]["salida"], "repetido": True})
        version_leida = estado.version
        data_as_of = c.execute("select data_as_of from servicio.datos_version").fetchone()["data_as_of"]
        reloj_persona = _reloj(c, conv["reloj"], data_as_of, customer_id)
        hoy = reloj_persona.hoy_datos
        estado.data_as_of = data_as_of
        primer_turno = not any(t.rol == "asistente" for t in estado.historial)
        preferencia = ["simple", "pasos_cortos"] if "vulnerabilidad_declarada" in estado.senales_riesgo else []
        ec = Constructor(estado.idioma, primer_turno, preferencia)
        ctx = Contexto(c=c, estado=estado, customer_id=customer_id, session_id=session_id, hoy=hoy, data_as_of=data_as_of,
                       idioma=estado.idioma, ec=ec, fallas=dict(fallas or {}), t_ultimo=t0, reloj=reloj_persona,
                       modelo=modelo)
        nodo_antes = estado.nodo.name
        interp: Interpretacion | None = None
        llamadas_a1: list[RespuestaModelo] = []
        hash_a1 = None

        # Sesión vencida en medio: se pide identidad otra vez y la confirmación pendiente se vuelve a pedir (INV-CONFIRMA)
        if estado.identidad_verificada and not customer_id:
            estado.identidad_verificada = False
            ec.afirmar("sesion_vencida")
            estado.nodo = Nodo.N1
            ctx.ui.append({"tipo": "formulario_identidad"})

        # Con una persona: el mensaje va a la persona; el asistente no interviene (la conversación sigue en el chat)
        traspaso_activo = c.execute("""select * from atencion.traspasos where conversation_id = %s
                                       and estado in ('en_cola','asignado','en_atencion','esperando_cliente')""",
                                    (conversation_id,)).fetchone()
        if not traspaso_activo and estado.traspaso_id:
            # La persona resolvió o devolvió el caso: la conversación vuelve al asistente con el estado limpio (§P8 paso 6)
            estado.traspaso_id = None
            estado.sin_modelo = False
            if estado.nodo == Nodo.N11:
                estado.nodo = Nodo.N2 if estado.identidad_verificada else Nodo.N0
        if traspaso_activo and (entrada.evento or {}).get("tipo") == "aceptar_idioma":
            # §P2.5 nivel 3: el cliente acepta seguir en el idioma que se le ofreció; el caso no pierde su lugar
            aviso_antes = enrutador.posicion_y_espera(traspaso_activo["traspaso_id"])
            if aviso_antes.get("ofrece_idioma") == entrada.evento.get("idioma"):
                enrutador.cambiar_idioma_a_pedido(traspaso_activo["traspaso_id"], entrada.evento["idioma"])
            _guardar(c, estado, version_leida, customer_id)
            aviso = enrutador.posicion_y_espera(traspaso_activo["traspaso_id"])
            enrutador.asignar()
            return Salida(conversation_id, estado.version, "", [{"tipo": "aviso_espera", **aviso}], estado.nodo.name,
                          estado.sin_modelo, aviso, turn_id)
        if traspaso_activo and (entrada.evento or {}).get("tipo") == "adjunto" and not entrada.evento["tipo_archivo"].startswith("audio"):
            # Un archivo que llega con el caso ya en la fila: sin esto quedaba guardado pero el asesor nunca lo veía (el paquete se armó antes).
            ev = entrada.evento
            estado.adjuntos.append(Adjunto(adjunto_id=ev["adjunto_id"], tipo=ev["tipo_archivo"], tamano=ev["tamano"]))
            c.execute("""update atencion.traspasos set paquete = jsonb_set(paquete, '{adjuntos}',
                         coalesce(paquete->'adjuntos', '[]'::jsonb) || to_jsonb(%s::text)) where traspaso_id = %s""",
                      (ev["adjunto_id"], traspaso_activo["traspaso_id"]))
        if traspaso_activo and (entrada.texto or entrada.evento):
            texto = borrar_tarjetas(entrada.texto or "")[0]
            if texto:
                _turno(c, estado, "cliente", texto, customer_id, mensaje_cliente_id=entrada.mensaje_cliente_id)
            _guardar(c, estado, version_leida, customer_id)
            aviso = enrutador.posicion_y_espera(traspaso_activo["traspaso_id"])
            return Salida(conversation_id, estado.version, "", [{"tipo": "aviso_espera", **aviso}], estado.nodo.name,
                          estado.sin_modelo, aviso, turn_id)

        texto_guardado = None
        if entrada.evento:
            _paso_evento(ctx, entrada.evento)
            _evento(ctx, entrada.evento)
        else:
            texto, hubo_tarjeta = borrar_tarjetas(entrada.texto or "")
            grafo._paso(ctx, "filtro_sensible", "ok", tarjeta_borrada=hubo_tarjeta)
            tope = presupuesto_tokens_conversacion(c)
            if tope and estado.tokens_consumidos >= tope:
                # Presupuesto agotado: no se llama más al modelo en esta conversación; sigue con una persona (no se corta).
                # El tope lo decide el banco en la operación (0 = sin tope), no el código.
                grafo._paso(ctx, "presupuesto", "fallo", tokens=estado.tokens_consumidos, tope=tope)
                _turno(c, estado, "cliente", texto, customer_id, mensaje_cliente_id=entrada.mensaje_cliente_id)
                return _sin_modelo(ctx, version_leida, turn_id, [], texto, nodo_antes, t0,
                                   motivo_extra="presupuesto_conversacion", otra_causa=True)
            temas = conocimiento.temas("publico", hoy)
            interp = None
            try:
                r1 = interpretar(modelo, estado, texto, temas)
                interp, llamadas_a1, hash_a1 = r1.interpretacion, r1.llamadas, r1.hash_prompt
                grafo._paso(ctx, "interprete", "ok", comandos=[f"{k.nombre}({', '.join(k.args)})" for k in interp.comandos],
                            senales=interp.senales_riesgo, reconoce=interp.reconoce, idioma=interp.idioma, reintentos=r1.reintentos)
                estado.no_entendidos = 0
            except InterpretacionFallida as e:
                llamadas_a1 = e.llamadas
                grafo._paso(ctx, "interprete", "fallo", motivo=str(e))
                _turno(c, estado, "cliente", texto, customer_id, mensaje_cliente_id=entrada.mensaje_cliente_id)
                if not (e.entendible and estado.no_entendidos < 1):
                    return _sin_modelo(ctx, version_leida, turn_id, llamadas_a1, texto, nodo_antes, t0)
                # El modelo respondió pero su salida no se pudo leer, dos veces: no es una caída. Se le pide al cliente que lo diga de otra
                # forma (el texto lo redacta el modelo, no el código); si el mensaje siguiente tampoco se entiende, pasa a una persona.
                estado.no_entendidos += 1
                texto_guardado = texto
                ec.preguntar("no_se_entendio")
            if interp is not None:
                texto, n_secretos = borrar_secretos(texto, interp.datos_secretos)
                if n_secretos:
                    estado.senales_riesgo = sorted(set(estado.senales_riesgo) | {"credencial_comprometida"})
                    ec.afirmar("secreto_borrado")
                if hubo_tarjeta:
                    ec.afirmar("tarjeta_borrada")
                texto_guardado = texto
                _turno(c, estado, "cliente", texto, customer_id, mensaje_cliente_id=entrada.mensaje_cliente_id)
                _decidir(ctx, interp, texto)

        # Esperando identidad: el formulario vuelve a aparecer debajo de cada respuesta (lo manda el estado, no el texto)
        if estado.nodo == Nodo.N1 and not estado.identidad_verificada and not ctx.traspaso:
            if not any(u["tipo"] == "formulario_identidad" for u in ctx.ui):
                ctx.ui.append({"tipo": "formulario_identidad"})
            if "identidad_requerida" not in ec.hechos_usados:
                ec.afirmar("identidad_requerida")

        # Estancamiento: turnos sin ningún cambio de estado (no un conteo total)
        estado.progreso = 0 if ctx.cambio else estado.progreso + 1
        limite = grafo.MAX_SIN_PROGRESO.get(estado.nodo, grafo.MAX_SIN_PROGRESO["defecto"])
        if estado.progreso >= limite and not ctx.traspaso:
            ec.afirmar("estancamiento")
            ec.ofrecer("persona")

        # Traspaso: paquete, cola y posición real
        traspaso_info = None
        if ctx.traspaso:
            traspaso_info = _crear_traspaso(ctx, sin_resumen=False)

        # Redacción (A8 + A9) o el borrador del Intérprete si no hay hechos nuevos
        llamadas_a8: list[RespuestaModelo] = []
        try:
            # El borrador del Intérprete es texto sin hechos: vale solo para un saludo o un agradecimiento puro.
            # Cualquier otra cosa (una pregunta, un mensaje que no se entendió) va al Redactor con el estado comunicable.
            solo_charla = bool(interp) and [k.nombre for k in interp.comandos] == ["charla"] and not primer_turno
            momento = _momento_del_dia(ctx) if primer_turno else None       # el primer mensaje lleva saludo
            if ec.vacio and solo_charla and interp.borrador_respuesta:
                from servicio.redactor.redactor import ResultadoRedaccion
                from contratos.modelos import Redaccion
                from servicio.verificacion.redaccion import verificar
                red = Redaccion(texto=interp.borrador_respuesta, idioma=normalizar(estado.idioma))
                errores = verificar(red, ec.construir(), estado.idioma, ctx.completadas)
                if errores:
                    raise RedaccionFallida("; ".join(errores), [])
                rr = ResultadoRedaccion(red, [], "borrador_interprete", [], None)
            else:
                if ec.vacio:
                    ec.preguntar("que_necesita")
                rr = redactar(modelo, estado, ec.construir(), estado.idioma, ctx.completadas,
                              interp.borrador_respuesta if solo_charla else None, momento)
            llamadas_a8 = rr.llamadas
            grafo._paso(ctx, "redactor", "ok", origen=rr.origen, errores_previos=rr.errores)
            grafo._paso(ctx, "verificador_redaccion", "ok")
            if ec.articulo:                   # cortacircuitos: la respuesta con el artículo pasó al primer intento o no
                _resultado_articulo(ctx, ec.articulo, ok=not rr.errores)
        except RedaccionFallida as e:
            llamadas_a8 = e.llamadas
            grafo._paso(ctx, "redactor", "fallo", motivo=str(e))
            if ec.articulo and not str(e).startswith("modelo no disponible"):   # una caída del proveedor no es del artículo
                _resultado_articulo(ctx, ec.articulo, ok=False)
            if not ctx.traspaso:
                # El motivo dice qué pasó de verdad: el proveedor no respondió (cupo, red) o el texto no pasó la verificación
                cupo = str(e).startswith("modelo no disponible")
                return _sin_modelo(ctx, version_leida, turn_id, llamadas_a1 + ctx.llamadas + llamadas_a8, texto_guardado, nodo_antes, t0,
                                   motivo_extra=None if cupo else "falla_verificacion")
            rr = None

        construido = ec.construir()
        if rr:                                  # sin texto no se le preguntó nada: la pregunta anterior sigue siendo la última dicha
            estado.ultima_pregunta = _pregunta_del_turno(construido)
        texto_marcadores = rr.redaccion.texto if rr else ""
        texto_final = reemplazar(texto_marcadores, construido) if rr else ""
        if primer_turno and rr:
            legal = TEXTOS_LEGALES["divulgacion"][normalizar(estado.idioma)]
            saludo = rr.redaccion.saludo
            texto_final = (f"{saludo}\n" if saludo else "") + legal + "\n\n" + texto_final
        if traspaso_info and rr and rr.redaccion.resumen_para_humano:
            _completar_solicitud(c, traspaso_info["traspaso_id"], rr.redaccion.resumen_para_humano, construido)
        elif traspaso_info and rr is None:      # el Redactor falló después del traspaso: el paquete lo dice
            c.execute("""update atencion.traspasos set paquete = jsonb_set(paquete, '{sin_resumen_ia}', 'true')
                         where traspaso_id = %s""", (traspaso_info["traspaso_id"],))
        grafo._paso(ctx, "siguiente", "ok", nodo=estado.nodo.name,
                    traspaso=({"habilidad": traspaso_info["habilidad"], "prioridad": traspaso_info["prioridad"]} if traspaso_info else None))
        salida = Salida(conversation_id, version_leida + 1, texto_final, ctx.ui, estado.nodo.name, estado.sin_modelo,
                        traspaso_info and {k: traspaso_info[k] for k in ("numero", "habilidad", "prioridad", "posicion", "espera_minutos", "abre") if k in traspaso_info},
                        turn_id)
        _turno(c, estado, "asistente", texto_marcadores, customer_id,
               {"salida": salida.__dict__, "texto_final": texto_final})
        estado.tokens_consumidos += sum(r.tokens_entrada + r.tokens_salida for r in llamadas_a1 + ctx.llamadas + llamadas_a8)
        _guardar(c, estado, version_leida, customer_id)
        _registrar(ctx, turn_id, nodo_antes, interp, llamadas_a1 + ctx.llamadas + llamadas_a8, hash_a1, rr.hash_prompt if rr else None,
                   len(entrada.texto or ""), t0)
    if traspaso_info:
        enrutador.asignar()
    return salida


def _momento_del_dia(ctx: Contexto) -> str:
    """El código calcula el momento del día con el reloj de la persona."""
    from servicio.resolutor.calendario import momento_del_dia
    return momento_del_dia(ctx.reloj.zona, ctx.reloj.ahora_local)


def _reloj(c, fijado: date | None, data_as_of: date, customer_id: str | None):
    """Reloj de la persona: zona de su país (la del banco, sin sesión). La evaluación trae su reloj fijado."""
    from servicio.enrutador.enrutador import config
    from servicio.resolutor.reloj import Reloj
    pais = c.execute("select pais from servicio.clientes").fetchone()["pais"] if customer_id else None
    zona = config()["zona_horaria"].get(pais) or config()["zona_horaria_por_defecto"]
    return Reloj.fijo(fijado, zona) if fijado else Reloj.vivo(zona, data_as_of)


def _sesion_vencida(conversation_id: str, modelo: Modelo, turn_id: str) -> Salida:
    ec = Constructor("es")
    ec.afirmar("sesion_vencida")
    estado = EstadoConversacion(conversation_id=conversation_id)
    try:
        rr = redactar(modelo, estado, ec.construir(), "es", set(), None)
        texto = reemplazar(rr.redaccion.texto, ec.construir())
    except RedaccionFallida:
        texto = ""
    return Salida(conversation_id, -1, texto, [{"tipo": "formulario_identidad"}], Nodo.N1.name, False, None, turn_id)


def _paso_evento(ctx: Contexto, evento: dict):
    grafo._paso(ctx, "interprete", "no_aplica", evento=evento.get("tipo"))


MIN_CARACTERES_PARA_CAMBIAR_IDIOMA = 12     # un mensaje más corto no trae evidencia de idioma (una confirmación, una cifra)


def _fijar_idioma(ctx: Contexto, interp: Interpretacion, texto: str) -> None:
    """El idioma de la conversación. Lo pedido por el cliente (evento `cambiar_idioma`) manda y se mantiene. Lo detectado en
    el mensaje rige mientras nadie haya pedido uno: el primer mensaje lo fija y, después, solo lo cambia un mensaje con
    texto suficiente para tener idioma (un "ok" o un "não" no deben voltear la conversación)."""
    e, ec = ctx.estado, ctx.ec
    if e.idioma_pedido or not es_soportado(interp.idioma):
        return
    ya_se_habla = any(t.rol == "asistente" for t in e.historial)
    if interp.idioma != e.idioma and ya_se_habla and len(texto.strip()) < MIN_CARACTERES_PARA_CAMBIAR_IDIOMA:
        return
    e.idioma = ctx.idioma = ec.idioma = interp.idioma


def _decidir(ctx: Contexto, interp: Interpretacion, texto: str):
    """Guardas del nodo N2 y de los nodos en curso (ARQUITECTURA §6.2), en orden de lo que está en juego."""
    e, ec = ctx.estado, ctx.ec
    nombres = [k.nombre for k in interp.comandos]
    nuevas = set(interp.senales_riesgo) - set(e.senales_riesgo)
    e.senales_riesgo = sorted(set(e.senales_riesgo) | set(interp.senales_riesgo))   # monótonas
    if nuevas:
        ctx.cambio = True
    _fijar_idioma(ctx, interp, texto)
    if "vulnerabilidad_declarada" in e.senales_riesgo:
        ec.preferencia = ["simple", "pasos_cortos"]
    for k in interp.comandos:
        if k.nombre in ("dar_dato", "corregir") and len(k.args) >= 2:
            if e.datos_dados.get(k.args[0]) != k.args[1]:
                ctx.cambio = True
            e.datos_dados[k.args[0]] = k.args[1]

    if interp.idioma == "otro":                                  # B7: se atiende en español o portugués
        ec.afirmar("idioma_no_soportado")
        return
    seguridad = sorted(SEGURIDAD & set(e.senales_riesgo))
    if "manipulacion" in nuevas or ("no_puedo" in nombres and not seguridad and len(nombres) == 1):   # N2 → N14
        e.nodo = Nodo.N14
        ec.afirmar("abstencion")
        ec.afirmar("persona_disponible")
        return
    if "no_puede_identificarse" in nombres and not e.identidad_verificada:     # C3, D8: nada sin identidad
        ec.afirmar("sin_codigo_alternativa")
        ec.afirmar("identidad_no_verificada")
        grafo.pedir_traspaso(ctx, (seguridad or []) + ["identidad_no_verificada"])
        return
    if seguridad and nuevas & set(seguridad) or (seguridad and _pide_accion_de_cuenta(interp) and not e.traspaso_id):
        if "consulta_informativa" in nombres:                    # la pregunta se responde también (D7)
            _consulta(ctx, interp, texto, fuera=False)
        if not e.identidad_verificada:
            # Sin sesión: se pide la identidad para poder proteger el producto y se recuerda que hay una persona.
            # Si no puede identificarse (no_puede_identificarse o tres códigos fallidos), N0/N1 → N11 sin datos.
            grafo.pedir_identidad(ctx, "tarjetas.bloquear" if "producto_en_manos_de_otro" in seguridad else None)
            ec.afirmar("proteccion_tras_identidad")         # por qué identificarse: para bloquear ya
            ec.afirmar("persona_disponible")
        else:
            grafo.ofrecer_proteccion_y_traspaso(ctx, seguridad)
        return
    if "vulnerabilidad_declarada" in nuevas:                     # N2 → N11, prioridad 2, sin más preguntas
        grafo.pedir_traspaso(ctx, ["vulnerabilidad_declarada"])
        return
    if "pedir_persona" in nombres:
        if "consulta_informativa" in nombres:                    # se responde la pregunta y se pasa a la persona (B10)
            _consulta(ctx, interp, texto, fuera=False)
        grafo.pedir_traspaso(ctx, ["pedir_persona"])
        return

    # Confirmar o negar la acción propuesta
    if e.accion_pendiente and "confirmar" in nombres:
        # Una acción con efectos se ejecuta por texto solo si el Intérprete leyó únicamente una confirmación. Con otra cosa a la vez
        # ("listo, ese es bueno, chao" se leyó como confirmar + charla y abrió un reclamo que el cliente no quería) no se ejecuta:
        # se recuerda lo pendiente y el cliente lo confirma con el botón.
        if set(nombres) == {"confirmar"}:
            grafo.ejecutar_pendiente(ctx)
        else:
            ec.afirmar("pendiente_recordado", sobre=grafo.tema_actual(e))
        return
    if e.accion_pendiente and "negar" in nombres:
        _negar(ctx)
        return

    # Consultas laterales: se responde y se vuelve al mismo nodo con el estado intacto
    if "consulta_informativa" in nombres or "fuera_de_alcance" in nombres:
        _consulta(ctx, interp, texto, fuera="fuera_de_alcance" in nombres)
        if not any(n in nombres for n in ("iniciar", "elegir", "dar_dato", "corregir")) and interp.reconoce == "ninguna":
            if e.accion_pendiente or e.nodo in (Nodo.N4, Nodo.N5, Nodo.N7):
                ec.afirmar("pendiente_recordado", sobre=grafo.tema_actual(e))
            return

    # Elegir una opción mostrada: se valida contra lo mostrado (nunca contra el texto libre)
    elegido = next((k.args[0] for k in interp.comandos if k.nombre == "elegir" and k.args), None)
    if elegido is None and e.opciones_mostradas and e.nodo == Nodo.N4 and interp.cargos_referidos:
        elegido = _elegir_por_datos(ctx, interp)
    if elegido and elegido in e.opciones_mostradas:
        _elegir(ctx, elegido)
        return

    intencion = next((k.args[0] for k in interp.comandos if k.nombre == "iniciar" and k.args), None)
    if intencion is None and not grafo.tema_actual(e):       # campo de una sola intención: la intención sale del esquema
        propios = catalogo.cargar().get("campos_de_intencion", {})
        intencion = next((propios[k.args[0]] for k in interp.comandos if k.nombre == "dar_dato" and k.args and k.args[0] in propios), None)
    # Reconoce / no reconoce sobre el cargo mostrado (N5)
    actual = grafo._cargo_actual(e)
    if actual and interp.reconoce in ("si", "no", "no_seguro") and intencion in (None, "disputas.reportar_cargo"):
        _reconoce(ctx, actual, interp.reconoce, interp)
        return
    if intencion:
        if intencion in grafo.INTENCIONES_CON_CUENTA and not e.identidad_verificada:
            grafo.pedir_identidad(ctx, intencion, interp.cargos_referidos)
            return
        e.nodo = Nodo.N2
        grafo.ruta(ctx, intencion, interp)
        return
    # Datos nuevos para el tema en curso (corrección o dato pedido)
    if (interp.cargos_referidos or any(n in ("dar_dato", "corregir") for n in nombres)) and grafo.tema_actual(e):
        tema = grafo.tema_actual(e)
        if tema in grafo.INTENCIONES_CON_CUENTA and not e.identidad_verificada:
            grafo.pedir_identidad(ctx, None)
            return
        grafo.ruta(ctx, tema, interp)
        return
    if "cancelar" in nombres:
        intenciones.descartar_pendientes(ctx.c, e.conversation_id)
        e.accion_pendiente = None
        grafo.desapilar(e)
        ec.preguntar("otra_ayuda")
        ctx.cambio = True
        return
    if "aclarar" in nombres:
        ec.preguntar("que_necesita")
        return
    if "charla" in nombres or not nombres:
        return
    ec.preguntar("que_necesita")


def _pide_accion_de_cuenta(interp: Interpretacion) -> bool:
    return any(k.nombre == "iniciar" and k.args and k.args[0] in grafo.INTENCIONES_CON_CUENTA for k in interp.comandos)


def _elegir_por_datos(ctx: Contexto, interp: Interpretacion) -> str | None:
    """Elegir entre las opciones mostradas por un dato: el monto y la fecha los filtra el código; la descripción
    (comercio o tipo de operación) la compara el Comparador por el sentido. Elige solo si queda una."""
    from servicio.resolutor import comparador
    from servicio.resolutor.resolutor import resolver
    ref = interp.cargos_referidos[0]
    por_datos = []
    for alias in ctx.estado.opciones_mostradas:
        c = grafo._cargo(ctx.estado, alias)
        if not c:
            continue
        tx = banco.obtener_transaccion(ctx.c, c.transaction_ref_interno)
        tx = {**tx, "fecha": tx["fecha"].date(), "monto": float(tx["monto"]), "amount_usd": float(tx["amount_usd"] or 0),
              "_alias": alias}
        if resolver(ref, [tx], ctx.hoy, ctx.data_as_of, ctx.reloj).clase == "1":
            por_datos.append(tx)
    if ref.descripcion and len(por_datos) > 1:
        comp = comparador.comparar(ctx.modelo, ref.descripcion, por_datos, ctx.idioma)
        ctx.llamadas += comp.llamadas
        grafo._paso(ctx, "comparador", "ok" if comp.candidatos is not None else "fallo", motivo=comp.motivo,
                    entran=len(por_datos), coinciden=None if comp.candidatos is None else len(comp.candidatos))
        por_datos = comp.candidatos if comp.candidatos is not None else por_datos
    return por_datos[0]["_alias"] if len(por_datos) == 1 else None


def _elegir(ctx: Contexto, alias: str):
    e = ctx.estado
    ctx.cambio = True
    if alias.startswith("P"):                                     # producto
        product_id = e.datos_dados.get(f"_producto_{alias}")
        tema = e.pila_temas[-1] if e.pila_temas else {}
        despues = (tema.get("estado_guardado") or {}).get("traspaso_despues")
        p = next(x for x in banco.listar_productos(ctx.c) if x["product_id"] == product_id)
        from servicio.redactor import formato
        texto = formato.producto(p["tipo"], p["ultimos4"], ctx.idioma)
        if tema.get("tema") == "tarjetas.desbloquear":
            grafo.desbloquear(ctx, p)
        else:
            grafo.proponer(ctx, "bloquear_producto", product_id, {"product_id": product_id, "origen": "cliente",
                                                                 "motivo": ",".join(despues or []) or None, "producto_texto": texto},
                           None, {"PRODUCTO": texto}, traspaso_despues=despues)
        e.opciones_mostradas = []
        return
    c = grafo._cargo(e, alias)
    tx = banco.obtener_transaccion(ctx.c, c.transaction_ref_interno)
    tx = {**tx, "hora": tx["fecha"].strftime("%H:%M"), "fecha": tx["fecha"].date(),
          "monto": float(tx["monto"]) if tx["monto"] is not None else None}
    grafo.mostrar_cargo(ctx, tx, alias)


def _reconoce(ctx: Contexto, cargo, valor: str, interp: Interpretacion):
    e, ec = ctx.estado, ctx.ec
    ctx.cambio = True
    if valor == "si" and e.accion_pendiente and e.accion_pendiente.codigo == "abrir_reclamo":
        intenciones.marcar(ctx.c, e.accion_pendiente.action_intent_id, "descartada")   # lo reconoció al ver el detalle
        e.accion_pendiente = None
    if valor == "si":
        if {"engano_por_tercero", "coaccion"} & set(e.senales_riesgo):         # estafa autorizada: nunca "usted lo autorizó"
            e.tipo_disputa = "estafa_autorizada"
            grafo.ofrecer_proteccion_y_traspaso(ctx, sorted({"engano_por_tercero", "coaccion"} & set(e.senales_riesgo)))
            return
        cargo.estado = "reconocido"
        grafo.registrar_reconocido_con_senal(ctx, cargo)
        e.nodo = Nodo.N12
        ec.ofrecer("abrir_reclamo", cargo.alias)                 # el derecho a reclamar es del cliente
        ec.preguntar("otra_ayuda")
        grafo.desapilar(e)
        return
    if valor == "no_seguro" and e.datos_dados.get(f"_no_seguro_{cargo.alias}") != "si":
        e.datos_dados[f"_no_seguro_{cargo.alias}"] = "si"      # se muestra una vez más; si persiste, cuenta como no
        tx = banco.obtener_transaccion(ctx.c, cargo.transaction_ref_interno)
        tx = {**tx, "hora": tx["fecha"].strftime("%H:%M"), "fecha": tx["fecha"].date(), "monto": float(tx["monto"])}
        grafo.mostrar_cargo(ctx, tx, cargo.alias)
        return
    if interp and interp.tipo_disputa_propuesto and interp.tipo_disputa_propuesto != "reconocida":
        e.tipo_disputa = interp.tipo_disputa_propuesto
    grafo.evaluar_no_reconocido(ctx, cargo)


def _negar(ctx: Contexto):
    e = ctx.estado
    p = e.accion_pendiente
    i = ctx.c.execute("select parametros from atencion.intenciones_accion where action_intent_id = %s", (p.action_intent_id,)).fetchone()
    params = (i or {}).get("parametros") or {}
    params = params if isinstance(params, dict) else json.loads(params)
    intenciones.marcar(ctx.c, p.action_intent_id, "descartada")
    e.accion_pendiente = None
    ctx.cambio = True
    if params.get("traspaso_despues"):                             # rechazó el bloqueo: igual pasa a fraude
        grafo.pedir_traspaso(ctx, params["traspaso_despues"])
        return
    if p.codigo == "abrir_reclamo":
        e.nodo = Nodo.N12
        ctx.ec.ofrecer("abrir_reclamo", p.alias)
    ctx.ec.preguntar("otra_ayuda")


def _consulta(ctx: Contexto, interp: Interpretacion, texto: str, fuera: bool):
    tema = next((k.args[0] for k in interp.comandos if k.nombre == "consulta_informativa" and k.args), None)
    pais = grafo._cliente(ctx).get("pais") if ctx.estado.identidad_verificada else None
    art = conocimiento.servir(ctx.c, tema, pais, ctx.idioma, ctx.hoy) if tema else None
    via = "tema"
    categoria = next((k.args[0] for k in interp.comandos if k.nombre == "fuera_de_alcance" and k.args), None)
    if art is None:
        # Una gestión fuera de alcance no se busca por las palabras sueltas del mensaje (una sola palabra común, "tarjeta", elige el
        # artículo equivocado: B3), sino por la categoría que declaró el Intérprete ("cambio de clave"), y el artículo debe contener todas sus palabras.
        consulta = categoria.replace("_", " ") if fuera and categoria else (None if fuera else texto)
        encontrados = conocimiento.buscar(ctx.c, consulta, pais, ctx.idioma, ctx.hoy, todas=fuera) if consulta else []
        art, via = (encontrados[0], "texto") if encontrados else (None, None)
    grafo._paso(ctx, "conocimiento", "ok" if art else "fallo", articulo=art and f"{art['id']}@{art['version']}", via=via)
    if fuera:
        ctx.estado.nodo = Nodo.N13 if not ctx.estado.accion_pendiente else ctx.estado.nodo
        ctx.ec.afirmar("fuera_de_alcance", categoria=categoria)
    if art:
        ctx.ec.responder(art)         # si el artículo no alcanza, el Redactor lo declara (suficiencia) y ofrece una persona; no se ofrece de más
    else:
        ctx.ec.afirmar("persona_disponible")
    ctx.cambio = True


def _evento(ctx: Contexto, ev: dict):
    """Eventos del canal: no pasan por el Intérprete; se validan contra lo que se le mostró al cliente."""
    e, ec, tipo = ctx.estado, ctx.ec, ev.get("tipo")
    if tipo == "identidad_verificada":
        if not ctx.customer_id:
            ec.afirmar("identidad_requerida")
            ctx.ui.append({"tipo": "formulario_identidad"})
            return
        e.identidad_verificada = True
        e.nodo = Nodo.N2
        ec.afirmar("identidad_verificada")
        ctx.cambio = True
        avisos = ctx.c.execute("select count(*) n from atencion.avisos_cliente where not leido").fetchone()["n"]
        if avisos:
            ec.afirmar("avisos_pendientes", valores={"CANTIDAD": str(avisos)})
        if e.accion_pendiente:                                   # tras re-autenticarse, la confirmación se pide de nuevo
            grafo.ejecutar_pendiente(ctx)
            return
        seguridad = sorted(SEGURIDAD & set(e.senales_riesgo))
        if seguridad and not e.traspaso_id:                      # proteger va antes que esperar
            if grafo.tema_actual(e) == "tarjetas.bloquear":
                grafo.desapilar(e)
            grafo.ofrecer_proteccion_y_traspaso(ctx, seguridad)
            return
        tema = e.pila_temas[-1] if e.pila_temas else None
        if tema:
            from contratos.modelos import CargoReferido
            refs = [CargoReferido(**c) for c in (tema.get("estado_guardado") or {}).get("cargos_referidos", [])]
            interp = Interpretacion(cargos_referidos=refs, tipo_disputa_propuesto=e.tipo_disputa)
            grafo.ruta(ctx, tema["tema"], interp)
        else:
            ec.preguntar("que_necesita")
        return
    if tipo == "identidad_fallida":                              # N1 → N11: tres códigos fallidos
        grafo.pedir_traspaso(ctx, ["codigos_fallidos", "identidad_no_verificada"])
        ec.afirmar("identidad_no_verificada")
        return
    if not e.identidad_verificada and tipo in ("no_reconozco", "reconoce", "confirmar", "elegir"):
        grafo.pedir_identidad(ctx, "disputas.reportar_cargo")
        return
    if tipo == "no_reconozco":                                    # desde "Mis movimientos": el cargo llega identificado
        ref = ev.get("ref")
        tx = banco.obtener_transaccion(ctx.c, ref)                # RLS: solo movimientos del titular
        tx = {**tx, "hora": tx["fecha"].strftime("%H:%M"), "fecha": tx["fecha"].date(), "monto": float(tx["monto"])}
        grafo.apilar(e, "disputas.reportar_cargo")
        e.tipo_disputa = e.tipo_disputa or "no_autorizada"
        alias = grafo._nuevo_alias(e)
        e.cargos.append(__import__("contratos.modelos", fromlist=["CargoEnDiscusion"]).CargoEnDiscusion(
            alias=alias, atributos={"estado": tx["estado"]}, estado="mostrado", transaction_ref_interno=tx["transaction_id"]))
        grafo.evaluar_no_reconocido(ctx, grafo._cargo(e, alias))
        ctx.ui.append(grafo._tarjeta_ui(alias, tx, ctx.idioma, ctx.reloj))
        return
    if tipo == "reconoce":
        actual = grafo._cargo_actual(e)
        if actual and ev.get("valor") in ("si", "no", "no_seguro"):
            _reconoce(ctx, actual, ev["valor"], None)
        return
    if tipo == "confirmar":
        grafo.ejecutar_pendiente(ctx, ev.get("action_intent_id"))
        return
    if tipo == "negar" and e.accion_pendiente:
        _negar(ctx)
        return
    if tipo == "elegir" and ev.get("alias") == "ninguno" and e.opciones_mostradas:
        grafo.ninguno_de_los_mostrados(ctx)
        return
    if tipo == "elegir" and ev.get("alias") in e.opciones_mostradas:
        _elegir(ctx, ev["alias"])
        return
    if tipo == "pedir_persona":
        grafo.pedir_traspaso(ctx, ["pedir_persona"])
        return
    if tipo == "cambiar_idioma":                                  # el selector ES/PT del chat: lo pedido manda y se mantiene
        pedido = ev.get("idioma")
        if not es_soportado(pedido):
            ec.afirmar("idioma_no_soportado")
            return
        if pedido != e.idioma:
            ec.afirmar("idioma_cambiado")
            ctx.cambio = True
        e.idioma = ctx.idioma = ec.idioma = pedido
        e.idioma_pedido = True
        if e.accion_pendiente or e.nodo in (Nodo.N4, Nodo.N5, Nodo.N7):     # a mitad de un trámite: se retoma
            ec.afirmar("pendiente_recordado", sobre=grafo.tema_actual(e))
        else:
            ec.preguntar("que_necesita")
        return
    if tipo == "adjunto":                                         # nada bloquea: se recibe y se responde en el mismo nodo
        adj = Adjunto(adjunto_id=ev["adjunto_id"], tipo=ev["tipo_archivo"], tamano=ev["tamano"])
        e.adjuntos.append(adj)
        ctx.cambio = True
        if ev["tipo_archivo"].startswith("audio"):
            ec.afirmar("audio_no_soportado")
            return
        ec.afirmar("adjunto_recibido", valores=None, tipo=ev["tipo_archivo"])
        # Solo se afirma lo verificado: quién lo verá depende del estado real, nunca se promete que alguien lo esté mirando.
        if e.identidad_verificada:
            activos = [r for r in banco.listar_reclamos(ctx.c) if r["estado"] in banco.ACTIVOS]
            if len(activos) == 1:
                r = activos[0]
                grafo.proponer(ctx, "agregar_informacion_reclamo", r["reclamo_id"],
                               {"reclamo_id": r["reclamo_id"], "numero": r["numero"], "adjunto_id": adj.adjunto_id},
                               r["numero"], {"CASO": r["numero"]})
                return
        ec.afirmar("adjunto_sin_revision")
        return


# ---------------------------------------------------------------- traspaso y sin modelo

def _crear_traspaso(ctx: Contexto, sin_resumen: bool) -> dict:
    e = ctx.estado
    cli = grafo._cliente(ctx) if ctx.customer_id else {}
    from servicio.redactor import formato
    hechos, en_juego = [], []
    idioma_eq = "es"                          # el panel del equipo está en español
    for cg in e.cargos:
        if cg.estado not in ("mostrado", "no_reconocido", "reclamado", "reconocido"):
            continue
        tx = banco.obtener_transaccion(ctx.c, cg.transaction_ref_interno) if cg.transaction_ref_interno else None
        idioma = normalizar(e.idioma)
        detalle = {"movimiento": formato.movimiento(tx["tipo"], idioma), "comercio": tx["comercio"],
                   "monto": formato.monto(float(tx["monto"]) if tx["monto"] is not None else None, tx["moneda"]),
                   "fecha": formato.fecha(ctx.reloj.a_local(tx["fecha"].date()), idioma)} if tx else {}
        hechos.append({"campo": "cargo", "valor": cg.alias, "estado": cg.estado, "fuente": "base",
                       **{k: v for k, v in detalle.items() if v}})
        if tx and cg.estado in ("no_reconocido", "reclamado") and dinero_en_juego(tx["tipo"], tx["amount_usd"]):
            en_juego.append({"alias": cg.alias, **dinero_en_juego(tx["tipo"], tx["amount_usd"])})
    # Todo lo hecho en la conversación, no solo en este turno: el asesor no pregunta ni repite lo ya hecho (R5)
    acciones = [{"accion": a["accion"], "estado": a["estado"], "resultado": a["resultado"] or {}} for a in ctx.c.execute(
        """select accion, estado, resultado from atencion.intenciones_accion where conversation_id = %s
           and estado in ('completada','desconocida') order by creado""", (e.conversation_id,)).fetchall()]
    evidencia = {"senal": ctx.senal_evidencia, "decision": ctx.decision,
                 "transacciones": [c.transaction_ref_interno for c in e.cargos if c.estado != "candidato"]}
    if en_juego:
        evidencia["dinero_en_juego"] = en_juego
    t = ctx.traspaso or {"motivos": [], "preguntas": [], "supera_umbral": False, "plazo": None}
    plazo = t["plazo"]
    if plazo and plazo.get("vence"):         # la persona del equipo lo lee en la fecha real del cliente, como él
        plazo = {**plazo, "vence_cliente": formato.fecha(ctx.reloj.a_local(plazo["vence"]), idioma_eq)}
    paquete = armar_paquete(e, t["motivos"], hechos, acciones, evidencia, t["preguntas"], t["supera_umbral"],
                            plazo, cli.get("pais"), ctx.hoy, None, sin_resumen, dinero_en_juego=bool(en_juego))
    fila = enrutador.crear_traspaso(ctx.c, paquete.model_dump(mode="json"), e.conversation_id, ctx.customer_id,
                                    cli.get("segmento"))
    e.traspaso_id = fila["traspaso_id"]
    e.nodo = Nodo.N11
    ya = fila.get("ya_activo", False)
    ctx.ec.afirmar("traspaso_ya_activo" if ya else "traspaso")
    aviso = enrutador.posicion_y_espera_con(ctx.c, fila)
    ctx.ui.append({"tipo": "aviso_espera", "numero": fila["numero"], **aviso})
    grafo._paso(ctx, "traspaso", "ok", habilidad=fila["habilidad"], prioridad=fila["prioridad"], numero=fila["numero"],
                sin_resumen_ia=sin_resumen)
    return {"traspaso_id": fila["traspaso_id"], "numero": fila["numero"], "habilidad": fila["habilidad"],
            "prioridad": fila["prioridad"], **aviso}


def _completar_solicitud(c, traspaso_id: str, resumen: str, ec) -> None:
    """El resumen llega con marcadores, como el texto al cliente: se llenan con los valores verificados. Si queda un
    marcador sin valor, el resumen no se guarda; el asesor tiene los hechos verificados en el paquete."""
    resumen = reemplazar(resumen, ec)
    if re.search(r"[{}]", resumen):
        return
    c.execute("""update atencion.traspasos set paquete = jsonb_set(paquete, '{solicitud}', to_jsonb(%s::text))
                 where traspaso_id = %s""", (resumen[:300], traspaso_id))


def _sin_modelo(ctx: Contexto, version_leida: int, turn_id: str, llamadas: list[RespuestaModelo], texto: str | None,
                nodo_antes: str, t0: float, motivo_extra: str | None = None, preguntas: list[str] | None = None,
                otra_causa: bool = False) -> Salida:
    """ARQUITECTURA §8.4 y PROCESOS §P8: nada se ejecuta; A11 enruta por el estado; el cliente ve el aviso de espera.
    `otra_causa`: el modelo está disponible, pero la conversación sigue con una persona por otra razón (una falla no
    prevista, el presupuesto agotado); el motivo lo dice y no se marca `sin_modelo`."""
    e = ctx.estado
    e.sin_modelo = not otra_causa
    motivos = [m for m in enrutar_sin_modelo(e) if not (otra_causa and m == "sin_modelo")] + ([motivo_extra] if motivo_extra else [])
    ctx.traspaso = {"motivos": motivos, "preguntas": preguntas or [], "supera_umbral": False, "plazo": None}
    ctx.ec = Constructor(e.idioma)                   # no se redacta nada: sin modelo no hay texto
    info = _crear_traspaso(ctx, sin_resumen=True)
    ctx.c.execute("insert into atencion.traspaso_eventos (traspaso_id, evento, detalle) values (%s,%s,%s)",
                  (info["traspaso_id"], "alarma_sin_modelo" if not otra_causa else
                   "alarma_falla_sistema" if motivo_extra == "falla_del_sistema" else "traspaso_por_" + (motivo_extra or "otra_causa"),
                   json.dumps({"motivos": motivos})))
    ui = [u for u in ctx.ui if u["tipo"] == "aviso_espera"]
    salida = Salida(e.conversation_id, version_leida + 1, "", ui, e.nodo.name, True,
                    {k: info[k] for k in ("numero", "habilidad", "prioridad", "posicion", "espera_minutos", "abre") if k in info},
                    turn_id)
    _turno(ctx.c, e, "sistema", "", ctx.customer_id, {"salida": salida.__dict__})
    e.tokens_consumidos += sum(r.tokens_entrada + r.tokens_salida for r in llamadas)
    _guardar(ctx.c, e, version_leida, ctx.customer_id)
    _registrar(ctx, turn_id, nodo_antes, None, llamadas, None, None, len(texto or ""), t0)
    return salida


def presupuesto_tokens_conversacion(c) -> int:
    from servicio.registro import parametros
    return parametros.leer(c, "presupuesto_tokens_conversacion")


def _resultado_articulo(ctx: Contexto, art: dict, ok: bool) -> None:
    estado = conocimiento.resultado(ctx.c, art, ok)
    if estado == "inactivo":
        grafo._paso(ctx, "conocimiento", "fallo", articulo=f"{art['id']}@{art['version']}", motivo="cortacircuitos")


def _rescate(conversation_id: str, token: str | None, reloj: date | None, turn_id: str, referencia) -> Salida | None:
    """Una falla no prevista revirtió el turno. En una transacción nueva, la conversación pasa a una persona por el mismo
    camino que sin modelo, con la referencia del incidente; el mensaje que falló no se guarda (pudo traer un secreto
    que el Intérprete no alcanzó a marcar) y el paquete le pide al asesor que el cliente lo repita. Si el rescate
    también falla, queda registrado y devuelve None: la API responde el error con la referencia."""
    from servicio.registro.consumo import registrar_incidente
    t0 = time.monotonic()
    claims = leer_token(token)
    customer_id = claims["sub"] if claims and claims.get("rol") == "cliente" else None
    try:
        with transaccion("app_ejecucion", customer_id=customer_id, conversation_id=conversation_id) as c:
            estado, conv = _cargar(c, conversation_id, customer_id, reloj)
            data_as_of = c.execute("select data_as_of from servicio.datos_version").fetchone()["data_as_of"]
            reloj_persona = _reloj(c, conv["reloj"], data_as_of, customer_id)
            ctx = Contexto(c=c, estado=estado, customer_id=customer_id, session_id=claims.get("sid") if claims else None,
                           hoy=reloj_persona.hoy_datos, data_as_of=data_as_of, idioma=estado.idioma,
                           ec=Constructor(estado.idioma), t_ultimo=t0, reloj=reloj_persona)
            grafo._paso(ctx, "rescate", "ok", incidente=referencia)
            return _sin_modelo(ctx, estado.version, turn_id, [], None, estado.nodo.name, t0,
                               motivo_extra="falla_del_sistema", otra_causa=True,
                               preguntas=[f"el último mensaje del cliente no se procesó (incidente {referencia}): pedir que lo repita"])
    except Exception as e2:
        registrar_incidente("orquestador.rescate", e2, severidad="critica", mensaje=f"falló el rescate del incidente {referencia}")
        return None


def _registrar(ctx: Contexto, turn_id: str, nodo_antes: str, interp: Interpretacion | None, llamadas: list[RespuestaModelo],
               hash_a1: str | None, hash_a8: str | None, tamano: int, t0: float):
    """A13: sin PII; versiones, decisiones, pasos, tokens y latencia."""
    e = ctx.estado
    registro = {
        "turn_id": turn_id, "conversation_id": e.conversation_id, "n": len(e.historial),
        "versiones": {"politica": motor.version_politica(), "hash_politica": motor.hash_politica(),
                      "catalogo": catalogo.hash_catalogo(), "prompt_interprete": hash_a1, "prompt_redactor": hash_a8,
                      "modelo": ",".join(sorted({r.modelo for r in llamadas})) or None},
        "nodo_antes": nodo_antes, "nodo_despues": e.nodo.name, "pasos": ctx.pasos,
        "interpretacion": interp.model_dump(exclude={"borrador_respuesta", "datos_secretos"}) if interp else None,
        "decision": ctx.decision, "senales": e.senales_riesgo,
        "acciones": [{"accion": a["accion"], **({"numero": a["resultado"].get("numero")} if a["resultado"].get("numero") else {})}
                     for a in ctx.acciones_realizadas],
        "tokens": {"entrada": sum(r.tokens_entrada for r in llamadas), "salida": sum(r.tokens_salida for r in llamadas),
                   "llamadas": len(llamadas)},
        "latencia_ms": round((time.monotonic() - t0) * 1000, 1), "sin_modelo": e.sin_modelo,
        "espera_cupo_ms": round(sum(r.espera_s for r in llamadas) * 1000, 1),
        "creado": datetime.now(timezone.utc).isoformat()}
    ctx.c.execute("insert into operacion.registro_turnos (turn_id, conversation_id, customer_id, n, registro) values (%s,%s,%s,%s,%s)",
                  (turn_id, e.conversation_id, ctx.customer_id, registro["n"], json.dumps(registro, default=str)))
    # Cada fila es una llamada que respondió; la que falló queda en su paso del registro con el motivo (p. ej. 429)
    # cada llamada al modelo ya quedó registrada por sí sola, con su resultado y su razón (servicio/registro/consumo.py)
