"""A3 — Resolutor de referencias (CONTRATOS A3).

Convierte un `CargoReferido` (lo que el cliente dijo, estructurado por el Intérprete) en candidatos reales del
cliente autenticado, por lo que se calcula: la fecha y el monto. Las fechas se calculan solo aquí; un monto aproximado
solo propone (±10%); con 2 o más candidatos nunca elige. La descripción del cliente (comercio o tipo de operación) la
compara por el sentido el Comparador (A3b) sobre estos candidatos. No consulta la base: recibe las transacciones que
el orquestador leyó con la herramienta.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from contratos.modelos import CargoReferido
from servicio.resolutor.calendario import rango_de_cuando

TOLERANCIA_APROXIMADO = 0.10
TOLERANCIA_EXACTO = 0.01
VENTANA_SIN_FECHA_DIAS = 30
MAX_LISTABLES = 5


@dataclass
class Resultado:
    candidatos: list[dict]
    clase: str            # "0" | "1" | "2-5" | ">5"
    rango: tuple[date, date] | None
    fecha_no_entendida: bool = False
    posterior_a_datos: bool = False


def _clase(n: int) -> str:
    if n == 0:
        return "0"
    if n == 1:
        return "1"
    return "2-5" if n <= MAX_LISTABLES else ">5"


def _monto_coincide(tx: dict, cargo: CargoReferido) -> bool:
    m = cargo.monto
    if m is None:
        return True
    tol = TOLERANCIA_APROXIMADO if m.aproximado else TOLERANCIA_EXACTO
    moneda = (m.moneda or "").upper()
    # Un monto dicho viene redondeado: la precisión con que se dijo también es tolerancia (23 → ±1; 180000 → ±500).
    redondeo = 500 if m.valor >= 1000 and m.valor % 1000 == 0 else 50 if m.valor >= 100 and m.valor % 100 == 0 else 1.0
    if moneda == "USD" and tx.get("moneda") != "USD":
        base = tx.get("amount_usd")
    else:
        base = tx.get("monto")
    if base is None:
        return False
    return abs(float(base) - m.valor) <= max(tol * max(m.valor, 1.0), redondeo)


def resolver(cargo: CargoReferido, transacciones: list[dict], hoy: date, data_as_of: date, reloj=None) -> Resultado:
    """`transacciones`: del titular del token, con claves fecha (date), monto, moneda, amount_usd, comercio, estado.
    `hoy` está en el marco de los datos. Lo que dijo el cliente se interpreta en su fecha real (`reloj`) y se lleva
    al marco de los datos."""
    rango = None
    fecha_no_entendida = False
    if cargo.cuando is not None:
        if reloj is not None:
            local = rango_de_cuando(cargo.cuando.tipo, cargo.cuando.valor, reloj.hoy_local, reloj.ahora_local)
            rango = (reloj.a_datos(local[0]), reloj.a_datos(local[1])) if local else None
        else:
            rango = rango_de_cuando(cargo.cuando.tipo, cargo.cuando.valor, hoy)
        fecha_no_entendida = rango is None
    if rango is None:
        rango = (hoy - timedelta(days=VENTANA_SIN_FECHA_DIAS), hoy)
    posterior = rango[0] > data_as_of

    elegidos = []
    for tx in transacciones:
        if not (rango[0] <= tx["fecha"] <= rango[1]):
            continue
        if not _monto_coincide(tx, cargo):
            continue
        elegidos.append(tx)
    elegidos.sort(key=lambda t: (t["fecha"], t.get("hora", "")), reverse=True)   # la recencia ordena, no decide
    return Resultado(elegidos, _clase(len(elegidos)), rango, fecha_no_entendida, posterior)
