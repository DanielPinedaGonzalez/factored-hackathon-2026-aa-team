"""A13 — Reconstrucción de una conversación para auditoría (GOBERNANZA_DATOS_IA, SEGURIDAD §3).

Une en una sola línea de tiempo todo lo que quedó en la base sobre una conversación: qué escribió el cliente (ya sin
tarjetas ni secretos), qué entendió el Intérprete, qué decidió la política con sus números, qué herramienta corrió y
qué se releyó, qué redactó el modelo y si pasó la verificación, cada llamada al modelo (componente, modelo, hash del
prompt, id del proveedor, tokens, latencia, espera de cupo), cada acción con su intención, cada evento del caso humano
(quién lo tomó, transfirió, pidió una sugerencia de IA, cerró), cada mensaje del asesor con su origen y cada acceso a
datos personales. Responde quién, qué, dónde, cuándo y con qué resultado, y marca lo que falló.

Solo lectura, con el rol del supervisor (la RLS lo permite y el acceso queda registrado por la API).
"""
from __future__ import annotations

import json

from servicio.datos.db import transaccion


def _e(hora, quien: str, donde: str, que: str, resultado: str = "ok", **detalle) -> dict:
    return {"hora": hora, "quien": quien, "donde": donde, "que": que, "resultado": resultado,
            "detalle": {k: v for k, v in detalle.items() if v not in (None, [], {})}}


def resolver_referencia(ref: str) -> str | None:
    """Número de caso humano (T-…), de reclamo (R-…) o la conversación misma; también en el archivo del reinicio."""
    ref = ref.strip()
    with transaccion("app_supervisor") as c:
        for sql in ("select conversation_id from atencion.traspasos where numero = %s",
                    "select conversation_id from atencion.reclamos where numero = %s",
                    "select conversation_id from operacion.archivo_reinicio where tabla in ('traspasos','reclamos') and fila->>'numero' = %s",
                    "select conversation_id from atencion.conversaciones where conversation_id = %s"):
            f = c.execute(sql, (ref,)).fetchone()
            if f and f["conversation_id"]:
                return f["conversation_id"]
    return None


