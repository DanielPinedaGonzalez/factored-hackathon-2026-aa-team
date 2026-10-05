"""A14 — Enrutador de atención humana (PROCESOS §P2, CONTRATOS A14).

Habilidad, idioma, prioridad y capacidad sobre la plantilla real de `service_agents` (chat: Digital o Hybrid).
Orden de la cola: prioridad → alarma → segmento Premium → llegada. Solo reciben casos los asesores de la demo
conectados; el resto de la plantilla cuenta como presencia y capacidad para que la espera estimada sea realista.
Función determinista: mismo estado → misma asignación. No promete un tiempo que la cola no respalde.
"""
from __future__ import annotations

import functools
import json
import math
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from servicio.datos.db import transaccion
from contratos.idiomas import normalizar

PAIS_ASESOR = {"Mexico": "MX", "México": "MX", "Colombia": "CO", "Argentina": "AR"}


@functools.lru_cache(maxsize=1)
def config() -> dict:
    return yaml.safe_load((Path(__file__).resolve().parents[2] / "config" / "atencion_humana.yaml").read_text())


def _en_turno(turno: str, pais: str | None, ahora: datetime, margen_min: int = 0) -> bool:
    ini, fin = config()["turnos"].get(turno, [6, 14])
    tz = ZoneInfo(config()["zona_horaria"].get(PAIS_ASESOR.get(pais or "", "CO"), "America/Bogota"))
    local = ahora.astimezone(tz)
    h = local.hour + local.minute / 60 + margen_min / 60
    return (ini <= h < fin) if ini < fin else (h >= ini or h < fin)


def _proximo_turno(asesores: list[dict], ahora: datetime) -> datetime | None:
    for minutos in range(0, 24 * 60, 15):
        t = ahora + timedelta(minutes=minutos)
        if any(_en_turno(a["turno"], a["pais"], t) for a in asesores):
            return t
    return None


def habilidades_por_nivel(habilidad: str, nivel: int) -> set[str]:
    if nivel == 0:
        return {habilidad}
    if nivel == 1:
        return {habilidad, *config()["afines"].get(habilidad, [])}
    return {"fraude", "reclamos", "general"}


def en_turno(a: dict, ahora: datetime, antes_del_fin: bool = False) -> bool:
    """Una sola regla de turno para todo el enrutador: las identidades de demo, si la configuración lo declara, están
    siempre en turno; el resto, según las horas de su turno. `antes_del_fin`: quedan más de `fin_de_turno_minutos`."""
    if config().get("asesores_demo_siempre_en_turno", False) and a.get("demo"):
        return True
    return _en_turno(a["turno"], a["pais"], ahora) and (
        not antes_del_fin or _en_turno(a["turno"], a["pais"], ahora, config()["fin_de_turno_minutos"]))


def elegibles(asesores: list[dict], habilidad: str, idioma: str, nivel: int, ahora: datetime,
              solo_demo: bool) -> list[dict]:
    cualquiera = config().get("asesores_demo_cualquier_habilidad", False)       # demo declarada: sus identidades reciben casos de cualquier habilidad
    return [a for a in asesores
            if (a["habilidad"] in habilidades_por_nivel(habilidad, nivel) or (cualquiera and a.get("demo"))) and idioma in a["idiomas"]
            and a["canal"] in ("Digital", "Hybrid") and en_turno(a, ahora, antes_del_fin=True)
            and (not solo_demo or (a["demo"] and a["presencia"] == "disponible" and a["carga"] < a["capacidad"]))]


def _asesores(c) -> list[dict]:
    return c.execute("""select a.employee_code, a.habilidad, a.idiomas, a.canal, a.turno, a.pais, a.demo,
                               coalesce(p.presencia, case when a.demo then 'desconectado' else 'disponible' end) as presencia,
                               coalesce(p.capacidad, 2) as capacidad, coalesce(k.carga, 0) as carga, k.ultima_asignacion
                        from atencion.asesores a
                        left join lateral (select presencia, capacidad from atencion.asesor_presencia_eventos e
                                           where e.employee_code = a.employee_code order by id desc limit 1) p on true
                        left join atencion.asesor_carga k using (employee_code)""").fetchall()


