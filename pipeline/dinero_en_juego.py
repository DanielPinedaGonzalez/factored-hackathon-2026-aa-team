"""Umbral de "dinero en juego" por tipo de movimiento (PROCESOS §P2.3): el cuantil declarado en la política común
(`politica/comun.yaml`, `dinero_en_juego.cuantil`) de amount_usd sobre todos los movimientos de plata, por tipo.

El número nunca se escribe a mano: sale de los datos y queda versionado en `artefactos/dinero_en_juego.json`, con la
tasa de fraude de cada tipo al lado. Esa tasa es la prueba de por qué el monto no es una señal de fraude en estos
datos (la misma en todos los tramos); se usa como daño posible para el cliente, no como riesgo.

Uso: python -m pipeline.dinero_en_juego
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import yaml

RAIZ = Path(__file__).resolve().parents[1]
PLATA = RAIZ.parent / "scratch" / "plata"
SALIDA = RAIZ / "artefactos" / "dinero_en_juego.json"


def calcular() -> dict:
    cuantil = yaml.safe_load((RAIZ / "politica" / "comun.yaml").read_text(encoding="utf-8"))["dinero_en_juego"]["cuantil"]
    c = duckdb.connect(config={"threads": 2, "memory_limit": "1GB"})
    filas = c.execute(f"""select tipo, count(*), quantile_cont(amount_usd, {float(cuantil)}), avg(fraude::int)
                          from read_parquet('{PLATA}/transacciones/*/*.parquet') where amount_usd is not null
                          group by 1 order by 1""").fetchall()
    return {"componente": "dinero_en_juego", "creado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cuantil": cuantil, "fuente": "plata/transacciones (todos los movimientos con amount_usd)",
            "por_tipo": {t: {"umbral_usd": round(u, 2), "n": n, "tasa_fraude": round(f, 5)} for t, n, u, f in filas}}


if __name__ == "__main__":
    a = calcular()
    SALIDA.write_text(json.dumps(a, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(a["por_tipo"], ensure_ascii=False))
