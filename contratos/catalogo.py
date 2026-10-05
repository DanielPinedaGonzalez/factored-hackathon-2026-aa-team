"""Carga el catálogo único (ARQUITECTURA D-14) y lo expone con validadores. Nada lo duplica."""
from __future__ import annotations

import functools
import hashlib
from pathlib import Path

import yaml

RUTA = Path(__file__).with_name("catalogo.yaml")
ORDEN_HABILIDAD = {"fraude": 3, "reclamos": 2, "general": 1}


@functools.lru_cache(maxsize=1)
def cargar() -> dict:
    return yaml.safe_load(RUTA.read_text(encoding="utf-8"))


def hash_catalogo() -> str:
    return hashlib.sha256(RUTA.read_bytes()).hexdigest()[:12]


def intenciones() -> set[str]:
    """Todas las intenciones como 'servicio.intencion'."""
    c = cargar()
    return {f"{s}.{i}" for s, d in c["servicios"].items() for i in d["intenciones"]}


def habilidad_de(motivos: list[str]) -> str:
    """La habilidad más exigente entre los motivos (PROCESOS §P2.2)."""
    tabla = cargar()["motivos_traspaso"]
    habilidades = [tabla[m] for m in motivos if m in tabla] or ["general"]
    return max(habilidades, key=ORDEN_HABILIDAD.__getitem__)