def nivel_desborde(habilidad: str, idioma: str, prioridad: int, llegada: datetime, ahora: datetime,
                   asesores: list[dict]) -> int:
    hito = config()["hitos_minutos"][prioridad] * 60
    fraccion = (ahora - llegada).total_seconds() / hito
    if not any(idioma in a["idiomas"] and en_turno(a, ahora) for a in asesores):
        return 3
    n = 0
    for nv, f in sorted(config()["desborde_fraccion"].items()):
        if fraccion >= f:
            n = nv
    return n


def crear_traspaso(c, paquete: dict, conversation_id: str, customer_id: str | None, segmento: str | None) -> dict:
    """Con la conexión del cliente (RLS). Un solo traspaso activo por conversación: si ya existe, lo devuelve."""
    activo = c.execute("""select * from atencion.traspasos where conversation_id = %s
                          and estado in ('en_cola','asignado','en_atencion','esperando_cliente')""", (conversation_id,)).fetchone()
    if activo:
        return {**activo, "ya_activo": True}
    ahora = datetime.now(timezone.utc)
    prioridad = paquete["prioridad"]
    numero = "T-" + str(c.execute("select nextval('atencion.traspaso_numero') n").fetchone()["n"]).zfill(6)
    tid = "tr_" + secrets.token_hex(8)
    c.execute("""insert into atencion.traspasos (traspaso_id, numero, conversation_id, customer_id, paquete, habilidad, idioma,
                   prioridad, segmento, primera_respuesta_vence, seguimiento_vence, version_config)
                 values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
              (tid, numero, conversation_id, customer_id, json.dumps(paquete, default=str), paquete["habilidad_requerida"],
               normalizar(paquete["idioma"]), prioridad, segmento,
               ahora + timedelta(minutes=config()["hitos_minutos"][prioridad]),
               ahora + timedelta(minutes=config()["seguimiento_minutos"]), config()["version"]))
    c.execute("insert into atencion.traspaso_eventos (traspaso_id, evento, detalle) values (%s,'creado',%s)",
              (tid, json.dumps({"prioridad": prioridad, "habilidad": paquete["habilidad_requerida"]})))
    c.execute("update atencion.conversaciones set estado = 'con_humano' where conversation_id = %s", (conversation_id,))
    fila = c.execute("select * from atencion.traspasos where traspaso_id = %s", (tid,)).fetchone()
    estimada = posicion_y_espera_con(c, fila, ahora).get("espera_minutos")
    if estimada:                         # la primera estimación: contra ella se mide si la espera se excedió (§P2.6)
        c.execute("update atencion.traspasos set espera_estimada_min = %s where traspaso_id = %s", (estimada, tid))
        fila = {**fila, "espera_estimada_min": estimada}
    return fila


def espera_excedida(t: dict, ahora: datetime) -> bool:
    """PROCESOS §P2.6: la espera real ya supera la primera estimación por la fracción declarada."""
    estimada = t.get("espera_estimada_min")
    return bool(estimada) and t["estado"] == "en_cola" and \
        (ahora - t["llegada"]).total_seconds() > config()["espera_excedida_fraccion"] * estimada * 60


def _orden(t: dict, ahora: datetime) -> tuple:
    hito = config()["hitos_minutos"][t["prioridad"]] * 60
    en_alarma = (ahora - t["llegada"]).total_seconds() >= config()["alarma_fraccion"] * hito
    return (t["prioridad"], 0 if en_alarma else 1, 0 if t["segmento"] == "Premium" else 1, t["llegada"], t["numero"])


def cola(ahora: datetime | None = None) -> list[dict]:
    ahora = ahora or datetime.now(timezone.utc)
    with transaccion("app_enrutador") as c:
        filas = c.execute("select * from atencion.traspasos where estado = 'en_cola'").fetchall()
    return sorted(filas, key=lambda t: _orden(t, ahora))


def posicion_y_espera_con(c, t: dict, ahora: datetime | None = None) -> dict:
    """Posición entre los casos de su misma habilidad e idioma y espera ≈ TMA × posición ÷ capacidad elegible total.
    Funciona con la conexión del cliente: la fila de la cola llega sin datos de otros clientes (atencion.fila_cola)."""
    ahora = ahora or datetime.now(timezone.utc)
    if t["estado"] != "en_cola":
        return {"estado": t["estado"], "asesor_asignado": bool(t["asesor"])}
    asesores = _asesores(c)
    mismos = c.execute("select * from atencion.fila_cola(%s, %s)", (t["habilidad"], t["idioma"])).fetchall()
    orden = sorted(mismos, key=lambda x: _orden(x, ahora))
    posicion = next((i + 1 for i, x in enumerate(orden) if x["traspaso_id"] == t["traspaso_id"]), 1)
    nivel = nivel_desborde(t["habilidad"], t["idioma"], t["prioridad"], t["llegada"], ahora, asesores)
    conectados = [a for a in elegibles(asesores, t["habilidad"], t["idioma"], min(nivel, 2), ahora, False)
                  if a["presencia"] != "en_pausa"]
    capacidad = sum(a["capacidad"] for a in conectados)
    if capacidad == 0:
        prox = _proximo_turno([a for a in asesores if t["idioma"] in a["idiomas"]], ahora)
        # Nivel 3 (§P2.5): nadie en turno con el idioma del caso. Se le ofrece seguir en español si hay alguien en
        # turno que lo hable; decide el cliente, nunca el sistema.
        ofrece = nivel == 3 and t["idioma"] != "es" and any("es" in a["idiomas"] and en_turno(a, ahora) for a in asesores)
        return {"estado": "en_cola", "posicion": posicion, "espera_minutos": None,
                "abre": prox.isoformat() if prox else None, "nivel_desborde": nivel,
                **({"ofrece_idioma": "es"} if ofrece else {}),
                **({"espera_excedida": True, "espera_estimada_inicial": t["espera_estimada_min"]} if espera_excedida(t, ahora) else {})}
    tma = config()["tma_segundos"][t["habilidad"]]
    return {"estado": "en_cola", "posicion": posicion,
            "espera_minutos": max(1, math.ceil(tma * posicion / capacidad / 60)), "nivel_desborde": nivel,
            **({"espera_excedida": True, "espera_estimada_inicial": t["espera_estimada_min"]} if espera_excedida(t, ahora) else {})}


def posicion_y_espera(traspaso_id: str, ahora: datetime | None = None) -> dict:
    with transaccion("app_enrutador") as c:
        t = c.execute("select * from atencion.traspasos where traspaso_id = %s", (traspaso_id,)).fetchone()
        return {"numero": t["numero"], **posicion_y_espera_con(c, t, ahora)}


def cambiar_idioma_a_pedido(traspaso_id: str, idioma: str) -> bool:
    """§P2.5 nivel 3: el cliente aceptó seguir en otro idioma. El caso vuelve al nivel 0 en ese idioma y conserva su
    llegada y su prioridad; queda el evento. Solo desde la cola y nunca por iniciativa del sistema."""
    with transaccion("app_enrutador") as c:
        t = c.execute("select idioma from atencion.traspasos where traspaso_id = %s and estado = 'en_cola'", (traspaso_id,)).fetchone()
        if t is None or t["idioma"] == idioma:
            return False
        c.execute("""update atencion.traspasos set idioma = %s, nivel_desborde = 0, version = version + 1
                     where traspaso_id = %s and estado = 'en_cola'""", (idioma, traspaso_id))
        c.execute("insert into atencion.traspaso_eventos (traspaso_id, evento, autor, detalle) values (%s,'idioma_aceptado_por_cliente','cliente',%s)",
                  (traspaso_id, json.dumps({"de": t["idioma"], "a": idioma})))
    return True


def envejecer(c, ahora: datetime) -> list[str]:
    """PROCESOS §P2.3: un caso de prioridad 4 con el hito vencido sube a 3, con un hito nuevo desde la subida. No sube
    más: la 2 es una condición del cliente y la 1 solo la da una señal de seguridad."""
    filas = c.execute("""update atencion.traspasos set prioridad = 3, primera_respuesta_vence = %s, version = version + 1
                         where estado = 'en_cola' and prioridad = 4 and primera_respuesta_vence < %s
                         returning traspaso_id""",
                      (ahora + timedelta(minutes=config()["hitos_minutos"][3]), ahora)).fetchall()
    for f in filas:
        c.execute("insert into atencion.traspaso_eventos (traspaso_id, evento, detalle) values (%s,'envejecido',%s)",
                  (f["traspaso_id"], json.dumps({"de": 4, "a": 3})))
    return [f["traspaso_id"] for f in filas]


def vencidas_aceptacion(c, ahora: datetime) -> list[str]:
    """PROCESOS §P2.4: el asesor tiene `aceptacion_segundos` para abrir el caso. Si no, el caso vuelve a la cola en su
    mismo lugar (conserva la llegada), el asesor pasa a `ausente` y el supervisor ve el evento."""
    limite = ahora - timedelta(seconds=config()["aceptacion_segundos"])
    filas = c.execute("""update atencion.traspasos t set estado = 'en_cola', asesor = null, asignado_en = null,
                                version = version + 1
                         from (select traspaso_id, asesor from atencion.traspasos
                               where estado = 'asignado' and asignado_en < %s for update) v
                         where t.traspaso_id = v.traspaso_id returning t.traspaso_id, v.asesor""", (limite,)).fetchall()
    for f in filas:
        c.execute("update atencion.asesor_carga set carga = greatest(carga - 1, 0) where employee_code = %s", (f["asesor"],))
        c.execute("insert into atencion.asesor_presencia_eventos (employee_code, presencia, capacidad) values (%s,'ausente',2)",
                  (f["asesor"],))
        c.execute("insert into atencion.traspaso_eventos (traspaso_id, evento, autor) values (%s,'aceptacion_vencida',%s)",
                  (f["traspaso_id"], f["asesor"]))
    return [f["traspaso_id"] for f in filas]


def asignar(ahora: datetime | None = None) -> list[dict]:
    """Recorre la cola en orden y asigna a asesores de la demo elegibles, con escritura condicional de la carga."""
    ahora = ahora or datetime.now(timezone.utc)
    asignados = []
    with transaccion("app_enrutador") as c:
        from servicio.registro import parametros
        c.execute("select atencion.cerrar_reclamos_sin_respuesta(%s)", (parametros.leer(c, "dias_espera_respuesta_cliente"),))
        asesores = _asesores(c)
        envejecer(c, ahora)
        if vencidas_aceptacion(c, ahora):
            asesores = _asesores(c)
        pendientes = sorted(c.execute("select * from atencion.traspasos where estado = 'en_cola'").fetchall(),
                            key=lambda t: _orden(t, ahora))
        for t in pendientes:
            if espera_excedida(t, ahora):     # una sola vez por caso: el supervisor lo ve en la auditoría y en la cola
                c.execute("""insert into atencion.traspaso_eventos (traspaso_id, evento, detalle)
                             select %s, 'espera_excedida', %s where not exists (select 1 from atencion.traspaso_eventos
                                   where traspaso_id = %s and evento = 'espera_excedida')""",
                          (t["traspaso_id"], json.dumps({"estimada_min": t["espera_estimada_min"]}), t["traspaso_id"]))
            nivel = nivel_desborde(t["habilidad"], t["idioma"], t["prioridad"], t["llegada"], ahora, asesores)
            if nivel != t["nivel_desborde"]:
                c.execute("update atencion.traspasos set nivel_desborde = %s where traspaso_id = %s", (nivel, t["traspaso_id"]))
                c.execute("insert into atencion.traspaso_eventos (traspaso_id, evento, detalle) values (%s,'desborde',%s)",
                          (t["traspaso_id"], json.dumps({"nivel": nivel})))
            candidatos = elegibles(asesores, t["habilidad"], t["idioma"], min(nivel, 2), ahora, True)
            candidatos.sort(key=lambda a: (a["carga"] / a["capacidad"], a["ultima_asignacion"] or datetime.min.replace(tzinfo=timezone.utc),
                                           a["employee_code"]))
            for a in candidatos:
                n = c.execute("""update atencion.asesor_carga set carga = carga + 1, ultima_asignacion = now()
                                 where employee_code = %s and carga = %s""", (a["employee_code"], a["carga"])).rowcount
                if n == 0:
                    continue
                c.execute("""update atencion.traspasos set estado = 'asignado', asesor = %s, asignado_en = now(), version = version + 1
                             where traspaso_id = %s and estado = 'en_cola'""", (a["employee_code"], t["traspaso_id"]))
                c.execute("insert into atencion.traspaso_eventos (traspaso_id, evento, autor, detalle) values (%s,'asignado',%s,%s)",
                          (t["traspaso_id"], a["employee_code"], json.dumps({"nivel": nivel})))
                a["carga"] += 1
                asignados.append({"traspaso_id": t["traspaso_id"], "asesor": a["employee_code"]})
                break
    return asignados
