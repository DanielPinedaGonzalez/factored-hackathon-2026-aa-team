"""M1 — señal de riesgo calibrada con control estadístico del riesgo (02_PLAN §4).

Procedimiento escrito antes de mirar la ventana LTT:
  1. Deduplicar por transaction_id y separar por fecha: aprender 2023-06..2025-06, LTT 2025-07..2025-12,
     test bloqueado 2026-01..2026-06 (no se mira hasta el reporte final).
  2. Calibrar en "aprender": regresión isotónica sobre las filas con score; p_ausente = P(fraude | sin score) con
     intervalo de Wilson.
  3. Elegir en "aprender", certificar en "LTT": rejilla fija de umbrales (paso 0,5 en 0..100), marcado = score > τ.
     En aprender, el τ de mayor recall con FDR observada ≤ α y suficientes marcadas esperadas para poder rechazar.
     En LTT, una sola prueba: H0: FDR(τ) > α (α = 1 %), p-valor binomial exacto, se rechaza con δ = 5 %. Si no se
     rechaza, no hay umbral certificado y el sistema no recomienda bloqueos por su cuenta.
  4. Guardar el artefacto versionado (umbral, cota de FDR, calibradores) y registrar la corrida.
El umbral nunca se escribe a mano (INV-UMBRAL): sale de aquí.

Uso: python -m ml.m1_ltt [--parquet RUTA] [--reporte-test]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
from scipy.stats import beta, binom
from sklearn.isotonic import IsotonicRegression

RAIZ = Path(__file__).resolve().parents[1]
PARQUET = RAIZ.parent / "scratch" / "bronce" / "transactions.parquet"
ARTEFACTO = RAIZ / "artefactos" / "m1.json"
CORRIDAS = RAIZ / "artefactos" / "corridas_m1.jsonl"
ALFA, DELTA, PASO = 0.01, 0.05, 0.5
VENTANAS = {"aprender": ("2023-06-01", "2025-07-01"), "ltt": ("2025-07-01", "2026-01-01"), "test": ("2026-01-01", "2026-07-01")}
LINEA_BASE = {"regla": ">=", "valor": 50.0}     # regla del banco (diagnóstico)


def _conectar() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(config={"threads": 2, "memory_limit": "1GB"})
    c.execute("set enable_progress_bar = false")
    return c


def _base(c, parquet: Path) -> None:
    c.execute(f"""
        create or replace temp view tx as
        select transaction_id,
               cast(substr(transaction_date, 1, 10) as date) as fecha,
               try_cast(nullif(fraud_score, '') as double) as score,
               lower(is_fraud) = 'true' as fraude
        from (select *, row_number() over (partition by transaction_id order by process_date) as rn
              from read_parquet('{parquet}'))
        where rn = 1
    """)


def _ventana(nombre: str) -> str:
    a, b = VENTANAS[nombre]
    return f"fecha >= date '{a}' and fecha < date '{b}'"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return p, max(0.0, centro - margen), min(1.0, centro + margen)


def clopper_pearson_superior(k: int, n: int, confianza: float = 0.95) -> float:
    """Cota superior unilateral."""
    if n == 0:
        return 1.0
    return 1.0 if k >= n else float(beta.ppf(confianza, k + 1, n - k))


def calibrar(c) -> dict:
    filas = c.execute(f"""select round(score, 2) as s, count(*) n, sum(fraude::int) f from tx
                          where {_ventana('aprender')} and score is not null group by 1 order by 1""").fetchall()
    x = np.array([r[0] for r in filas])
    n = np.array([r[1] for r in filas], dtype=float)
    f = np.array([r[2] for r in filas], dtype=float)
    iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(x, f / n, sample_weight=n)
    k_aus, n_aus = c.execute(f"select sum(fraude::int), count(*) from tx where {_ventana('aprender')} and score is null").fetchone()
    p, lo, hi = wilson(int(k_aus or 0), int(n_aus or 0))
    return {"isotonica_x": [float(v) for v in iso.X_thresholds_], "isotonica_y": [float(v) for v in iso.y_thresholds_],
            "p_ausente": p, "p_ausente_ic95": [lo, hi], "n_aprender": int(n.sum()), "n_ausente": int(n_aus or 0)}


def conteos(c, ventana: str, tau: float, regla: str = ">") -> dict:
    op = ">" if regla == ">" else ">="
    n_marc, fp, tp, fraudes, legit = c.execute(f"""
        select count(*) filter (where score {op} {tau}),
               count(*) filter (where score {op} {tau} and not fraude),
               count(*) filter (where score {op} {tau} and fraude),
               count(*) filter (where fraude),
               count(*) filter (where not fraude)
        from tx where {_ventana(ventana)}""").fetchone()
    return {"tau": tau, "regla": regla, "n_marcadas": n_marc, "fp": fp, "tp": tp, "fraudes": fraudes,
            "legitimas": legit, "recall": tp / fraudes if fraudes else None,
            "fdr_observada": fp / n_marc if n_marc else None,
            "cota_fdr_95": clopper_pearson_superior(fp, n_marc), "fpr": fp / legit if legit else None}


def n_minimo() -> int:
    """Marcadas necesarias para que incluso 0 falsas alarmas rechacen H0: (1 − α)^n ≤ δ."""
    return math.ceil(math.log(DELTA) / math.log(1 - ALFA))


def _barrido(c, ventana: str) -> list[dict]:
    """Por cada τ de la rejilla fija: marcadas (score > τ), falsas alarmas y verdaderas."""
    f = c.execute(f"select score, fraude from tx where {_ventana(ventana)} and score is not null").fetchnumpy()
    orden = np.argsort(-f["score"])
    s, y = f["score"][orden], f["fraude"].astype(bool)[orden]
    fp_acum, tp_acum = np.cumsum(~y), np.cumsum(y)
    filas = []
    for i in range(int(100 / PASO) + 1):
        tau = round(100 - i * PASO, 1)
        k = int(np.searchsorted(-s, -tau, side="left"))
        filas.append({"tau": tau, "n_marcadas": k, "fp": int(fp_acum[k - 1]) if k else 0,
                      "tp": int(tp_acum[k - 1]) if k else 0})
    return filas


def seleccionar(c) -> dict:
    """Paso 1 (ventana de aprendizaje): el τ de mayor recall con FDR observada ≤ α y al menos n_minimo marcadas
    esperadas en la LTT. Paso 2 (ventana LTT): una sola prueba binomial exacta de H0: FDR(τ) > α. Una sola hipótesis:
    no hay multiplicidad que corregir, y la elección no mira la LTT."""
    n_apr = c.execute(f"select count(*) from tx where {_ventana('aprender')}").fetchone()[0]
    n_ltt = c.execute(f"select count(*) from tx where {_ventana('ltt')}").fetchone()[0]
    minimo_apr = n_minimo() * n_apr / n_ltt
    aprender = _barrido(c, "aprender")
    candidatos = [r for r in aprender if r["n_marcadas"] >= minimo_apr and r["fp"] <= ALFA * r["n_marcadas"]]
    if not candidatos:
        raise RuntimeError("ningún umbral candidato en la ventana de aprendizaje")
    elegido = max(candidatos, key=lambda r: (r["tp"], r["tau"]))
    tau = elegido["tau"]
    ltt_tabla = _barrido(c, "ltt")
    fila = next(r for r in ltt_tabla if r["tau"] == tau)
    pval = float(binom.cdf(fila["fp"], fila["n_marcadas"], ALFA)) if fila["n_marcadas"] else 1.0
    return {"umbral": tau, "certificado": fila["n_marcadas"] > 0 and pval <= DELTA, "p_valor": pval,
            "seleccion_aprender": elegido, "n_minimo": n_minimo(), "tabla_ltt": ltt_tabla}


def hash_archivo(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()[:16]


def correr(parquet: Path, reporte_test: bool) -> dict:
    t0 = time.time()
    c = _conectar()
    _base(c, parquet)
    cal = calibrar(c)
    sel = seleccionar(c)
    tau = sel["umbral"]
    en_ltt = conteos(c, "ltt", tau)
    artefacto = {
        "componente": "M1", "creado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "umbral": tau, "regla_marcado": "score > umbral", "alfa": ALFA, "delta": DELTA,
        "certificado": sel["certificado"], "p_valor_ltt": sel["p_valor"],
        "cota_fdr": en_ltt["cota_fdr_95"], "ltt": en_ltt, "seleccion_aprender": sel["seleccion_aprender"],
        "n_minimo": sel["n_minimo"], **cal,
        "datos": {"parquet": str(parquet.name), "hash": hash_archivo(parquet)},
        "ventanas": VENTANAS,
    }
    artefacto["version"] = hashlib.sha256(json.dumps(artefacto, sort_keys=True, default=str).encode()).hexdigest()[:12]
    reporte = {"ltt": {"propuesto": en_ltt, "linea_base": conteos(c, "ltt", LINEA_BASE["valor"], ">=")}}
    if reporte_test:      # el test bloqueado se mira solo en el reporte final
        reporte["test"] = {"propuesto": conteos(c, "test", tau),
                           "linea_base": conteos(c, "test", LINEA_BASE["valor"], ">="),
                           "mismo_valor_con_mayor_o_igual": conteos(c, "test", tau, ">=")}
    ARTEFACTO.parent.mkdir(exist_ok=True)
    ARTEFACTO.write_text(json.dumps(artefacto, indent=1, ensure_ascii=False))
    (RAIZ / "artefactos" / "m1_ltt_tabla.json").write_text(json.dumps(sel["tabla_ltt"], indent=0))
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=RAIZ).stdout.strip()
    except OSError:
        commit = None
    corrida = {"fecha": artefacto["creado"], "commit": commit, "version_artefacto": artefacto["version"],
               "hash_datos": artefacto["datos"]["hash"], "parametros": {"alfa": ALFA, "delta": DELTA, "paso": PASO},
               "umbral": tau, "reporte": reporte, "segundos": round(time.time() - t0, 1)}
    with open(CORRIDAS, "a") as f:
        f.write(json.dumps(corrida, ensure_ascii=False, default=str) + "\n")
    return corrida


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", type=Path, default=PARQUET)
    ap.add_argument("--reporte-test", action="store_true")
    a = ap.parse_args()
    print(json.dumps(correr(a.parquet, a.reporte_test), indent=1, ensure_ascii=False, default=str))
