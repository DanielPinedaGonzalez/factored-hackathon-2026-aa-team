"""¿Un modelo con TODAS las variables supera al puntaje del banco? (la prueba que faltaba para justificar que M1 solo calibra el puntaje)

Entrena LightGBM en la ventana de aprendizaje (2023-06..2025-06; todos los fraudes y el 5 % de los legítimos, con pesos) y lo mide en la ventana
de certificación (2025-07..2025-12) **sin tocar la prueba bloqueada de 2026-H1** (INV-EVAL). Compara, por AUC y AP (precisión promedio):
  (a) el puntaje del banco tal cual · (b) LightGBM solo con el puntaje · (c) LightGBM con todas las variables · (d) LightGBM con todas menos el puntaje.
Uso: python scripts/diagnostico/c_ablacion_lightgbm.py  → artefactos/ablacion_lightgbm.json
La memoria de la máquina es de 3 GB: DuckDB lee el parquet por tramos y solo llega a pandas la muestra de aprendizaje.
"""
import json
from pathlib import Path

import duckdb
import lightgbm as lgb
import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

RAIZ = Path(__file__).resolve().parents[2]
PARQUET = RAIZ.parent / "scratch" / "bronce" / "transactions.parquet"
CATEGORICAS = ["tipo", "canal", "moneda", "pais", "categoria", "cat_comercio", "estado", "respuesta"]
NUMERICAS = ["monto_usd", "hora", "dia_semana", "dia_mes"]
SELECT = """
    select cast(substr(transaction_date, 1, 10) as date) as fecha,
           try_cast(nullif(fraud_score, '') as double) as score, try_cast(nullif(amount_usd, '') as double) as monto_usd,
           hour(try_cast(transaction_date as timestamp)) as hora, dayofweek(try_cast(transaction_date as timestamp)) as dia_semana,
           day(try_cast(transaction_date as timestamp)) as dia_mes,
           transaction_type as tipo, channel as canal, currency as moneda, transaction_country as pais,
           transaction_category as categoria, merchant_category as cat_comercio, transaction_status as estado, response_code as respuesta,
           (lower(is_fraud) = 'true')::int as y, transaction_id
    from (select *, row_number() over (partition by transaction_id order by process_date) as rn from read_parquet('{p}')) where rn = 1"""


def cargar(c, desde: str, hasta: str, muestra_legitimos: float | None):
    filtro = f"fecha >= date '{desde}' and fecha < date '{hasta}'"
    if muestra_legitimos is not None:
        filtro += f" and (y = 1 or hash(transaction_id) % 1000 < {int(muestra_legitimos * 1000)})"
    return c.execute(f"select * exclude(transaction_id, fecha) from ({SELECT.format(p=PARQUET)}) where {filtro}").df()


def matriz(df, columnas, categorias):
    X = df[columnas].copy()
    for col in columnas:
        if col in CATEGORICAS:
            X[col] = X[col].astype(object).where(X[col].notna(), "∅").astype("category")
            X[col] = X[col].cat.set_categories(categorias[col])
    return X


def main():
    c = duckdb.connect(config={"threads": 2, "memory_limit": "1GB"})
    c.execute("set enable_progress_bar = false")
    apr = cargar(c, "2023-06-01", "2025-07-01", 0.05)
    cer = cargar(c, "2025-07-01", "2026-01-01", None)
    categorias = {k: sorted(set(apr[k].astype(object).where(apr[k].notna(), "∅")) | set(cer[k].astype(object).where(cer[k].notna(), "∅")))
                  for k in CATEGORICAS}
    w = np.where(apr["y"] == 1, 1.0, 1 / 0.05)        # los legítimos se submuestrearon al 5 %: se pesan para recuperar la proporción real
    todas = ["score"] + NUMERICAS + CATEGORICAS
    sin_score = NUMERICAS + CATEGORICAS
    resultados = {"aprender": {"filas": len(apr), "fraudes": int(apr["y"].sum())},
                  "certificar": {"filas": len(cer), "fraudes": int(cer["y"].sum())}}
    y = cer["y"].to_numpy()
    puntaje = cer["score"].fillna(-1).to_numpy()
    resultados["a_puntaje_del_banco"] = {"auc": roc_auc_score(y, puntaje), "ap": average_precision_score(y, puntaje)}
    for nombre, cols in (("b_lightgbm_solo_puntaje", ["score"]), ("c_lightgbm_todas", todas), ("d_lightgbm_sin_puntaje", sin_score)):
        modelo = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1,
                                    colsample_bytree=0.8, random_state=7, n_jobs=2, verbose=-1)
        modelo.fit(matriz(apr, cols, categorias), apr["y"], sample_weight=w)
        p = modelo.predict_proba(matriz(cer, cols, categorias))[:, 1]
        resultados[nombre] = {"auc": roc_auc_score(y, p), "ap": average_precision_score(y, p)}
    resultados["azar"] = {"ap": float(y.mean())}
    resultados["nota"] = "ventana de certificación 2025-H2; la prueba bloqueada 2026-H1 no se usa"
    destino = RAIZ / "artefactos" / "ablacion_lightgbm.json"
    destino.write_text(json.dumps(resultados, indent=1), encoding="utf-8")
    print(json.dumps(resultados, indent=1))


if __name__ == "__main__":
    main()
