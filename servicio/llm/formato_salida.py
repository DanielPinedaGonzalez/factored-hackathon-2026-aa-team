"""Normaliza la salida de un modelo antes de leerla: algunos modelos escriben sus marcas internas de canal
(`<|message|>`, `<|channel|>`) donde va el separador. Es tolerancia de formato, no interpretación."""
import re

_MARCA = re.compile(r"<\|[a-z_]+\|>")


def normalizar(texto: str) -> str:
    texto = re.sub(r"(^|\n)([A-Z_]+)\s*(?:<\|[a-z_]+\|>\s*)+", lambda m: f"{m.group(1)}{m.group(2)}: ", texto)
    return _MARCA.sub(" ", texto)
