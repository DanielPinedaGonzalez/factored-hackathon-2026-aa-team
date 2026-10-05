"""Bronce → plata sobre un FIXTURE SINTÉTICO de pocas filas (no son datos del organizador).

El reto pide demostrar la corrección de la actualización cuando solo hay datos estáticos: aquí se simulan entregas
sucesivas del mismo archivo de transacciones. Se prueba: deduplicación (gana el process_date más reciente), marca de
agua, reproceso solo de los meses tocados por una llegada tardía, idempotencia, marcas de coherencia que no corrigen
el dato y contratos que bloquean la carga.
"""
import json

import duckdb
import pytest

from pipeline import plata

COLUMNAS_TX = ["transaction_id", "customer_id", "product_id", "transaction_date", "process_date", "transaction_type",
               "transaction_category", "amount", "currency", "amount_usd", "channel", "merchant_name",
               "merchant_category", "transaction_country", "transaction_city", "transaction_status", "response_code",
               "is_fraud", "fraud_score", "_archivo"]


def _tx(tid, fecha, proceso, monto="10.00", score="", fraude="False", moneda="USD", pais="Colombia", canal="POS",
        tipo="Purchase", estado="Approved"):
    return [tid, "C1", "P1", f"{fecha} 10:00:00", proceso, tipo, "", monto, moneda, monto, canal, "Tienda", "Retail",
            pais, "Bogotá", estado, "00", fraude, score, "entrega.csv"]


def _escribir(ruta, columnas, filas):
    c = duckdb.connect()
    c.execute("create table t (" + ",".join(f'"{x}" varchar' for x in columnas) + ")")
    for f in filas:
        c.execute(f"insert into t values ({','.join(['?'] * len(columnas))})", f)
    c.execute(f"copy t to '{ruta}' (format parquet)")


def _bronce(carpeta, transacciones):
    carpeta.mkdir(exist_ok=True)
    _escribir(carpeta / "products.parquet", ["product_id", "customer_id", "product_type", "product_status", "currency",
                                              "product_number", "opening_date"],
              [["P1", "C1", "Debit", "Active", "USD", "1234567812345678", "2020-01-01"]])
    _escribir(carpeta / "customers.parquet", ["customer_id", "country", "segment", "customer_status", "detected_accent",
                                                "first_name"], [["C1", "Colombia", "Basic", "Active", "", "Ana María"]])
    _escribir(carpeta / "daily_exchange_rates.parquet", ["date", "source_currency", "target_currency", "exchange_rate"],
              [["2025-01-10", "COP", "USD", "0.00025"]])
    _escribir(carpeta / "service_agents.parquet", ["agent_id", "employee_code", "agent_type", "languages", "specialty",
                                                     "work_shift", "agent_status", "country_of_origin"],
              [["A1", "E1", "digital", "es", "Fraudes", "day", "Active", "Colombia"]])
    _escribir(carpeta / "transactions.parquet", COLUMNAS_TX, transacciones)


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(plata, "REPORTE", tmp_path / "calidad.json")      # nunca pisar el artefacto real
    return tmp_path / "bronce", tmp_path / "plata"


def _filas(plata_dir):
    c = duckdb.connect()
    return c.execute(f"select transaction_id, monto, fraude from read_parquet('{plata_dir}/transacciones/**/*.parquet', "
                     f"hive_partitioning = false) order by transaction_id").fetchall()


def _marca(plata_dir):
    return json.loads((plata_dir / "marca_de_agua.json").read_text())["process_date"]


def test_carga_completa_deduplica_y_fija_la_marca_de_agua(entorno):
    bronce, plata_dir = entorno
    _bronce(bronce, [_tx("T1", "2025-01-05", "2025-01-06", "10.00"),
                     _tx("T1", "2025-01-05", "2025-01-09", "12.00"),        # corrección posterior: gana
                     _tx("T2", "2025-02-03", "2025-02-04")])
    r = plata.construir(bronce, plata_dir)
    assert [(f[0], str(f[1])) for f in _filas(plata_dir)] == [("T1", "12.00"), ("T2", "10.00")]
    assert _marca(plata_dir) == "2025-02-04"
    assert r["meses_reprocesados"] == "todos"
    assert all(k["cumple"] or k["severidad"] == "advierte" for k in r["contratos"])


def test_sin_entregas_nuevas_no_reprocesa_nada(entorno):
    bronce, plata_dir = entorno
    _bronce(bronce, [_tx("T1", "2025-01-05", "2025-01-06")])
    plata.construir(bronce, plata_dir)
    antes = _filas(plata_dir)
    r = plata.construir(bronce, plata_dir)                                   # misma entrega otra vez
    assert r["meses_reprocesados"] == []
    assert _filas(plata_dir) == antes and _marca(plata_dir) == "2025-01-06"


def test_llegada_tardia_reprocesa_solo_su_mes_y_es_idempotente(entorno):
    bronce, plata_dir = entorno
    _bronce(bronce, [_tx("T1", "2025-01-05", "2025-01-06"), _tx("T2", "2025-02-03", "2025-02-04")])
    plata.construir(bronce, plata_dir)
    # segunda entrega: llega tarde una transacción de enero y una nueva de marzo
    _bronce(bronce, [_tx("T1", "2025-01-05", "2025-01-06"), _tx("T2", "2025-02-03", "2025-02-04"),
                     _tx("T3", "2025-01-20", "2025-03-02"), _tx("T4", "2025-03-01", "2025-03-02")])
    r = plata.construir(bronce, plata_dir)
    assert sorted(r["meses_reprocesados"]) == ["2025-01", "2025-03"]         # febrero no se toca
    assert [f[0] for f in _filas(plata_dir)] == ["T1", "T2", "T3", "T4"]
    assert _marca(plata_dir) == "2025-03-02"
    assert plata.construir(bronce, plata_dir)["meses_reprocesados"] == []    # idempotente


def test_la_incoherencia_se_marca_pero_el_dato_no_se_corrige(entorno):
    bronce, plata_dir = entorno
    _bronce(bronce, [_tx("T1", "2025-01-05", "2025-01-06", moneda="ARS", pais="México")])   # ARS en México
    r = plata.construir(bronce, plata_dir)
    moneda = next(k for k in r["contratos"] if k["contrato"].startswith("moneda coherente"))
    assert moneda["incumplen"] == 1 and moneda["severidad"] == "advierte"
    assert len(_filas(plata_dir)) == 1                                       # la fila sigue ahí, sin corregir


def test_un_contrato_que_bloquea_detiene_la_carga(entorno):
    bronce, plata_dir = entorno
    _bronce(bronce, [_tx("T1", "2025-01-05", "2025-01-06", score="150")])    # fraud_score fuera de [0, 100]
    with pytest.raises(RuntimeError, match="fraud_score"):
        plata.construir(bronce, plata_dir)
