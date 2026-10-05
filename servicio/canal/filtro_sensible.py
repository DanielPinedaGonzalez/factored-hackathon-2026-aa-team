"""A17 — Filtro de datos sensibles (ARQUITECTURA §8.10, CONTRATOS A17).

Borra números de tarjeta por su forma (13 a 19 dígitos con dígito de control de Luhn), antes de guardar el turno o
llamar a un modelo. No interpreta lo que el cliente quiere decir. También borra los tramos que el Intérprete marcó
como secretos (claves, PIN, códigos): la IA declara, Python borra.
"""
from __future__ import annotations

import re

MARCA_TARJETA = "[tarjeta borrada]"
MARCA_SECRETO = "[dato secreto borrado]"
# Secuencias de dígitos con espacios o guiones entre grupos; los bordes no pueden ser dígitos.
_CANDIDATO = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _luhn(digitos: str) -> bool:
    total = 0
    for i, d in enumerate(reversed(digitos)):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def borrar_tarjetas(texto: str) -> tuple[str, bool]:
    """Devuelve (texto sin números de tarjeta, hubo_borrado)."""
    hubo = False

    def reemplazo(m: re.Match) -> str:
        nonlocal hubo
        digitos = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digitos) <= 19 and _luhn(digitos):
            hubo = True
            return MARCA_TARJETA
        return m.group(0)

    return _CANDIDATO.sub(reemplazo, texto), hubo


def borrar_secretos(texto: str, tramos: list[str]) -> tuple[str, int]:
    """Borra cada tramo literal marcado por el Intérprete. Devuelve (texto, cuántos se borraron)."""
    borrados = 0
    for tramo in sorted({t for t in tramos if t and t.strip()}, key=len, reverse=True):
        if tramo in texto:
            texto = texto.replace(tramo, MARCA_SECRETO)
            borrados += 1
    return texto, borrados
