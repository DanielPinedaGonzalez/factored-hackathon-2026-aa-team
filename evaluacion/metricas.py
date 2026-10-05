"""Métricas del enunciado (R9), con numerador y denominador publicados e intervalos (02_PLAN §8)."""
from __future__ import annotations

import math

from scipy.stats import beta


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, c - m), 3), round(min(1.0, c + m), 3)]


def cota_superior(k: int, n: int) -> float | None:
    """Clopper-Pearson unilateral 95 %: con 0 casos inseguros se reporta la cota, nunca 'cero riesgo'."""
    if n == 0:
        return None
    return 1.0 if k >= n else round(float(beta.ppf(0.95, k + 1, n - k)), 3)


def _tasa(k: int, n: int) -> dict:
    return {"numerador": k, "denominador": n, "tasa": round(k / n, 3) if n else None, "ic95": wilson(k, n)}


def percentil(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, math.ceil(q * len(xs)) - 1))
    return round(xs[i], 1)


def calcular(resultados: list[dict], precio_usd_millon: tuple[float, float] = (0.15, 0.60)) -> dict:
    """`precio_usd_millon`: precio público de entrada y salida del modelo, solo para el equivalente de referencia."""
    n = len(resultados)
    elegibles = [r for r in resultados if r["automatizable"]]
    inseguros = [r for r in resultados if r["inseguro"]]
    contenidos = [r for r in resultados if not r["escalo"]]
    escalar = [r for r in resultados if r["debia_escalar"]]
    no_escalar = [r for r in resultados if not r["debia_escalar"]]
    latencias = [x for r in resultados for x in r["latencias_ms"]]
    procesamiento = [x for r in resultados for x in r.get("latencias_sin_espera_ms", r["latencias_ms"])]
    tokens_in = sum(r["consumo"]["entrada"] for r in resultados)
    tokens_out = sum(r["consumo"]["salida"] for r in resultados)
    usd = tokens_in / 1e6 * precio_usd_millon[0] + tokens_out / 1e6 * precio_usd_millon[1]
    resueltos = [r for r in resultados if r["resuelto_automatico_seguro"]]
    salida = {
        "casos": n,
        "pasan": _tasa(sum(r["paso"] for r in resultados), n),
        "resolucion_automatica_segura_sobre_elegibles": _tasa(len([r for r in elegibles if r["resuelto_automatico_seguro"]]), len(elegibles)),
        "resolucion_automatica_segura_sobre_intentados": _tasa(len(resueltos), n),
        "contencion_correcta": _tasa(len([r for r in contenidos if not r["debia_escalar"] and r["paso"]]), n),
        "contencion_falsa": _tasa(len([r for r in contenidos if r["debia_escalar"]]), n),
        "escalada_correcta": _tasa(len([r for r in escalar if r["escalo"]]), len(escalar)),
        "escalada_faltante": _tasa(len([r for r in escalar if not r["escalo"]]), len(escalar)),
        "escalada_innecesaria": _tasa(len([r for r in no_escalar if r["escalo"] and not r["sin_modelo"]]), len(no_escalar)),
        "inseguros": {**_tasa(len(inseguros), n), "cota_superior_95": cota_superior(len(inseguros), n),
                      "detalle": {r["caso"]: r["inseguro"] for r in inseguros}},
        "latencia_ms": {"p50": percentil(procesamiento, 0.5), "p95": percentil(procesamiento, 0.95), "turnos": len(latencias),
                        "con_espera_de_cupo": {"p50": percentil(latencias, 0.5), "p95": percentil(latencias, 0.95)}},
        "consumo": {"tokens_entrada": tokens_in, "tokens_salida": tokens_out,
                    "llamadas": sum(r["consumo"]["llamadas"] for r in resultados),
                    "equivalente_usd_referencia": round(usd, 4),
                    "equivalente_usd_por_caso": round(usd / n, 5) if n else None,
                    "equivalente_usd_por_resolucion": round(usd / len(resueltos), 5) if resueltos else "no definido"},
        "fallas": {r["caso"]: r["fallas"] for r in resultados if r["fallas"]},
    }
    for campo, clave in (("idioma", "por_idioma"), ("segmento", "por_segmento")):
        salida[clave] = {}
        for valor in sorted({str(r.get(campo)) for r in resultados}):
            sub = [r for r in resultados if str(r.get(campo)) == valor]
            salida[clave][valor] = {"pasan": _tasa(sum(r["paso"] for r in sub), len(sub)),
                                    "inseguros": _tasa(sum(bool(r["inseguro"]) for r in sub), len(sub))}
    return salida
