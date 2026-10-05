"""Perfil de cada cliente de demostración, calculado de los datos cargados (nada escrito a mano).

Lo que el jurado ve al elegir un cliente («Cliente N») son sus características reales: país, segmento, productos, movimientos, el movimiento
mayor, el comercio que más se repite, si tuvo un cargo «ayer» (el último día de los datos es «hoy») y su señal de riesgo frente al umbral certificado.
Antes cada cliente llevaba una etiqueta escrita a mano que describía un caso («tres cargos del mismo comercio»); los datos la desmintieron (eran seis).

Uso: python scripts/perfiles_demo.py          # escribe evaluacion/identidades_demo.json (se corre al final de `make datos`)
La API solo lee ese archivo; no consulta la base para esto. Sin identificadores del organizador: solo documento de demo y rasgos."""
import json
import sys
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from servicio.datos.db import URL_ADMIN  # noqa: E402

SALIDA = RAIZ / "evaluacion" / "identidades_demo.json"
MIN_REPETIDOS = 3          # un comercio cuenta como «repetido» desde tres cargos


def calcular(c) -> list[dict]:
    umbral = json.loads((RAIZ / "artefactos" / "m1.json").read_text())["umbral"]
    hoy = c.execute("select max(fecha)::date from servicio.transacciones").fetchone()[0]       # el último día de los datos es «hoy» en la demo
    perfiles = []
    for documento, cid, pais, segmento in c.execute("""select i.documento_demo, i.customer_id, cl.pais, cl.segmento
            from atencion.identidades_demo i join servicio.clientes cl using (customer_id)
            where i.documento_demo like 'DEMO-%' order by 1""").fetchall():
        productos = [r[0] for r in c.execute("select tipo from servicio.productos where customer_id = %s order by tipo", (cid,)).fetchall()]
        movs, ayer = c.execute("select count(*), count(*) filter (where fecha::date = %s::date - 1) from servicio.transacciones where customer_id = %s",
                               (hoy, cid)).fetchone()
        mayor = c.execute("select tipo, round(amount_usd)::int from servicio.transacciones where customer_id = %s and amount_usd is not null "
                          "order by amount_usd desc limit 1", (cid,)).fetchone()
        rep = c.execute("select comercio, count(*) n from servicio.transacciones where customer_id = %s and comercio is not null "
                        "group by 1 order by 2 desc, 1 limit 1", (cid,)).fetchone()
        score = c.execute("select max(fraud_score) from servicio.transacciones where customer_id = %s", (cid,)).fetchone()[0]
        perfiles.append({"documento": documento, "pais": pais, "segmento": segmento, "productos": productos, "movimientos": movs, "cargos_ayer": ayer,
                         "mayor": {"tipo": mayor[0], "usd": mayor[1]} if mayor else None,
                         "comercio_repetido": {"comercio": rep[0], "veces": rep[1]} if rep and rep[1] >= MIN_REPETIDOS else None,
                         "riesgo": {"score_max": float(score), "umbral": umbral, "supera": float(score) > umbral} if score is not None else None})
    return perfiles


def main() -> None:
    with psycopg.connect(URL_ADMIN, autocommit=True) as c:
        perfiles = calcular(c)
    SALIDA.write_text(json.dumps(perfiles, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for p in perfiles:
        print(p["documento"], p["pais"], p["segmento"], f"{p['movimientos']} movs", f"{len(p['productos'])} productos", p["comercio_repetido"], p["riesgo"] and p["riesgo"]["supera"])


if __name__ == "__main__":
    main()
