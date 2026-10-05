"""A16 — Asistencia al asesor (PROCESOS §P2.8, CONTRATOS A16).

La guía del caso la calcula el código desde los motivos del traspaso y la decisión de la política; los artículos
sugeridos salen de los motivos; el borrador, solo a pedido, lo escribe el Redactor con la misma información segura
que usaría para el cliente (sin la señal de riesgo ni el camino interno) y pasa por el verificador. Nunca se envía
solo: el envío es una acción del asesor y queda con su origen.
"""
from __future__ import annotations

import functools
from pathlib import Path

import yaml

from contratos.modelos import EstadoConversacion
from servicio.llm.cliente import Modelo
from servicio.redactor.estado_comunicable import Constructor
from servicio.redactor.redactor import RedaccionFallida, redactar


@functools.lru_cache(maxsize=1)
def _guias() -> dict:
    return yaml.safe_load((Path(__file__).resolve().parents[2] / "config" / "guias_asesor.yaml").read_text(encoding="utf-8"))


def guia(paquete: dict) -> dict:
    """Pasos y artículos por motivo, en el orden de los motivos del paquete. Sin modelo."""
    g = _guias()
    pasos, articulos = [], []
    for m in paquete.get("motivo_traspaso", []):
        d = g["motivos"].get(m, {})
        pasos += [p for p in d.get("pasos", []) if p not in pasos]
        articulos += [a for a in d.get("articulos", []) if a not in articulos]
    if not paquete.get("identidad_verificada", True):
        pasos.insert(0, g["identidad_no_verificada"])
    return {"pasos": pasos or g["por_defecto"], "articulos": articulos}


def borrador(modelo: Modelo, estado: EstadoConversacion, paquete: dict, idioma: str) -> dict:
    ec = Constructor(idioma)
    hechas = [a for a in paquete.get("acciones_realizadas", []) if a.get("estado", "completada") == "completada"]
    for a in hechas:                 # una acción en estado desconocido no se comunica como hecha (INV-VERIFICA)
        valores = {"CASO": a["resultado"]["numero"]} if a["resultado"].get("numero") else None
        ec.resultado("accion_completada", a["accion"], valores)
    ec.preguntar("otra_ayuda")        # quien escribe ya es la persona: el borrador no ofrece una
    completadas = {a["accion"] for a in hechas}
    try:
        r = redactar(modelo, estado, ec.construir(), idioma, completadas, None)
    except RedaccionFallida as e:
        return {"ok": False, "motivo": str(e), "llamadas": []}
    from servicio.verificacion.redaccion import reemplazar
    return {"ok": True, "texto": reemplazar(r.redaccion.texto, ec.construir()), "origen_prompt": r.hash_prompt,
            "llamadas": [{"modelo": x.modelo, "proveedor": x.proveedor, "request_id": x.request_id,
                          "tokens": x.tokens_entrada + x.tokens_salida, "latencia_ms": round(x.latencia_ms, 1)} for x in r.llamadas]}
