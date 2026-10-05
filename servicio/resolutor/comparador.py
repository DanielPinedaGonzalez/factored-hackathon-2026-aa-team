"""A3b — Comparador de descripciones (ARQUITECTURA §5.1, CONTRATOS A3b).

El Resolutor (A3) encuentra por código los movimientos que coinciden con el monto y la fecha. El Comparador decide
por el sentido cuáles corresponden a cómo los describió el cliente: el comercio o el tipo de operación, con sus
palabras. El modelo solo elige alias de una lista cerrada de descripciones reales; el código valida cada alias y el
cliente confirma el movimiento antes de cualquier acción. El modelo nunca ve IDs, montos ni fechas.

Sin modelo, o con dos salidas inválidas seguidas, no se filtra: el cliente elige entre los candidatos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from servicio.llm.cliente import Modelo, ModeloNoDisponible, RespuestaModelo, hash_texto
from servicio.redactor import formato

RUTA_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "comparador.md"
_LINEA = re.compile(r"^\s*(?:[-*•]\s*)?\**COINCIDEN\**\s*:\s*\**\s*(.*)$", re.I | re.M)


class SalidaInvalida(Exception):
    """La salida no cumple el formato o nombra un alias fuera de la lista. El mensaje explica qué corregir."""


@dataclass
class Resultado:
    candidatos: list[dict] | None        # None: sin comparación (sin modelo o salida inválida); se muestran todos
    llamadas: list[RespuestaModelo] = field(default_factory=list)
    motivo: str | None = None
    hash_prompt: str | None = None


def descripcion_real(tx: dict, idioma: str) -> str:
    """Lo que el banco sabe del movimiento, en el idioma del cliente: su tipo y, si lo tiene, el comercio."""
    partes = [formato.movimiento(tx.get("tipo"), idioma) or tx.get("tipo"), tx.get("comercio")]
    return " · ".join(p for p in partes if p)


def agrupar(txs: list[dict], idioma: str) -> tuple[dict[str, str], dict[str, list[dict]]]:
    """Una opción por descripción distinta (D1, D2...), con los movimientos que la comparten."""
    opciones: dict[str, str] = {}
    grupos: dict[str, list[dict]] = {}
    por_texto: dict[str, str] = {}
    for tx in txs:
        texto = descripcion_real(tx, idioma)
        alias = por_texto.get(texto)
        if alias is None:
            alias = por_texto[texto] = f"D{len(opciones) + 1}"
            opciones[alias] = texto
            grupos[alias] = []
        grupos[alias].append(tx)
    return opciones, grupos


def leer(texto: str, validos: list[str]) -> list[str]:
    m = _LINEA.search(texto or "")
    if not m:
        raise SalidaInvalida("falta la línea COINCIDEN con los alias o ninguna")
    valor = m.group(1).strip().strip("`'\"").strip()
    if valor.lower() in ("ninguna", "ninguno"):
        return []
    elegidos = [a.strip().upper() for a in re.split(r"[,\s]+", valor) if a.strip()]
    fuera = [a for a in elegidos if a not in validos]
    if fuera or not elegidos:
        raise SalidaInvalida(f"alias fuera de la lista: {', '.join(fuera) or valor}. Alias válidos: {', '.join(validos)}, o ninguna")
    return list(dict.fromkeys(elegidos))


def mensaje_usuario(descripcion: str, opciones: dict[str, str], idioma: str) -> str:
    lineas = "\n".join(f"{a}: {t}" for a, t in opciones.items())
    return (f"IDIOMA: {idioma}\n\n<<<CLIENTE\n{descripcion}\nCLIENTE>>>\n\n"
            f"OPCIONES:\n<<<OPCIONES\n{lineas}\nOPCIONES>>>")


def comparar(modelo: Modelo | None, descripcion: str, txs: list[dict], idioma: str) -> Resultado:
    """Los movimientos de `txs` que corresponden a la descripción del cliente."""
    if modelo is None:
        return Resultado(None, motivo="sin modelo en este contexto")
    opciones, grupos = agrupar(txs, idioma)
    sistema = RUTA_PROMPT.read_text(encoding="utf-8")
    usuario = mensaje_usuario(descripcion, opciones, idioma)
    llamadas: list[RespuestaModelo] = []
    error = None
    for _ in range(2):
        pedido = usuario if error is None else f"{usuario}\n\nCorrige la salida anterior: {error}."
        try:
            r = modelo.completar(sistema, pedido, "comparar", max_tokens=300)
        except ModeloNoDisponible as e:
            return Resultado(None, llamadas, f"modelo no disponible: {e}", hash_texto(sistema))
        llamadas.append(r)
        try:
            elegidos = leer(r.texto, list(opciones))
        except SalidaInvalida as e:
            error = str(e)
            continue
        return Resultado([tx for a in elegidos for tx in grupos[a]], llamadas, None, hash_texto(sistema))
    return Resultado(None, llamadas, f"salida inválida dos veces: {error}", hash_texto(sistema))
