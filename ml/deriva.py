"""Vigilancia de la deriva de M1 (GOBERNANZA §8): ¿el `fraud_score` que llega sigue repartido como en la ventana con que
se calibró? Se mide mes a mes con el índice de estabilidad de la población (PSI) sobre tramos fijos del score, más el
porcentaje de movimientos sin score. Un PSI mayor que 0,2 es un cambio que invalida la calibración: la cabina lo avisa
y el procedimiento de M1 se vuelve a correr antes de confiar en el umbral.

Uso: python -m ml.deriva  →  artefactos/deriva_m1.json
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[1]
PLATA = RAIZ.parent / "scratch" / "plata" / "transacciones"
SALIDA = RAIZ / "artefactos" / "deriva_m1.json"
TRAMOS = [10 * i for i in range(10)] + [100.01]                  # tramos fijos de 10 puntos; el umbral no se escribe aquí
VENTANA_REFERENCIA = ("2023-06-01", "2025-07-01")                 # la de aprendizaje de M1
UMBRAL_ALERTA = 0.2


def psi(referencia: list[float], actual: list[float]) -> float:
    total = 0.0
    for r, a in zip(referencia, actual):
        r, a = max(r, 1e-6), max(a, 1e-6)
        total += (a - r) * math.log(a / r)
    return total


def _distribucion(c, donde: str) -> tuple[list[float], float, int]:
    casos = " ".join(f"when fraud_score < {TRAMOS[i + 1]} then {i}" for i in range(len(TRAMOS) - 1))
    filas = dict(c.execute(f"""select case when fraud_score is null then -1 else (case {casos} end) end t, count(*)
                                from read_parquet('{PLATA}/*/*.parquet') where {donde} group by 1""").fetchall())
    n = sum(filas.values())
    con = n - filas.get(-1, 0)
    return [filas.get(i, 0) / con if con else 0.0 for i in range(len(TRAMOS) - 1)], filas.get(-1, 0) / n if n else 0.0, n


def medir() -> dict:
    c = duckdb.connect(config={"threads": 2, "memory_limit": "1GB"})
    a, b = VENTANA_REFERENCIA
    ref, ref_sin, n_ref = _distribucion(c, f"fecha >= '{a}' and fecha < '{b}'")
    meses = [m for (m,) in c.execute(f"select distinct strftime(fecha, '%Y-%m') from read_parquet('{PLATA}/*/*.parquet') "
                                     f"where fecha >= '{b}' order by 1").fetchall()]
    por_mes = []
    for m in meses:
        dist, sin, n = _distribucion(c, f"strftime(fecha, '%Y-%m') = '{m}'")
        valor = psi(ref, dist)
        por_mes.append({"mes": m, "movimientos": n, "psi": round(valor, 4), "sin_score": round(sin, 4),
                        "alerta": valor > UMBRAL_ALERTA})
    return {"componente": "deriva_m1", "creado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "referencia": {"ventana": list(VENTANA_REFERENCIA), "movimientos": n_ref, "sin_score": round(ref_sin, 4)},
            "tramos": TRAMOS[:-1], "umbral_alerta": UMBRAL_ALERTA, "por_mes": por_mes,
            "alerta": any(x["alerta"] for x in por_mes)}


if __name__ == "__main__":
    r = medir()
    SALIDA.write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: r[k] for k in ("alerta",)} | {"psi_max": max(x["psi"] for x in r["por_mes"])}, ensure_ascii=False))
