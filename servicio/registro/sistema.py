"""A13 — Estado del sistema (la cabina): salud, pool de llaves, consumo, fallos y lo que necesita atención.

Como la cabina del sistema propio del autor, compone y no recalcula: la salud sale de la base y de los artefactos,
el pool de su estado vivo, el consumo de `operacion.consumo_modelos`, los fallos de los pasos del registro de turnos
y la operación de `indicadores.calcular`. Los avisos llegan solos a "necesita atención", con su severidad.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from servicio.datos.db import transaccion
from servicio.registro import indicadores
from servicio.registro.indicadores import MODELO_DE_PRUEBAS      # lo que hacen las pruebas automáticas no es operación

PRECIO_LISTA_USD_MILLON = {"openai/gpt-oss-120b": (0.15, 0.60), "openai/gpt-oss-20b": (0.075, 0.30),
                           "llama-3.3-70b-versatile": (0.59, 0.79), "qwen/qwen3.8-27b": (0.29, 0.59)}
UMBRAL_PETICIONES_DIA = 0.10          # aviso cuando a una llave le queda menos del 10 % de sus peticiones del día


def _aviso(severidad: str, origen: str, texto: str, **detalle) -> dict:
    return {"severidad": severidad, "origen": origen, "texto": texto, "detalle": detalle}


def _salud(c) -> dict:
    from servicio.conocimiento import conocimiento
    from servicio.politica import motor
    from servicio.riesgo import senal
    version = int(c.execute("show server_version_num").fetchone()["server_version_num"])
    datos = c.execute("select data_as_of, hash_manifest from servicio.datos_version").fetchone()
    articulos = conocimiento.articulos_en_disco()
    estados = {}
    for a in articulos:
        estados[a["cabecera"]["estado"]] = estados.get(a["cabecera"]["estado"], 0) + 1
    return {"postgres": version, "postgres_ok": version >= 160015, "datos_hasta": str(datos["data_as_of"]) if datos else None,
            "politica": motor.version_politica(), "m1": (senal.artefacto() or {}).get("version"),
            "modelo_modo": os.environ.get("MODELO_MODO", "puente"), "articulos": estados,
            "articulos_servidos_en_borrador": os.environ.get("CONOCIMIENTO_INCLUIR_PENDIENTES") == "1"}


def _consumo(c, desde: datetime) -> list[dict]:
    filas = c.execute("""select modelo, proposito, llave, count(*) llamadas, sum(tokens_entrada) entrada, sum(tokens_salida) salida,
                                avg(latencia_ms) latencia_media_ms, avg(espera_s) espera_media_s
                         from operacion.consumo_modelos where creado >= %s and origen = 'operacion' and modelo <> %s
                         group by 1, 2, 3 order by 4 desc""", (desde, MODELO_DE_PRUEBAS)).fetchall()
    for f in filas:
        pe, ps = PRECIO_LISTA_USD_MILLON.get(f["modelo"], (0.0, 0.0))
        f["equivalente_usd"] = round((f["entrada"] or 0) / 1e6 * pe + (f["salida"] or 0) / 1e6 * ps, 5)
        f["latencia_media_ms"] = round(float(f["latencia_media_ms"] or 0), 1)
        f["espera_media_s"] = round(float(f["espera_media_s"] or 0), 2)
    return filas


def _fallos(c, desde: datetime) -> list[dict]:
    """Pasos que fallaron (modelo sin cupo, verificación, herramienta), por componente y motivo."""
    return c.execute("""select p->>'componente' componente, coalesce(p->'detalle'->>'motivo', p->'detalle'->>'error', '') motivo,
                               count(*) veces, max(r.creado) ultima
                        from operacion.registro_turnos r, jsonb_array_elements(r.registro->'pasos') p
                        where r.creado >= %s and p->>'estado' = 'fallo' and r.origen = 'operacion' and r.conversation_id not like %s
                          and r.conversation_id not in (select conversation_id from operacion.registro_turnos
                                                        where registro->'versiones'->>'modelo' like %s)
                        group by 1, 2 order by 3 desc limit 20""",
                     (desde, indicadores.PREFIJO_EVALUACION + "%", f"%{MODELO_DE_PRUEBAS}%")).fetchall()


def _razones(c, desde: datetime) -> dict:
    """Las razones reales: llamadas al modelo que fallaron (con el mensaje del proveedor), incidentes y rechazos."""
    llamadas = c.execute("""select modelo, proposito, llave, coalesce(http_estado::text, 'local') estado, left(error, 240) error,
                                   count(*) veces, max(creado) ultima
                            from operacion.consumo_modelos where creado >= %s and resultado = 'fallo' and origen = 'operacion'
                              and modelo not in (%s, 'evaluacion')
                            group by 1, 2, 3, 4, 5 order by 6 desc limit 15""", (desde, MODELO_DE_PRUEBAS)).fetchall()
    incidentes = c.execute("""select id, creado, donde, tipo, severidad, left(mensaje, 300) mensaje, conversation_id
                              from operacion.incidentes where creado >= %s and origen = 'operacion' order by id desc limit 15""",
                                (desde,)).fetchall()
    rechazos = c.execute("""select tipo, count(*) veces, max(creado) ultima from operacion.eventos_seguridad
                            where creado >= %s and origen = 'operacion' group by 1 order by 2 desc""", (desde,)).fetchall()
    return {"llamadas_fallidas": llamadas, "incidentes": incidentes, "rechazos": rechazos}


def _deriva_m1() -> dict | None:
    """La última medición de deriva del fraud_score (ml/deriva.py), si existe."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "artefactos" / "deriva_m1.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cabina(rol: str, horas: int = 24, ahora: datetime | None = None) -> dict:
    from servicio.llm.pool import pool_del_sistema
    ahora = ahora or datetime.now(timezone.utc)
    desde = ahora - timedelta(hours=horas)
    with transaccion(rol) as c:
        salud = _salud(c)
        consumo = _consumo(c, desde)
        fallos = _fallos(c, desde)
        razones = _razones(c, desde)
        from servicio.registro import parametros as par
        params = par.listar(c)
        al_tope = c.execute("""select count(distinct conversation_id) n from operacion.registro_turnos
                               where creado >= %s and origen = 'operacion'
                                 and registro->'pasos' @> '[{"componente": "presupuesto"}]'""", (desde,)).fetchone()["n"]
        for p in params:
            if p["clave"] == "presupuesto_tokens_conversacion":
                p["conversaciones_al_tope"] = al_tope
        por_llave = {(f["proveedor"], f["llave"]): f for f in c.execute(
            """select proveedor, llave, sum(tokens_entrada + tokens_salida) tokens, count(*) llamadas,
                      count(*) filter (where resultado = 'fallo') fallos
               from operacion.consumo_modelos where creado >= %s and llave is not null group by 1, 2""",
            (ahora - timedelta(hours=24),)).fetchall()}
    operacion = indicadores.leer(rol, horas)
    pool = pool_del_sistema()
    modelo = pool.estado() if pool else {"estado": "SIN_POOL", "proveedor": salud["modelo_modo"], "llaves": []}

    import yaml
    from pathlib import Path
    limite_dia = yaml.safe_load((Path(__file__).resolve().parents[2] / "config" / "llaves.yaml").read_text())["limite_tokens_dia"]
    for k in modelo.get("llaves", []):          # el gasto diario de cada llave, medido de nuestro registro (todo origen)
        f = por_llave.get((k.get("proveedor") or modelo["proveedor"], k["indice"]), {})
        k["tokens_24h"], k["limite_tokens_dia"] = int(f.get("tokens") or 0), limite_dia
        k["llamadas_24h"], k["fallos_24h"] = int(f.get("llamadas") or 0), int(f.get("fallos") or 0)
    avisos: list[dict] = []
    if modelo["estado"] == "SIN_LLAVES":
        avisos.append(_aviso("critica", "ia", "La API arrancó sin llaves del modelo: toda conversación pasa a una persona. "
                             "Se arranca con make api, que carga el archivo de llaves.", razon=modelo.get("razon")))
    elif modelo["estado"] == "SATURADO":
        avisos.append(_aviso("critica", "ia", "Todas las llaves están en enfriamiento: las conversaciones nuevas pasan a una persona."))
    elif modelo["estado"] == "DEGRADADO":
        avisos.append(_aviso("advertencia", "ia", "Alguna llave está en enfriamiento; el pool atiende con las demás.",
                             llaves=[k["llave"] for k in modelo["llaves"] if not k["disponible"]]))
    for k in modelo.get("llaves", []):
        if k["tokens_24h"] >= 0.8 * k["limite_tokens_dia"]:
            avisos.append(_aviso("critica" if k["tokens_24h"] >= 0.98 * k["limite_tokens_dia"] else "advertencia", "ia",
                                 f"La llave {k['llave']} gastó {k['tokens_24h']:,} de {k['limite_tokens_dia']:,} tokens del día."))
        if k.get("enfriada_s", 0) > 300:          # el proveedor pidió esperar minutos: un límite largo (p. ej. el diario)
            avisos.append(_aviso("critica", "ia", f"La llave {k['llave']} está fuera por {k['enfriada_s'] // 60} min según el proveedor.",
                                 razon=k.get("ultimo_error")))
        restantes = k.get("peticiones_restantes_dia")
        if restantes is not None and restantes < 1000 * UMBRAL_PETICIONES_DIA:
            avisos.append(_aviso("advertencia", "ia", f"A la llave {k['llave']} le quedan {restantes} peticiones del día."))
    alarma = operacion["operacion"]["alarma_sin_modelo"]
    if alarma["activa"]:
        avisos.append(_aviso("critica", "operacion", f"{alarma['turnos']} turnos sin modelo en {alarma['ventana_minutos']} min."))
    vencidos = sum(f["vencidos"] for f in operacion["colas"])
    if vencidos:
        avisos.append(_aviso("critica", "operacion", f"{vencidos} casos con la primera respuesta vencida en la fila."))
    if not salud["postgres_ok"]:
        avisos.append(_aviso("critica", "base", f"PostgreSQL {salud['postgres']} por debajo de 16.15."))
    pendientes = salud["articulos"].get("pendiente_aprobacion", 0)
    if pendientes:
        avisos.append(_aviso("informativa", "conocimiento", f"{pendientes} artículos esperan aprobación"
                             + (" y se sirven en borrador." if salud["articulos_servidos_en_borrador"] else ".")))
    if sum(f["veces"] for f in fallos):
        avisos.append(_aviso("advertencia", "registro", f"{sum(f['veces'] for f in fallos)} pasos fallidos en {horas} h.",
                             principal=f"{fallos[0]['componente']}: {fallos[0]['motivo']}"))
    criticos = [i for i in razones["incidentes"] if i["severidad"] == "critica"]
    if criticos:
        avisos.append(_aviso("critica", "incidentes", f"{len(criticos)} incidentes críticos (el último: {criticos[0]['donde']}: "
                             f"{criticos[0]['tipo']})", referencia=criticos[0]["id"]))
    deriva = _deriva_m1()
    if deriva and deriva["alerta"]:
        avisos.append(_aviso("critica", "m1", "El fraud_score cambió de distribución (PSI > 0,2): hay que volver a certificar el umbral.",
                             meses=[x["mes"] for x in deriva["por_mes"] if x["alerta"]]))
    orden = {"critica": 0, "advertencia": 1, "informativa": 2}
    avisos.sort(key=lambda a: orden[a["severidad"]])
    sano = not any(a["severidad"] == "critica" for a in avisos)
    return {"sano": sano, "generado": ahora.isoformat(), "horas": horas, "salud": salud, "modelo": modelo,
            "consumo": consumo, "consumo_total_usd": round(sum(f["equivalente_usd"] for f in consumo), 5),
            "fallos": fallos, **razones, "operacion": operacion["operacion"], "colas": operacion["colas"], "avisos": avisos,
            "parametros": params, "deriva_m1": deriva and {"psi_max": max((x["psi"] for x in deriva["por_mes"]), default=None),
                                                          "meses": len(deriva["por_mes"]), "alerta": deriva["alerta"],
                                                          "medido": deriva["creado"]}}
