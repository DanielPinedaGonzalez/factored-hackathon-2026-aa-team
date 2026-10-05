"""Parámetros de operación (PROCESOS §P9): valores que decide el banco y se cambian sin tocar el código.

El valor inicial vive en `config/parametros_operacion.yaml`; el vigente, en `operacion.parametros`, y solo lo cambia un
supervisor con motivo (función de la base, evento de solo agregar). Se leen con la conexión del turno, así que un
cambio rige desde el turno siguiente, sin reiniciar nada.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import yaml

RUTA = Path(__file__).resolve().parents[2] / "config" / "parametros_operacion.yaml"


class ValorInvalido(ValueError):
    """El valor pedido está fuera del rango declarado del parámetro."""


@functools.lru_cache(maxsize=1)
def catalogo() -> dict:
    return yaml.safe_load(RUTA.read_text(encoding="utf-8"))


def leer(c, clave: str) -> int:
    fila = c.execute("select valor from operacion.parametros where clave = %s", (clave,)).fetchone()
    return int(fila["valor"]) if fila else int(catalogo()[clave]["inicial"])


def listar(c) -> list[dict]:
    """Cada parámetro con su valor vigente, de dónde sale y su último cambio."""
    filas = {f["clave"]: f for f in c.execute("select * from operacion.parametros").fetchall()}
    salida = []
    for clave, d in catalogo().items():
        f = filas.get(clave)
        salida.append({"clave": clave, "valor": int(f["valor"]) if f else int(d["inicial"]), "inicial": d["inicial"],
                       "minimo": d["minimo"], "maximo": d["maximo"], "unidad": d["unidad"], "descripcion": d["descripcion"],
                       "origen": "operacion" if f else "configuracion",
                       "cambiado_por": f and f["actualizado_por"], "cambiado_en": f and f["actualizado_en"].isoformat()})
    return salida


def cambiar(c, clave: str, valor: int, autor: str, motivo: str) -> None:
    d = catalogo().get(clave)
    if d is None:
        raise ValorInvalido(f"parámetro desconocido: {clave}")
    if not (d["minimo"] <= valor <= d["maximo"]):
        raise ValorInvalido(f"{clave} debe estar entre {d['minimo']} y {d['maximo']}")
    if not (motivo or "").strip():
        raise ValorInvalido("el cambio necesita un motivo")
    c.execute("select operacion.cambiar_parametro(%s, %s, %s, %s)", (clave, json.dumps(valor), autor, motivo.strip()))
