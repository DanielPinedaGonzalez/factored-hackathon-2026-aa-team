"""Métricas complementarias de M1 para un problema con 0,1 % de positivos (02_PLAN §4).

El umbral y su certificado salen de `ml/m1_ltt.py`; aquí solo se **describe** qué tan bien ordena y calibra M1 en las
ventanas LTT y test. No elige nada: nada de lo que se calcula aquí vuelve al umbral ni a los calibradores.

Para cada ventana, sobre las filas con score:
  - ROC-AUC y PR-AUC (precisión promedio) del score crudo; la PR-AUC se compara con la prevalencia, que es lo que
    obtendría un clasificador al azar.
  - Brier de la probabilidad calibrada (isotónica de `artefactos/m1.json`) frente al Brier de la prevalencia
    constante de la ventana de aprendizaje; Brier skill score = 1 − Brier / Brier_referencia.
  - Calibración por tramos de probabilidad predicha: probabilidad media, frecuencia observada y n por tramo.
Sobre las filas sin score: frecuencia observada de fraude frente a `p_ausente` (la probabilidad guardada).
Todas las cifras llevan su n; los intervalos de las frecuencias son de Wilson.

Uso: python -m ml.metricas_m1 [--parquet RUTA]    → artefactos/m1_metricas.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from ml.m1_ltt import ARTEFACTO, PARQUET, RAIZ, _base, _conectar, _ventana, wilson

SALIDA = RAIZ / "artefactos" / "m1_metricas.json"
TRAMOS = [0.0, 1e-4, 1e-3, 1e-2, 0.1, 0.5, 1.0000001]


def _probabilidad(art: dict, score: np.ndarray) -> np.ndarray:
    """La isotónica guardada, evaluada igual que al calibrar (se recorta fuera del rango visto)."""
    return np.interp(score, art["isotonica_x"], art["isotonica_y"])


def _tramos(p: np.ndarray, y: np.ndarray) -> list[dict]:
    filas = []
    for lo, hi in zip(TRAMOS[:-1], TRAMOS[1:]):
        m = (p >= lo) & (p < hi)
        n = int(m.sum())
        if n == 0:
            continue
        k = int(y[m].sum())
        _, a, b = wilson(k, n)
        filas.append({"desde": lo, "hasta": min(hi, 1.0), "n": n, "fraudes": k,
                      "prob_media_predicha": float(p[m].mean()), "frecuencia_observada": k / n,
                      "ic95_frecuencia": [a, b]})
    return filas


def _ventana_con_score(c, art: dict, nombre: str, prevalencia_ref: float) -> dict:
    f = c.execute(f"select score, fraude from tx where {_ventana(nombre)} and score is not null").fetchnumpy()
    s, y = f["score"], f["fraude"].astype(int)
    p = _probabilidad(art, s)
    prev = float(y.mean())
    brier = float(brier_score_loss(y, p))
    brier_ref = float(brier_score_loss(y, np.full_like(p, prevalencia_ref)))
    return {"n": int(len(y)), "fraudes": int(y.sum()), "prevalencia": prev,
            "roc_auc_score_crudo": float(roc_auc_score(y, s)),
            "pr_auc_score_crudo": float(average_precision_score(y, s)),
            "pr_auc_al_azar": prev,
            "brier_calibrada": brier, "brier_prevalencia_constante": brier_ref,
            "brier_skill_score": 1 - brier / brier_ref,
            "calibracion_por_tramos": _tramos(p, y)}


def _ventana_sin_score(c, art: dict, nombre: str) -> dict:
    n, k = c.execute(f"select count(*), sum(fraude::int) from tx where {_ventana(nombre)} and score is null").fetchone()
    n, k = int(n or 0), int(k or 0)
    p, lo, hi = wilson(k, n)
    return {"n": n, "fraudes": k, "frecuencia_observada": p, "ic95": [lo, hi], "p_ausente_guardada": art["p_ausente"],
            "dentro_del_ic": bool(lo <= art["p_ausente"] <= hi) if n else None}


def correr(parquet: Path) -> dict:
    art = json.loads(ARTEFACTO.read_text())
    c = _conectar()
    _base(c, parquet)
    n_apr, k_apr = c.execute(f"select count(*), sum(fraude::int) from tx where {_ventana('aprender')} and score is not null").fetchone()
    prev_ref = k_apr / n_apr
    out = {"version_m1": art["version"], "prevalencia_referencia_aprender": prev_ref, "ventanas": {}}
    for v in ("ltt", "test"):
        out["ventanas"][v] = {"con_score": _ventana_con_score(c, art, v, prev_ref), "sin_score": _ventana_sin_score(c, art, v)}
    SALIDA.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", type=Path, default=PARQUET)
    print(json.dumps(correr(ap.parse_args().parquet), indent=1, ensure_ascii=False))
