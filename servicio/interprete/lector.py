"""Lector tolerante de la salida del Intérprete (ARQUITECTURA D-13).

Esqueleto adaptado de un sistema propio del autor: una línea por campo, tolerante al formato (mayúsculas, viñetas,
bloques de código) y estricto con el contenido: todo valor se valida contra el catálogo único y el esquema cerrado.
Un campo desconocido o un valor fuera del catálogo es un error: el Intérprete reintenta una vez con el error.
"""
from __future__ import annotations

import re
import unicodedata

from pydantic import ValidationError

from contratos import catalogo
from contratos.modelos import CargoReferido, Comando, Cuando, Interpretacion, Monto
from servicio.resolutor.calendario import expresion_de_cuando


class SalidaInvalida(Exception):
    """La salida no cumple la gramática o el catálogo. El mensaje explica qué corregir."""


_CAMPOS = {"IDIOMA", "COMANDO", "RECONOCE", "TIPO_DISPUTA", "EVIDENCIA_TIPO", "SENAL", "SECRETO", "CARGO", "MONTO",
           "MONEDA", "APROXIMADO", "CUANDO", "DESCRIPCION", "FIN_CARGO", "BORRADOR"}
_EN_CARGO = {"MONTO", "MONEDA", "APROXIMADO", "CUANDO", "DESCRIPCION"}
_MODIFICADORES = {"MONEDA", "APROXIMADO"}      # matizan un monto; sueltos no llevan información
_LINEA = re.compile(r"^\s*(?:[-*•]\s*)?\**([A-Za-zÁÉÍÓÚÑ_]+)\**\s*:\s*(.*)$")


def _distancia(a: str, b: str) -> int:
    fila = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        previa, fila[0] = fila[0], i
        for j, cb in enumerate(b, 1):
            previa, fila[j] = fila[j], min(fila[j] + 1, fila[j - 1] + 1, previa + (ca != cb))
    return fila[-1]


def _del_catalogo(valor: str, validos, campo: str) -> str:
    """Tolerancia de formato sobre un catálogo cerrado: acepta una variante mal escrita solo si hay un único valor
    válido a dos letras o menos. No interpreta al cliente: corrige la ortografía de un código."""
    valor = valor.strip().strip("`'\"").lower()
    validos = list(validos)
    if valor in validos:
        return valor
    cercanos = [v for v in validos if _distancia(valor, v) <= 2]
    if len(cercanos) == 1:
        return cercanos[0]
    raise SalidaInvalida(f"{campo} fuera del catálogo: '{valor}'. Valores válidos: {', '.join(validos)}")


def _numero(v: str) -> float:
    limpio = re.sub(r"[^\d.,-]", "", v)
    if limpio.count(",") and limpio.count("."):
        limpio = limpio.replace(".", "").replace(",", ".") if limpio.rfind(",") > limpio.rfind(".") else limpio.replace(",", "")
    elif limpio.count(",") == 1 and len(limpio.split(",")[1]) != 3:
        limpio = limpio.replace(",", ".")
    else:
        limpio = limpio.replace(",", "")
        if limpio.count(".") > 1 or (limpio.count(".") == 1 and len(limpio.split(".")[1]) == 3):
            limpio = limpio.replace(".", "")
    return float(limpio)


def _validar_comando(nombre: str, args: list[str]) -> Comando:
    cat = catalogo.cargar()
    nombre = _del_catalogo(nombre, cat["comandos"], "COMANDO")
    if nombre == "iniciar":
        if not args:
            raise SalidaInvalida(f"iniciar necesita servicio.intencion. Válidas: {', '.join(sorted(catalogo.intenciones()))}")
        args[0] = _del_catalogo(args[0], sorted(catalogo.intenciones()), "iniciar")
    if nombre in ("dar_dato", "corregir"):
        if len(args) < 2:
            raise SalidaInvalida(f"{nombre} necesita 'campo | valor'; recibido {args}")
        args[0] = _del_catalogo(args[0], cat["campos"], "campo")
    if nombre == "elegir" and not args:
        raise SalidaInvalida("elegir necesita el alias mostrado")
    return Comando(nombre=nombre, args=args)


