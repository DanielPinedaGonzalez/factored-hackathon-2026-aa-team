"""Formato de los valores que reemplazan a los marcadores (ARQUITECTURA §8.5): según idioma y moneda."""
from __future__ import annotations

import functools
from datetime import date, datetime
from pathlib import Path

import yaml
from contratos.idiomas import normalizar


@functools.lru_cache(maxsize=1)
def _cfg() -> dict:
    return yaml.safe_load((Path(__file__).resolve().parents[2] / "config" / "formatos.yaml").read_text(encoding="utf-8"))


def monto(valor: float | None, moneda: str | None) -> str:
    if valor is None:
        return "—"
    f = _cfg()["moneda"].get((moneda or "USD").upper(), _cfg()["moneda"]["USD"])
    entero, _, dec = f"{abs(valor):,.{f['cifras']}f}".partition(".")
    entero = entero.replace(",", f["miles"])
    texto = entero + (f["decimales"] + dec if f["cifras"] else "")
    return f"{'-' if valor < 0 else ''}{f['simbolo']} {texto}{f['sufijo']}"


def fecha(d: date | datetime | str | None, idioma: str) -> str:
    if d is None:
        return "—"
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    idioma = normalizar(idioma)
    mes = _cfg()["meses"][idioma][d.month - 1]
    return _cfg()["fecha"][idioma].format(d=d.day, mes=mes, a=d.year)


def producto(tipo: str | None, ultimos4: str | None, idioma: str) -> str:
    idioma = normalizar(idioma)
    nombre = _cfg()["tipos_producto"][idioma].get(tipo or "", tipo or "")
    return f"{nombre} •••• {ultimos4}" if ultimos4 else nombre


def movimiento(tipo: str | None, idioma: str) -> str | None:
    """El nombre del tipo de movimiento en el idioma del cliente; None si el tipo no tiene nombre configurado."""
    idioma = normalizar(idioma)
    return _cfg()["tipos_movimiento"][idioma].get(tipo or "")
