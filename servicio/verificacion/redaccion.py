"""A9 — Verificador de redacción (CONTRATOS A9): determinista, sobre la estructura, sin listas de palabras.

Comprueba: marcadores obligatorios presentes, ningún marcador desconocido ni incompleto, ningún dígito fuera de los marcadores,
acciones afirmadas ⊆ acciones completadas, idioma declarado = idioma del cliente = idioma detectado por un modelo
estadístico pequeño, y la cita del artículo = la entregada.
"""
from __future__ import annotations

import re

import langid

from contratos.modelos import EstadoComunicable, Redaccion
from servicio.redactor.estado_comunicable import marcadores, obligatorios
from contratos.idiomas import normalizar

langid.set_languages(["es", "pt", "en"])
MARCADOR = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
MINIMO_PARA_DETECTAR = 25        # con menos caracteres el identificador no es confiable y no se exige


def _codigos_internos() -> re.Pattern:
    from contratos import catalogo
    cat = catalogo.cargar()
    codigos = list(cat["clases_estado_comunicable"]) + [k for k in {**cat["hechos"], **cat["preguntas"]} if "_" in k]
    return re.compile(r"\b(" + "|".join(map(re.escape, codigos)) + r")\b")


_CODIGOS = _codigos_internos()


def _aliases(contenido: str) -> set[str]:
    import json
    c = json.loads(contenido)
    valores = c.get("sobre")
    valores = valores if isinstance(valores, list) else [valores]
    return {v for v in valores if isinstance(v, str) and re.fullmatch(r"[CP]\d{1,2}", v)}


def detectar_idioma(texto: str) -> str | None:
    limpio = MARCADOR.sub(" ", texto)
    if len(limpio.strip()) < MINIMO_PARA_DETECTAR:
        return None
    return langid.classify(limpio)[0]


def verificar(r: Redaccion, ec: EstadoComunicable, idioma_cliente: str, completadas: set[str],
              saludo_pedido: bool = False) -> list[str]:
    errores = []
    if saludo_pedido and not r.saludo:
        errores.append("escribe la línea SALUDO para el momento del día del cliente")
    if r.saludo and (re.search(r"\d", r.saludo) or MARCADOR.search(r.saludo)):
        errores.append("escribe el SALUDO solo con palabras")
    usados = set(MARCADOR.findall(r.texto))
    disponibles = set(marcadores(ec))
    if faltan := obligatorios(ec) - usados:
        errores.append(f"incluye los marcadores obligatorios {sorted(faltan)}")
    if extra := usados - disponibles:
        errores.append(f"usa solo marcadores de las listas del estado comunicable; estos son ajenos: {sorted(extra)}")
    if re.search(r"[{}]", MARCADOR.sub("", f"{r.saludo or ''} {r.texto}")):
        errores.append("escribe cada marcador completo, con su llave de apertura y su llave de cierre")
    # Los alias mostrados al cliente (C1, P2) son rótulos de opciones, no cifras.
    aliases = {a for e in ec.elementos for a in _aliases(e.contenido)}
    sin_alias = re.sub(r"\b(" + "|".join(sorted(aliases)) + r")\b", "", MARCADOR.sub("", r.texto)) if aliases else MARCADOR.sub("", r.texto)
    if re.search(r"\d", sin_alias):
        errores.append("pon cada cifra dentro de su marcador")
    if afirmadas := set(r.acciones_afirmadas) - completadas:
        errores.append(f"presenta como propuesta estas acciones, que aún están sin completar: {sorted(afirmadas)}")
    esperado = normalizar(idioma_cliente)
    if r.idioma != esperado:
        errores.append(f"escribe y declara el idioma del cliente: {esperado}")
    detectado = detectar_idioma(f"{r.saludo or ''} {r.texto}")
    if detectado and detectado != esperado:
        errores.append(f"escribe el texto en {esperado} (se detectó {detectado})")
    if ec.articulo:
        cita = f"{ec.articulo['id']}@{ec.articulo['version']}"
        if r.cita_articulo not in (cita, None) or (r.suficiencia in ("completa", "parcial") and r.cita_articulo != cita):
            errores.append(f"cita exactamente {cita}")
    if not r.texto.strip():
        errores.append("escribe el mensaje para el cliente en la línea TEXTO")
    if _CODIGOS.search(f"{r.saludo or ''} {r.texto}"):
        errores.append("redacta el mensaje para el cliente con palabras propias, en lugar de los códigos internos del estado comunicable")
    return errores


def reemplazar(texto: str, ec: EstadoComunicable) -> str:
    valores = marcadores(ec)
    return MARCADOR.sub(lambda m: valores.get(m.group(1), m.group(0)), texto)
