"""Selección determinista de clientes reales para los casos canónicos y la demo (02_PLAN §8 y §9).

Por cada caso de `evaluacion/ground_truth_cases.yaml` y cada conjunto (desarrollo: transacciones 2025-H2; final:
2026-H1) se toma al azar, con semilla derivada del id del caso y del conjunto, un cliente que cumple el perfil. Nada
se elige a mano. El reloj de cada caso es el día siguiente a su transacción objetivo, para que "ayer" sea real.
El manifest resultante es la única lista de clientes que se carga a la base (el subconjunto declarado).

Uso: python -m pipeline.seleccion
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import duckdb
import yaml

RAIZ = Path(__file__).resolve().parents[1]
PLATA = RAIZ.parent / "scratch" / "plata"
MANIFEST = RAIZ / "evaluacion" / "manifest_casos.json"
CONJUNTOS = {"desarrollo": ("2025-07-01", "2026-01-01"), "final": ("2026-01-01", "2026-06-19")}
RELOJ_DEMO = date(2026, 6, 18)
TARJETAS = ("Tarjeta Crédito", "Tarjeta Débito")
PAISES = {"México": "MX", "Colombia": "CO", "Argentina": "AR"}

# Identidades de demo (F-3): reproducen los tres casos obligatorios y los que más muestran el diseño.
DEMO = [
    {"documento": "DEMO-1001", "perfil": {"tipo": "un_cargo", "monto_usd_max": 500, "senal": "bajo"}},
    {"documento": "DEMO-1002", "perfil": {"tipo": "varios_mismo_comercio", "cantidad": 3, "monto_usd_max": 500, "senal": "bajo"}},
    {"documento": "DEMO-1003", "perfil": {"tipo": "un_cargo", "monto_usd_min": 2000, "senal": "bajo"}},
    {"documento": "DEMO-1004", "perfil": {"tipo": "con_tarjeta_activa"}},
    {"documento": "DEMO-1005", "perfil": {"tipo": "un_cargo", "pais": "MX", "monto_usd_max": 500, "senal": "bajo"}},
    {"documento": "DEMO-1006", "perfil": {"tipo": "un_cargo", "segmento": "Premium", "monto_usd_max": 500, "senal": "bajo"}},
    {"documento": "DEMO-1007", "perfil": {"tipo": "un_cargo", "score_min_estricto": "umbral"}},
]


def _semilla(*partes: str) -> int:
    return int(hashlib.sha256("|".join(partes).encode()).hexdigest()[:8], 16)


def conectar() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(config={"threads": 2, "memory_limit": "1GB"})
    c.execute("set enable_progress_bar = false")
    c.execute(f"create or replace view tx as select * from read_parquet('{PLATA}/transacciones/*/*.parquet', hive_partitioning = true)")
    c.execute(f"create or replace view cli as select * from read_parquet('{PLATA}/clientes.parquet')")
    c.execute(f"create or replace view prod as select * from read_parquet('{PLATA}/productos.parquet')")
    return c


def _umbral() -> float:
    return json.loads((RAIZ / "artefactos" / "m1.json").read_text())["umbral"]


def elegir(c, perfil: dict, ventana: tuple[str, str], semilla: int, excluir: set[str]) -> dict | None:
    """Devuelve {customer_id, transaction_id?, reloj, extra} o None si ningún cliente cumple el perfil."""
    tipo = perfil["tipo"]
    filtros_cli = ["c.pais_nombre in ('México','Colombia','Argentina')", "c.estado = 'Active'"]
    if "pais" in perfil:
        filtros_cli.append(f"c.pais_nombre = '{[k for k, v in PAISES.items() if v == perfil['pais']][0]}'")
    if "segmento" in perfil:
        filtros_cli.append(f"c.segmento = '{perfil['segmento']}'")
    excl = "and t.customer_id not in (" + ",".join(f"'{e}'" for e in excluir) + ")" if excluir else ""
    orden = f"order by hash(t.transaction_id || '{semilla}') limit 1"
    a, b = ventana

    if tipo in ("un_cargo", "cargo_en_otro_producto"):
        f = ["t.estado = 'Approved'", "t.moneda_pais_coherente", "t.amount_usd is not null"]
        # Las compras con comercio no pasan de ~510 USD en los datos (medido): los montos altos son retiros y transferencias.
        if "movimiento" in perfil:              # un tipo de movimiento del dato fijado por el caso
            f.append(f"t.tipo = '{perfil['movimiento']}'")
        else:
            f += (["t.tipo in ('Withdrawal','Transfer','Payment')"] if "monto_usd_min" in perfil
                  else ["t.tipo in ('Purchase','Payment')", "t.comercio is not null"])
        if "monto_usd_max" in perfil:
            f.append(f"t.amount_usd <= {perfil['monto_usd_max']}")
        if "monto_usd_min" in perfil:
            f.append(f"t.amount_usd >= {perfil['monto_usd_min']}")
        if perfil.get("senal") == "bajo":        # con score y sin superar el umbral certificado de M1
            f.append(f"t.fraud_score is not null and t.fraud_score <= {_umbral()}")
        if perfil.get("score_min_estricto") == "umbral":
            f.append(f"t.fraud_score > {_umbral()}")
        # un solo candidato ese día con monto parecido (±10 %)
        f.append("""not exists (select 1 from tx o where o.customer_id = t.customer_id and o.transaction_id <> t.transaction_id
                    and o.fecha::date = t.fecha::date and abs(o.monto - t.monto) <= 0.1 * t.monto)""")
        if tipo == "cargo_en_otro_producto":
            f.append(f"""(select count(*) from prod p where p.customer_id = t.customer_id and p.tipo in {TARJETAS}) >= 2""")
        fila = c.execute(f"""select t.customer_id, t.transaction_id, t.fecha::date from tx t join cli c using (customer_id)
            where t.fecha >= '{a}' and t.fecha < '{b}' and {' and '.join(f + filtros_cli)} {excl} {orden}""").fetchone()
        return fila and {"customer_id": fila[0], "transaction_id": fila[1], "reloj": str(fila[2] + timedelta(days=1))}

    if tipo in ("varios_mismo_comercio", "varios_cargos"):
        n = perfil.get("cantidad", 3)
        agrupar = "t.comercio" if tipo == "varios_mismo_comercio" else "1"
        f = ["t.tipo in ('Purchase','Payment')", "t.estado = 'Approved'", "t.comercio is not null"]
        if "monto_usd_max" in perfil:
            f.append(f"t.amount_usd <= {perfil['monto_usd_max']}")
        if perfil.get("senal") == "bajo":
            f.append(f"t.fraud_score is not null and t.fraud_score <= {_umbral()}")
        # n a 5 cargos (se listan todos) dentro de 30 días; el reloj queda al día siguiente del último
        fila = c.execute(f"""with g as (select t.customer_id, {agrupar} as grupo, max(t.fecha::date) as ultima,
                list(t.transaction_id order by t.fecha desc) as ids, count(*) as n
                from tx t join cli c using (customer_id)
                where t.fecha >= '{a}' and t.fecha < '{b}' and {' and '.join(f + filtros_cli)} {excl}
                group by t.customer_id, {agrupar}
                having count(*) between {n} and 5 and max(t.fecha::date) - min(t.fecha::date) <= 30)
            select customer_id, grupo, ultima, ids from g order by hash(customer_id || '{semilla}') limit 1""").fetchone()
        return fila and {"customer_id": fila[0], "reloj": str(fila[2] + timedelta(days=1)),
                         "extra": {"comercio": fila[1] if tipo == "varios_mismo_comercio" else None, "transacciones": fila[3]}}

    # Perfiles que necesitan solo un cliente con cierto producto; la preparación (reclamos, bloqueos) la hace el corredor.
    f = list(filtros_cli)
    if tipo in ("con_tarjeta_activa", "con_bloqueo_por_riesgo", "con_bloqueo_del_cliente"):
        f.append(f"exists (select 1 from prod p where p.customer_id = c.customer_id and p.tipo in {TARJETAS} and p.estado = 'Active')")
    f.append(f"exists (select 1 from tx t where t.customer_id = c.customer_id and t.fecha >= '{a}' and t.fecha < '{b}' "
             f"and t.tipo in ('Purchase','Payment') and t.estado = 'Approved' and t.moneda_pais_coherente "
             f"and t.fraud_score is not null and t.fraud_score <= {_umbral()})")
    excl_c = "and c.customer_id not in (" + ",".join(f"'{e}'" for e in excluir) + ")" if excluir else ""
    fila = c.execute(f"""select c.customer_id from cli c where {' and '.join(f)} {excl_c}
                         order by hash(c.customer_id || '{semilla}') limit 1""").fetchone()
    if not fila:
        return None
    ultima = c.execute(f"""select max(fecha::date) from tx where customer_id = '{fila[0]}' and fecha >= '{a}' and fecha < '{b}'""").fetchone()[0]
    return {"customer_id": fila[0], "reloj": str(ultima + timedelta(days=1)), "preparacion": tipo if tipo.startswith("con_") else None}


def seleccionar() -> dict:
    c = conectar()
    casos = yaml.safe_load((RAIZ / "evaluacion" / "ground_truth_cases.yaml").read_text())["casos"]
    usados: set[str] = set()
    salida = {"semilla_base": "id del caso + conjunto", "conjuntos": CONJUNTOS, "casos": {}, "demo": []}
    for conjunto, ventana in CONJUNTOS.items():
        for caso in casos:
            r = elegir(c, caso["perfil"], ventana, _semilla(caso["id"], conjunto), usados)
            if r is None:
                raise RuntimeError(f"ningún cliente cumple el perfil de {caso['id']} en {conjunto}")
            usados.add(r["customer_id"])
            salida["casos"].setdefault(caso["id"], {})[conjunto] = r
    for d in DEMO:
        # el cargo de la demo es del día anterior al reloj del sandbox, para que "ayer" sea real
        ventana = ("2026-06-17", "2026-06-18") if d["perfil"]["tipo"] == "un_cargo" else ("2026-05-18", "2026-06-18")
        r = elegir(c, d["perfil"], ventana, _semilla(d["documento"]), usados)
        if r is None:
            raise RuntimeError(f"ninguna identidad de demo para {d['documento']}")
        usados.add(r["customer_id"])
        salida["demo"].append({**d, **r, "reloj": str(RELOJ_DEMO)})
    salida["clientes"] = sorted(usados)
    salida["hash"] = hashlib.sha256(json.dumps(salida, sort_keys=True).encode()).hexdigest()[:16]
    MANIFEST.write_text(json.dumps(salida, indent=1, ensure_ascii=False))
    # Lo que se publica de la demo: solo el documento; los rasgos de cada cliente los calcula `scripts/perfiles_demo.py` de los datos cargados
    # (antes había una etiqueta escrita a mano por cliente, y los datos la desmintieron).
    (RAIZ / "evaluacion" / "identidades_demo.json").write_text(json.dumps(
        [{"documento": d["documento"]} for d in salida["demo"]], indent=1, ensure_ascii=False))
    return salida


if __name__ == "__main__":
    s = seleccionar()
    print(len(s["clientes"]), "clientes; hash", s["hash"])
