"""A13 — Indicadores de operación en vivo (PROCESOS §P8, INTERFACES §3.2).

Se calculan de lo que ya quedó en la base: el `RegistroTurno` de cada turno (sin PII), la cola enmascarada y los
eventos de traspaso. Son las mismas definiciones del reporte de evaluación (`evaluacion/metricas.py`), aplicadas a las
conversaciones reales de la demo: ningún número se escribe a mano ni sale del texto del modelo.
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta, timezone

from servicio.datos.db import transaccion
from servicio.enrutador import enrutador

PRECIO_USD_MILLON = (0.15, 0.60)          # precio público de referencia (el mismo del reporte); con llaves gratuitas no hay cobro
VENTANA_ALARMA_MIN = 15                   # una conversación sin modelo en este lapso enciende la alarma roja (§P8)
MODELO_DE_PRUEBAS = "falso"                # las pruebas automáticas escriben en la base local
PREFIJO_EVALUACION = "eval_"              # las conversaciones de la evaluación no son operación


def _percentil(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, max(0, math.ceil(q * len(xs)) - 1))], 1)


def _tasa(k: int, n: int) -> dict:
    return {"numerador": k, "denominador": n, "tasa": round(k / n, 3) if n else None}


def calcular(registros: list[dict], ahora: datetime) -> dict:
    """Función pura sobre los registros de turno ({conversation_id, creado, registro})."""
    por_conv: dict[str, list[dict]] = {}
    for r in registros:
        por_conv.setdefault(r["conversation_id"], []).append(r)
    n_conv = len(por_conv)
    escaladas, resueltas, sin_modelo_conv = set(), set(), set()
    habilidades: Counter = Counter()
    acciones: Counter = Counter()
    senales: Counter = Counter()
    for cid, turnos in por_conv.items():
        pasos = [p for t in turnos for p in t["registro"].get("pasos", [])]
        traspasos = [p for p in pasos if p.get("componente") == "traspaso" and p.get("estado") == "ok"]
        if traspasos:
            escaladas.add(cid)
            habilidades[traspasos[0]["detalle"].get("habilidad")] += 1
        hechas = [a["accion"] for t in turnos for a in t["registro"].get("acciones", [])]
        acciones.update(hechas)
        if hechas and not traspasos:
            resueltas.add(cid)
        if any(t["registro"].get("sin_modelo") for t in turnos):
            sin_modelo_conv.add(cid)
        senales.update(set(turnos[-1]["registro"].get("senales") or []))
    procesamiento = [t["registro"]["latencia_ms"] - t["registro"].get("espera_cupo_ms", 0) for t in registros
                     if t["registro"].get("latencia_ms") is not None]
    tokens_in = sum(t["registro"].get("tokens", {}).get("entrada", 0) for t in registros)
    tokens_out = sum(t["registro"].get("tokens", {}).get("salida", 0) for t in registros)
    usd = tokens_in / 1e6 * PRECIO_USD_MILLON[0] + tokens_out / 1e6 * PRECIO_USD_MILLON[1]
    recientes = [t for t in registros if t["registro"].get("sin_modelo")
                 and t["creado"] >= ahora - timedelta(minutes=VENTANA_ALARMA_MIN)]
    return {
        "conversaciones": n_conv,
        "turnos": len(registros),
        "resueltas_por_el_asistente": _tasa(len(resueltas), n_conv),
        "pasaron_a_una_persona": _tasa(len(escaladas), n_conv),
        "sin_modelo": _tasa(len(sin_modelo_conv), n_conv),
        "traspasos_por_habilidad": dict(habilidades),
        "acciones_verificadas": dict(acciones),
        "senales_de_riesgo": dict(senales.most_common()),
        "latencia_ms": {"p50": _percentil(procesamiento, 0.5), "p95": _percentil(procesamiento, 0.95)},
        "tokens": {"entrada": tokens_in, "salida": tokens_out},
        "equivalente_usd_por_conversacion": round(usd / n_conv, 5) if n_conv else None,
        "equivalente_usd_por_resolucion": round(usd / len(resueltas), 5) if resueltas else "no definido",
        "alarma_sin_modelo": {"activa": bool(recientes), "turnos": len(recientes), "ventana_minutos": VENTANA_ALARMA_MIN},
    }


def leer(rol: str, horas: int = 24, incluir_evaluacion: bool = False, ahora: datetime | None = None,
         incluir_pruebas: bool = False) -> dict:
    """`rol`: app_supervisor o app_observador (la RLS de registro_turnos y la cola enmascarada los permiten).
    Las conversaciones de las pruebas automáticas (modelo de pruebas) y de la evaluación no son operación."""
    ahora = ahora or datetime.now(timezone.utc)
    desde = ahora - timedelta(hours=horas)
    with transaccion(rol) as c:
        registros = c.execute("""select conversation_id, creado, registro from operacion.registro_turnos
                                 where creado >= %s and (%s or conversation_id not like %s)
                                   and (%s or (origen = 'operacion'
                                                and conversation_id not in (select conversation_id from operacion.registro_turnos
                                                                            where registro->'versiones'->>'modelo' like %s)))
                                 order by creado""",
                              (desde, incluir_evaluacion, PREFIJO_EVALUACION + "%", incluir_pruebas, f"%{MODELO_DE_PRUEBAS}%")).fetchall()
        colas = c.execute("""select habilidad, idioma, count(*) filter (where estado = 'en_cola') as en_cola,
                                    count(*) filter (where estado <> 'en_cola') as con_asesor,
                                    count(*) filter (where primera_respuesta_vence < now()) as vencidos,
                                    min(llegada) filter (where estado = 'en_cola') as mas_antiguo
                             from atencion.cola_enmascarada group by 1, 2 order by 1, 2""").fetchall()
        eventos = []
        if rol == "app_supervisor":
            eventos = c.execute("""select e.creado, t.numero, e.evento, e.autor, e.detalle from atencion.traspaso_eventos e
                                   join atencion.traspasos t using (traspaso_id) order by e.id desc limit 12""").fetchall()
            asesores = enrutador._asesores(c)
            for fila in colas:             # capacidad conectada y espera con la misma fórmula que ve el cliente (A14)
                conectados = [a for a in enrutador.elegibles(asesores, fila["habilidad"], fila["idioma"], 0, ahora, False)
                              if a["presencia"] != "en_pausa"]
                capacidad = sum(a["capacidad"] for a in conectados)
                fila["asesores_conectados"] = len(conectados)
                fila["espera_minutos"] = (max(1, math.ceil(enrutador.config()["tma_segundos"][fila["habilidad"]]
                                                           * fila["en_cola"] / capacidad / 60))
                                          if capacidad and fila["en_cola"] else (0 if capacidad else None))
    return {"desde": desde.isoformat(), "horas": horas, "operacion": calcular(registros, ahora),
            "colas": colas, "eventos": eventos}
