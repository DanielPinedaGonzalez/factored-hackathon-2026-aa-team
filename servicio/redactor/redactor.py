"""A8 — Redactor (CONTRATOS A8) con su verificación (A9).

Recibe el estado comunicable (sin la señal de riesgo ni el camino interno), la conversación y el idioma. Si la
verificación falla: una re-redacción con el error; luego el borrador del Intérprete si pasa la misma verificación;
si no, el caso pasa a una persona. Nunca una frase fija para tapar el fallo (ARQUITECTURA §8.4).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from contratos import catalogo
from contratos.modelos import EstadoComunicable, EstadoConversacion, Redaccion
from servicio.interprete.interprete import conversacion_para_modelo
from servicio.llm.cliente import Modelo, ModeloNoDisponible, RespuestaModelo, hash_texto
from servicio.redactor.estado_comunicable import para_modelo
from servicio.verificacion.redaccion import verificar
from contratos.idiomas import declarado, normalizar

RUTA_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "redactor.md"
_CLAVES = ("IDIOMA", "ACCIONES_AFIRMADAS", "CITA", "SUFICIENCIA", "RESUMEN_HUMANO", "SALUDO", "TEXTO")


class RedaccionFallida(Exception):
    def __init__(self, motivo: str, llamadas: list[RespuestaModelo]):
        super().__init__(motivo)
        self.llamadas = llamadas


def prompt_sistema(ec: EstadoComunicable | None = None) -> str:
    """Solo los hechos y preguntas que trae este turno (el contexto es finito: lo mínimo de alta señal)."""
    cat = catalogo.cargar()
    todos = {**cat["hechos"], **cat["preguntas"]}
    if ec is not None:
        usados = set()
        for e in ec.elementos:
            c = json.loads(e.contenido)
            usados |= {c.get("hecho"), c.get("pregunta")}
        todos = {k: v for k, v in todos.items() if k in usados}
    hechos = "\n".join(f"- {k}: {v}" for k, v in todos.items()) or "- (ninguno)"
    return RUTA_PROMPT.read_text(encoding="utf-8").replace("{{HECHOS}}", hechos)


def leer(texto: str, idioma_defecto: str) -> Redaccion:
    from servicio.llm.formato_salida import normalizar
    texto = normalizar(texto)
    datos: dict = {}
    lineas = [l for l in texto.replace("\r", "").split("\n") if not l.strip().startswith("```")]
    for i, linea in enumerate(lineas):
        m = re.match(r"^\s*\**([A-Z_]+)\**\s*:\s*(.*)$", linea)
        if not m or m.group(1) not in _CLAVES:
            continue
        clave, valor = m.group(1), m.group(2).strip()
        if clave == "TEXTO":
            datos["texto"] = "\n".join([valor] + lineas[i + 1:]).strip()
            break
        datos[clave] = valor
    # Solo cuentan los códigos de acción del catálogo: un hecho listado ahí no afirma ninguna acción.
    acciones_catalogo = set(catalogo.cargar()["acciones"])
    acciones = [a.strip() for a in datos.get("ACCIONES_AFIRMADAS", "").split(",") if a.strip() in acciones_catalogo]
    cita = datos.get("CITA", "").strip()
    suf = datos.get("SUFICIENCIA", "").strip().lower()
    idioma = datos.get("IDIOMA", idioma_defecto).strip().lower()[:2]
    return Redaccion(texto=datos.get("texto", ""), acciones_afirmadas=acciones, saludo=(datos.get("SALUDO") or "").strip() or None,
                     idioma=declarado(idioma),
                     resumen_para_humano=datos.get("RESUMEN_HUMANO") or None,
                     cita_articulo=None if cita.lower() in ("", "ninguna", "ninguno") else cita,
                     suficiencia=suf if suf in ("completa", "parcial", "insuficiente", "ambigua") else None)


@dataclass
class ResultadoRedaccion:
    redaccion: Redaccion
    llamadas: list[RespuestaModelo]
    origen: str          # redactor | re_redaccion | borrador_interprete
    errores: list[str]
    hash_prompt: str


def redactar(modelo: Modelo, estado: EstadoConversacion, ec: EstadoComunicable, idioma: str,
             completadas: set[str], borrador: str | None, momento: str | None = None) -> ResultadoRedaccion:
    """`momento`: el momento del día en la zona del cliente; llega solo en el primer mensaje, que lleva saludo."""
    sistema = prompt_sistema(ec)
    usuario = (f"IDIOMA: {idioma if idioma in ('es', 'pt') else 'es'}\nPREFERENCIA: {', '.join(ec.preferencia) or 'ninguna'}\n"
               + (f"MOMENTO DEL DÍA DEL CLIENTE: {momento}\n" if momento else "") +
               f"ACCIONES VERIFICADAS: {', '.join(sorted(completadas)) or 'ninguna'}\n\n"
               f"CONVERSACIÓN:\n{conversacion_para_modelo(estado)}\n\nESTADO COMUNICABLE:\n{para_modelo(ec)}")
    llamadas: list[RespuestaModelo] = []
    errores_todos: list[str] = []
    error = None
    for intento, origen in enumerate(("redactor", "re_redaccion")):
        pedido = usuario if error is None else f"{usuario}\n\nCorrige el texto anterior: {error}."
        try:
            r = modelo.completar(sistema, pedido, "redactar")
        except ModeloNoDisponible as e:
            raise RedaccionFallida(f"modelo no disponible: {e}", llamadas)
        llamadas.append(r)
        red = leer(r.texto, idioma)
        errores = verificar(red, ec, idioma, completadas, saludo_pedido=bool(momento))
        if not errores:
            return ResultadoRedaccion(red, llamadas, origen, errores_todos, hash_texto(sistema))
        error = "; ".join(errores)
        errores_todos += errores
    if borrador:
        red = Redaccion(texto=borrador, idioma=normalizar(idioma))
        if not verificar(red, ec, idioma, completadas) and not _debe_decir_algo(ec):
            return ResultadoRedaccion(red, llamadas, "borrador_interprete", errores_todos, hash_texto(sistema))
    raise RedaccionFallida(f"verificación fallida dos veces: {error}", llamadas)


def _debe_decir_algo(ec: EstadoComunicable) -> bool:
    """El borrador del Intérprete no conoce los hechos: solo sirve si el turno no trae nada que decir."""
    return any(e.clase in ("AFIRMAR", "EXACTO", "RESULTADO", "RESPONDER", "OFRECER") for e in ec.elementos)