def linea_de_tiempo(conversation_id: str) -> dict:
    with transaccion("app_supervisor") as c:
        conv = c.execute("select * from atencion.conversaciones where conversation_id = %s", (conversation_id,)).fetchone()
        if conv is None:
            return {"encontrada": False}
        turnos = c.execute("select n, rol, texto, respuesta, creado from atencion.turnos where conversation_id = %s order by n",
                           (conversation_id,)).fetchall()
        registros = c.execute("select turn_id, n, registro, creado from operacion.registro_turnos where conversation_id = %s order by creado",
                              (conversation_id,)).fetchall()
        llamadas = c.execute("select * from operacion.consumo_modelos where conversation_id = %s order by id",
                             (conversation_id,)).fetchall()
        intenciones = c.execute("""select action_intent_id, accion, estado, parametros, resultado, creado
                                   from atencion.intenciones_accion where conversation_id = %s order by creado""",
                                (conversation_id,)).fetchall()
        reclamos = c.execute("select reclamo_id, numero from atencion.reclamos where conversation_id = %s", (conversation_id,)).fetchall()
        rec_eventos = c.execute("""select e.*, r.numero from atencion.reclamo_eventos e join atencion.reclamos r using (reclamo_id)
                                   where r.conversation_id = %s order by e.id""", (conversation_id,)).fetchall()
        blq_eventos = c.execute("""select e.*, b.action_intent_id from atencion.bloqueo_eventos e join atencion.bloqueos b using (bloqueo_id)
                                   where b.action_intent_id in (select action_intent_id from atencion.intenciones_accion
                                                                where conversation_id = %s)
                                      or (e.autor_tipo = 'asesor' and b.customer_id = %s)
                                   order by e.id""", (conversation_id, conv["customer_id"])).fetchall()
        traspasos = c.execute("select traspaso_id, numero from atencion.traspasos where conversation_id = %s", (conversation_id,)).fetchall()
        # Lo que el reinicio de la demo archivó antes de borrar (operacion.archivo_reinicio): la historia no se pierde
        archivo: dict[str, list[dict]] = {}
        for f in c.execute("select tabla, fila from operacion.archivo_reinicio where conversation_id = %s order by id",
                           (conversation_id,)).fetchall():
            archivo.setdefault(f["tabla"], []).append({**f["fila"], "archivado": True})
        traspasos += [{"traspaso_id": t["traspaso_id"], "numero": t["numero"]} for t in archivo.get("traspasos", [])]
        ids = [t["traspaso_id"] for t in traspasos]
        tr_eventos = c.execute("""select e.*, t.numero from atencion.traspaso_eventos e join atencion.traspasos t using (traspaso_id)
                                  where e.traspaso_id = any(%s) order by e.id""", (ids,)).fetchall()
        mensajes = c.execute("select * from atencion.mensajes_asesor where conversation_id = %s order by id", (conversation_id,)).fetchall()
        accesos = c.execute("select * from operacion.accesos_pii where traspaso_id = any(%s) order by id", (ids,)).fetchall()
        incidentes = c.execute("select * from operacion.incidentes where conversation_id = %s order by id", (conversation_id,)).fetchall()

    from datetime import datetime
    numeros = {r["reclamo_id"]: r["numero"] for r in archivo.get("reclamos", [])}
    reclamos = list(reclamos) + [{"reclamo_id": r["reclamo_id"], "numero": r["numero"]} for r in archivo.get("reclamos", [])]
    rec_eventos = list(rec_eventos) + [{**e, "numero": numeros.get(e["reclamo_id"]), "creado": datetime.fromisoformat(e["creado"])}
                                       for e in archivo.get("reclamo_eventos", [])]
    blq_eventos = list(blq_eventos) + [{**e, "action_intent_id": None, "creado": datetime.fromisoformat(e["creado"])}
                                       for e in archivo.get("bloqueo_eventos", [])]
    tr_eventos = list(tr_eventos) + [{**e, "creado": datetime.fromisoformat(e["creado"])} for e in archivo.get("traspaso_eventos", [])]
    mensajes = list(mensajes) + [{**m, "creado": datetime.fromisoformat(m["creado"])} for m in archivo.get("mensajes_asesor", [])]
    eventos: list[dict] = []
    for t in turnos:
        if t["rol"] == "cliente":
            eventos.append(_e(t["creado"], "cliente", "chat", "escribió", texto=t["texto"]))
        elif t["rol"] == "asistente":
            r = t["respuesta"] or {}
            eventos.append(_e(t["creado"], "asistente", "chat", "respondió", texto=r.get("texto_final", t["texto"]),
                              ui=[u.get("tipo") for u in (r.get("salida") or {}).get("ui", [])]))
        else:
            eventos.append(_e(t["creado"], "sistema", "chat", "sin modelo: aviso de espera, sin texto", "fallo"))
    por_turno = {}
    for l in llamadas:
        por_turno.setdefault(l["turn_id"], []).append(l)
    for reg in registros:
        r = reg["registro"]
        for p in r.get("pasos", []):
            eventos.append(_e(reg["creado"], p["componente"], f"turno {r['n']} · {r['nodo_antes']}→{r['nodo_despues']}",
                              "paso", p["estado"], latencia_ms=p.get("latencia_ms"), **p.get("detalle", {})))
        if r.get("decision"):
            eventos.append(_e(reg["creado"], "politica", f"turno {r['n']}", "decidió",
                              "ok" if r["decision"].get("permitido", True) else "negado", **r["decision"]))
        for l in por_turno.get(reg["turn_id"], []):
            eventos.append(_e(l["creado"], f"modelo {l['modelo']}", f"turno {r['n']} · {l['proposito']}", "llamada al modelo",
                              l["resultado"], proveedor=l["proveedor"], llave=l.get("llave"), error=l.get("error"),
                              http_estado=l.get("http_estado"), request_id=l.get("request_id"), hash_prompt=l["hash_prompt"],
                              tokens=l["tokens_entrada"] + l["tokens_salida"], latencia_ms=l["latencia_ms"],
                              espera_cupo_s=l["espera_s"]))
        eventos.append(_e(reg["creado"], "registro", f"turno {r['n']}", "versiones del turno", **r.get("versiones", {}),
                          latencia_total_ms=r.get("latencia_ms"), sin_modelo=r.get("sin_modelo") or None))
    con_registro = {reg["turn_id"] for reg in registros}
    for turno, lista in por_turno.items():             # un turno que falló antes de escribir su registro
        if turno in con_registro:
            continue
        for l in lista:
            eventos.append(_e(l["creado"], f"modelo {l['modelo']}", f"turno sin registro · {l['proposito']}", "llamada al modelo",
                              l["resultado"], proveedor=l["proveedor"], llave=l.get("llave"), error=l.get("error"),
                              http_estado=l.get("http_estado"), request_id=l.get("request_id"), turn_id=turno))
    for i in intenciones:
        eventos.append(_e(i["creado"], "herramientas", "acciones", f"intención {i['accion']}",
                          i["estado"] if i["estado"] in ("completada", "propuesta", "confirmada") else i["estado"],
                          action_intent_id=i["action_intent_id"], resultado_releido=i["resultado"]))
    for e in rec_eventos:
        eventos.append(_e(e["creado"], e["autor"] or e["autor_tipo"], f"reclamo {e['numero']}",
                          f"{e['estado_anterior'] or '—'} → {e['estado_nuevo']}", motivo=e["motivo"]))
    for e in blq_eventos:
        eventos.append(_e(e["creado"], e.get("autor") or e["autor_tipo"], "bloqueo", f"{e['estado_anterior']} → {e['estado_nuevo']}",
                          motivo=e["motivo"], action_intent_id=e["action_intent_id"]))
    for e in tr_eventos:
        det = e["detalle"] if isinstance(e["detalle"], dict) else json.loads(e["detalle"] or "{}")
        fallo = e["evento"] in ("alarma_sin_modelo", "alarma_falla_sistema", "aceptacion_vencida") or (e["evento"] == "sugerencia_ia" and not det.get("ok"))
        eventos.append(_e(e["creado"], e["autor"] or "enrutador", f"caso {e['numero']}", e["evento"], "fallo" if fallo else "ok", **det))
    for m in mensajes:
        eventos.append(_e(m["creado"], m["asesor"], "chat", "asesor escribió", origen=m["origen"], texto=m["texto"]))
    for i in incidentes:
        eventos.append(_e(i["creado"], i["donde"], "incidente", i["tipo"], "fallo" if i["severidad"] != "advertencia" else "advertencia",
                          referencia=i["id"], mensaje=i["mensaje"], rastro=(i["rastro"] or "")[-600:] or None))
    for a in accesos:
        eventos.append(_e(a["creado"], a["persona"], "datos personales", f"vio el caso ({a['rol']})", motivo=a["motivo"]))
    # En un turno todo comparte la hora de su transacción: dentro de la misma hora, el orden lógico del turno
    orden = {"escribió": 0, "paso": 1, "decidió": 2, "llamada al modelo": 3, "respondió": 6, "versiones del turno": 7}
    eventos.sort(key=lambda x: (x["hora"], orden.get(x["que"], 5)))
    fallas = [x for x in eventos if x["resultado"] not in ("ok", "no_aplica", "completada", "propuesta", "confirmada", "descartada")]
    return {"encontrada": True, "conversation_id": conversation_id, "cliente": conv["customer_id"] and "verificado",
            "reclamos": [r["numero"] for r in reclamos], "casos_humanos": [t["numero"] for t in traspasos],
            "eventos": eventos, "fallas": fallas}