def leer(texto: str) -> Interpretacion:
    from servicio.llm.formato_salida import normalizar
    texto = normalizar(texto)
    cat = catalogo.cargar()
    lineas = [l for l in texto.replace("\r", "").split("\n") if l.strip() and not l.strip().startswith("```")]
    datos: dict = {"comandos": [], "cargos_referidos": [], "senales_riesgo": [], "datos_secretos": []}
    cargo: dict | None = None
    implicito = False       # el bloque lo abrió el lector porque el modelo dio un dato del cargo sin abrirlo
    borrador: list[str] | None = None

    for linea in lineas:
        if borrador is not None:
            borrador.append(linea.strip())
            continue
        m = _LINEA.match(linea)
        clave = m.group(1).upper() if m else linea.strip().upper().strip("*")
        clave = "".join(c for c in unicodedata.normalize("NFD", clave) if unicodedata.category(c) != "Mn")   # DESCRIPCIÓN
        valor = m.group(2).strip() if m else ""
        if clave not in _CAMPOS:
            raise SalidaInvalida(f"línea fuera del formato: '{linea.strip()[:60]}'")
        if clave == "FIN_CARGO":
            if cargo is None:
                raise SalidaInvalida("FIN_CARGO sin CARGO")
            datos["cargos_referidos"].append(cargo)
            cargo, implicito = None, False
            continue
        if clave in _EN_CARGO:
            if cargo is None:
                if clave in _MODIFICADORES:
                    continue        # «aproximado» o «moneda» sin cargo ni monto no dicen nada: se ignoran en vez de perder el turno
                if clave not in ("CUANDO", "DESCRIPCION") or not datos["cargos_referidos"]:
                    raise SalidaInvalida(f"{clave} fuera de un bloque CARGO")
                # El cuándo o la descripción escritos DESPUÉS de cerrar un cargo ya declarado (visto en producción): el modelo entendió el mensaje y se descuidó con
                # el formato; el dato pertenece a ese cargo. Sin ningún cargo declarado sigue siendo un error (se atribuiría a un cargo que nadie mencionó), igual que un monto suelto.
                cargo = datos["cargos_referidos"].pop()
                implicito = True
            if not valor:
                continue
            if clave == "MONTO":
                try:
                    cargo["monto"] = {"valor": _numero(valor), **cargo.get("monto", {})}
                except ValueError:
                    raise SalidaInvalida(f"MONTO no es un número: '{valor}'")
            elif clave == "MONEDA":
                cargo.setdefault("monto", {})["moneda"] = valor.upper()[:3]
            elif clave == "APROXIMADO":
                cargo.setdefault("monto", {})["aproximado"] = valor.lower().startswith("s")
            elif clave == "CUANDO":
                # La misma regla que el campo suelto: con su tipo, o un valor del vocabulario del calendario. Una fecha que el calendario no ubica no
                # pierde el turno: pasa como no entendida y el resolutor busca sin ella y lo dice (`fecha_no_entendida`), igual que con el campo suelto.
                tipo, expresion = expresion_de_cuando(valor) or ("relativa", valor)
                cargo["cuando"] = {"tipo": tipo, "valor": expresion.strip()}
            elif clave == "DESCRIPCION":
                cargo["descripcion"] = valor
            continue
        if cargo is not None:
            if not implicito:
                raise SalidaInvalida(f"falta FIN_CARGO antes de {clave}")
            datos["cargos_referidos"].append(cargo)      # el bloque abierto por el lector termina donde empieza otro campo
            cargo, implicito = None, False
        if clave == "CARGO":
            cargo = {"refiere_a": valor or "nuevo"}
        elif clave == "IDIOMA":
            datos["idioma"] = valor.lower()
        elif clave == "COMANDO":
            partes = [p.strip() for p in valor.split("|")]
            primera = partes[0].split(maxsplit=1)
            nombre, args = primera[0].lower(), ([primera[1].strip()] if len(primera) > 1 else []) + [p for p in partes[1:] if p]
            datos["comandos"].append(_validar_comando(nombre, args))
        elif clave == "RECONOCE":
            datos["reconoce"] = valor.lower()
        elif clave == "TIPO_DISPUTA":
            datos["tipo_disputa_propuesto"] = _del_catalogo(valor, cat["tipos_disputa"], "TIPO_DISPUTA")
        elif clave == "EVIDENCIA_TIPO":
            datos["tipo_evidencia"] = valor
        elif clave == "SENAL":
            datos["senales_riesgo"].append(_del_catalogo(valor, cat["senales_riesgo"], "SENAL"))
        elif clave == "SECRETO":
            if valor:
                datos["datos_secretos"].append(valor)
        elif clave == "BORRADOR":
            borrador = [valor] if valor else []
    if cargo is not None:
        datos["cargos_referidos"].append(cargo)       # tolera un FIN_CARGO olvidado al final
    if borrador is not None:
        datos["borrador_respuesta"] = "\n".join(borrador).strip()
    try:
        interp = Interpretacion(**{**datos, "cargos_referidos": [CargoReferido(
            refiere_a=c.get("refiere_a", "nuevo"),
            monto=Monto(**c["monto"]) if c.get("monto", {}).get("valor") is not None else None,
            cuando=Cuando(**c["cuando"]) if c.get("cuando") else None,
            descripcion=c.get("descripcion")) for c in datos["cargos_referidos"]]})
    except ValidationError as e:
        raise SalidaInvalida(f"esquema: {e.errors()[0]['loc']} {e.errors()[0]['msg']}")
    return interp
