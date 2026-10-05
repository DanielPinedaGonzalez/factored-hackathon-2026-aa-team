"""A5 — Señal de riesgo (M1) (CONTRATOS A5).

Lee el artefacto versionado de M1: el umbral nunca está escrito en el código (INV-UMBRAL). La señal nunca llega al
Intérprete, al Redactor ni al cliente: solo a la política y al panel del asesor.
"""
from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ARTEFACTO = Path(__file__).resolve().parents[2] / "artefactos" / "m1.json"


@dataclass(frozen=True)
class Senal:
    p: float | None                  # None = sin score
    supera_umbral_certificado: bool
    cota_fdr: float | None
    version: str | None


@functools.lru_cache(maxsize=1)
def artefacto() -> dict | None:
    return json.loads(ARTEFACTO.read_text()) if ARTEFACTO.exists() else None


def evaluar(fraud_score: float | None) -> Senal:
    a = artefacto()
    if a is None:
        return Senal(None, False, None, None)
    if fraud_score is None:
        return Senal(a["p_ausente"], False, a["cota_fdr"] if a["certificado"] else None, a["version"])
    p = float(np.interp(fraud_score, a["isotonica_x"], a["isotonica_y"]))
    supera = bool(a["certificado"] and fraud_score > a["umbral"])
    return Senal(p, supera, a["cota_fdr"] if a["certificado"] else None, a["version"])
