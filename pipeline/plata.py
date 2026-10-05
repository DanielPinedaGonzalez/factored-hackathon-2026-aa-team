"""Bronce → plata (02_PLAN §7; R6): tipos, deduplicación, marcas de coherencia y contratos de calidad.

Bronce: los CSV del organizador convertidos a Parquet sin tocar (todo texto, con el archivo de origen). Plata: tipos
explícitos, una fila por transacción, marcas de coherencia por fila (sin corregir el dato) y un reporte de calidad
con cada contrato y su resultado. Todo en DuckDB, con memoria limitada (INV-MEMORIA).

Incremental: la marca de agua es el `process_date` máximo cargado. Una corrida nueva reprocesa los meses que
tocan los `process_date` posteriores a la marca (llegadas tardías incluidas) y es idempotente.

Uso: python -m pipeline.plata [--bronce DIR] [--plata DIR] [--completo]
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[1]
BRONCE = RAIZ.parent / "scratch" / "bronce"
PLATA = RAIZ.parent / "scratch" / "plata"
REPORTE = RAIZ / "artefactos" / "calidad_datos.json"

# Moneda esperada por país de la transacción. En los datos, México opera en USD (medido; declarado).
MONEDAS_VALIDAS = {"Argentina": ("ARS", "USD"), "Colombia": ("COP", "USD"), "México": ("USD",), "Mexico": ("USD",),
                   "Brazil": ("USD",), "Spain": ("USD",), "USA": ("USD",)}
# Tipos de operación que un canal puede producir. Lo que queda fuera se marca, no se corrige.
TIPOS_POR_CANAL = {"ATM": ("Withdrawal", "Deposit"), "POS": ("Purchase", "Payment"),
                   "Transfer": ("Transfer",), "App": None, "Web": None, "Branch": None}   # None = cualquiera
PAIS = {"México": "MX", "Colombia": "CO", "Argentina": "AR"}


def conectar() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(config={"threads": 2, "memory_limit": "1GB"})
    c.execute("set enable_progress_bar = false")
    c.execute("set preserve_insertion_order = false")
    return c


def _en(valores) -> str:
    return "(" + ",".join(f"'{v}'" for v in valores) + ")"


def _sql_coherencia() -> tuple[str, str]:
    moneda = " or ".join(f"(transaction_country = '{p}' and currency in {_en(m)})" for p, m in MONEDAS_VALIDAS.items())
    canal = " or ".join(f"(channel = '{c}'" + (f" and transaction_type in {_en(t)})" if t else ")")
                        for c, t in TIPOS_POR_CANAL.items())
    return f"({moneda})", f"({canal})"


def construir(bronce: Path, plata: Path, completo: bool = False) -> dict:
    t0 = time.time()
    plata.mkdir(parents=True, exist_ok=True)
    c = conectar()
    moneda_ok, canal_ok = _sql_coherencia()
    marca_archivo = plata / "marca_de_agua.json"
    marca = None if completo or not marca_archivo.exists() else json.loads(marca_archivo.read_text())["process_date"]

    c.execute(f"""create or replace temp view productos as select
        product_id, customer_id, product_type as tipo, product_status as estado, currency as moneda,
        right(product_number, 4) as ultimos4, try_cast(opening_date as date) as apertura
        from read_parquet('{bronce}/products.parquet')""")
    c.execute(f"copy productos to '{plata}/productos.parquet' (format parquet)")
    c.execute(f"""copy (select customer_id, country as pais_nombre, segment as segmento, customer_status as estado,
        detected_accent as acento, split_part(first_name, ' ', 1) as nombre_pila
        from read_parquet('{bronce}/customers.parquet')) to '{plata}/clientes.parquet' (format parquet)""")
    c.execute(f"""copy (select try_cast(date as date) as fecha, source_currency as moneda,
        try_cast(exchange_rate as double) as tasa_a_usd
        from read_parquet('{bronce}/daily_exchange_rates.parquet') where target_currency = 'USD')
        to '{plata}/tasas.parquet' (format parquet)""")
    c.execute(f"""copy (select agent_id, employee_code, agent_type, languages, specialty, work_shift, agent_status,
        country_of_origin from read_parquet('{bronce}/service_agents.parquet')) to '{plata}/asesores.parquet' (format parquet)""")

    filtro = f"where process_date > '{marca}'" if marca else ""
    meses = [r[0] for r in c.execute(f"""select distinct substr(transaction_date, 1, 7) from read_parquet('{bronce}/transactions.parquet')
                                          {filtro}""").fetchall()] if marca else None
    donde_meses = f"and substr(transaction_date, 1, 7) in {_en(meses)}" if meses else ""
    if marca and not meses:
        return {"meses_reprocesados": [], "segundos": round(time.time() - t0, 1)}
    c.execute(f"""create or replace temp table tx as
        select transaction_id, customer_id, product_id,
               cast(transaction_date as timestamp) as fecha, cast(process_date as date) as fecha_proceso,
               transaction_type as tipo, nullif(transaction_category, '') as categoria,
               try_cast(amount as decimal(18,2)) as monto, currency as moneda,
               try_cast(nullif(amount_usd, '') as decimal(18,2)) as amount_usd_original,
               channel as canal, nullif(merchant_name, '') as comercio, nullif(merchant_category, '') as categoria_comercio,
               transaction_country as pais_transaccion, transaction_city as ciudad, transaction_status as estado,
               response_code as codigo_respuesta, lower(is_fraud) = 'true' as fraude,
               try_cast(nullif(fraud_score, '') as double) as fraud_score,
               {canal_ok} as canal_tipo_coherente, {moneda_ok} as moneda_pais_coherente,
               substr(transaction_date, 1, 7) as mes
        from (select *, row_number() over (partition by transaction_id order by process_date desc, _archivo) as rn
              from read_parquet('{bronce}/transactions.parquet') where true {donde_meses}) where rn = 1""")
    # USD derivado con la tasa del día cuando el organizador no lo trae; sin tasa, queda desconocido (NULL).
    c.execute(f"""create or replace temp table tx2 as select t.*,
        coalesce(t.amount_usd_original, case when t.moneda = 'USD' then t.monto end,
                 round(t.monto * r.tasa_a_usd, 2)) as amount_usd,
        (t.fecha::date >= p.apertura) as fecha_producto_coherente
        from tx t left join productos p using (product_id)
        left join read_parquet('{plata}/tasas.parquet') r on r.moneda = t.moneda and r.fecha = t.fecha::date""")
    c.execute(f"copy (select * exclude (amount_usd_original) from tx2) to '{plata}/transacciones' "
              f"(format parquet, partition_by (mes), overwrite_or_ignore true)")

    contratos = contratos_de_calidad(c)
    nueva_marca = c.execute(f"select max(process_date) from read_parquet('{bronce}/transactions.parquet')").fetchone()[0]
    marca_archivo.write_text(json.dumps({"process_date": str(nueva_marca)}))
    reporte = {"fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"), "marca_anterior": marca,
               "marca_nueva": str(nueva_marca), "meses_reprocesados": meses or "todos", "contratos": contratos,
               "segundos": round(time.time() - t0, 1)}
    REPORTE.parent.mkdir(exist_ok=True)
    REPORTE.write_text(json.dumps(reporte, indent=1, ensure_ascii=False, default=str))
    return reporte


def contratos_de_calidad(c) -> list[dict]:
    """Cada contrato: nombre, severidad (bloquea | advierte), filas que lo incumplen, total. Bloquear detiene la carga."""
    reglas = [
        ("transaction_id único", "bloquea", "select count(*) - count(distinct transaction_id) from tx2"),
        ("customer_id presente", "bloquea", "select count(*) filter (where customer_id is null or customer_id = '') from tx2"),
        ("fecha válida", "bloquea", "select count(*) filter (where fecha is null) from tx2"),
        ("monto numérico y positivo", "advierte", "select count(*) filter (where monto is null or monto <= 0) from tx2"),
        ("estado conocido", "bloquea", "select count(*) filter (where estado not in ('Approved','Pending','Declined','Reversed')) from tx2"),
        ("fraud_score en [0, 100] o ausente", "bloquea", "select count(*) filter (where fraud_score < 0 or fraud_score > 100) from tx2"),
        ("moneda coherente con el país (marca)", "advierte", "select count(*) filter (where not moneda_pais_coherente) from tx2"),
        ("tipo coherente con el canal (marca)", "advierte", "select count(*) filter (where not canal_tipo_coherente) from tx2"),
        ("fecha posterior a la apertura del producto (marca)", "advierte", "select count(*) filter (where not fecha_producto_coherente) from tx2"),
        ("monto en USD conocido", "advierte", "select count(*) filter (where amount_usd is null) from tx2"),
    ]
    total = c.execute("select count(*) from tx2").fetchone()[0]
    salida = []
    for nombre, severidad, sql in reglas:
        n = c.execute(sql).fetchone()[0]
        salida.append({"contrato": nombre, "severidad": severidad, "incumplen": n, "total": total,
                       "porcentaje": round(100 * n / total, 2) if total else 0.0, "cumple": n == 0})
    rotos = [s["contrato"] for s in salida if s["severidad"] == "bloquea" and not s["cumple"]]
    if rotos:
        raise RuntimeError(f"contratos que bloquean la carga: {rotos}")
    return salida


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bronce", type=Path, default=BRONCE)
    ap.add_argument("--plata", type=Path, default=PLATA)
    ap.add_argument("--completo", action="store_true")
    a = ap.parse_args()
    print(json.dumps(construir(a.bronce, a.plata, a.completo), indent=1, ensure_ascii=False, default=str))
