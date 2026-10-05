"""Idiomas que el sistema atiende: la única fuente (ARQUITECTURA §8.4).

Agregar un idioma es agregarlo aquí y dar su contenido en `config/formatos.yaml`, `config/textos_legales.yaml` y los
artículos de `conocimiento/`; una prueba candado vigila que ningún otro archivo repita la lista.
"""
from __future__ import annotations

IDIOMAS: tuple[str, ...] = ("es", "pt")
IDIOMA_BASE = "es"          # al que se vuelve cuando el idioma del cliente no está soportado
IDIOMA_OTRO = "otro"        # lo que se declara cuando un texto viene en un idioma no soportado


def es_soportado(idioma: str | None) -> bool:
    return idioma in IDIOMAS


def normalizar(idioma: str | None) -> str:
    """El idioma con el que se atiende: el del cliente si está soportado, el base si no."""
    return idioma if es_soportado(idioma) else IDIOMA_BASE


def declarado(idioma: str | None) -> str:
    """El idioma que un texto declara: nunca se fuerza a uno soportado, para que la verificación vea la diferencia."""
    return idioma if es_soportado(idioma) else IDIOMA_OTRO
