"""Verifica los artículos de conocimiento/ contra docs/GOBERNANZA_DATOS_IA.md §11 y regenera su índice.

Uso: python scripts/verificar_conocimiento.py   (sale con error si algo no cumple)
"""
import glob
import re
import sys

import yaml

RAIZ = __file__.rsplit("/scripts/", 1)[0]
OBLIGATORIOS = ["id", "titulo", "version", "estado", "audiencia", "paises", "protocolo", "criticidad", "autor",
                "aprobado_por", "vigente_desde", "revisar_antes_de", "fuentes", "casos"]
ESTADOS = {"pendiente_aprobacion", "publicado", "reemplazado", "rechazado", "inactivo"}
REFERENCIA = re.compile(r"^(politica|config)\.[a-z0-9_.]+$")


def articulos():
    for f in sorted(glob.glob(f"{RAIZ}/conocimiento/*/*.md")):
        if f.endswith("README.md"):
            continue
        texto = open(f, encoding="utf-8").read()
        _, cabecera, cuerpo = texto.split("---\n", 2)
        yield f, yaml.safe_load(cabecera), cuerpo


def verificar():
    claves = {r["clave"] for r in yaml.safe_load(open(f"{RAIZ}/docs/bibliografia/referencias.yaml", encoding="utf-8"))}
    casos = set(re.findall(r"^\| ([A-F]\d+) \|", open(f"{RAIZ}/docs/CASOS.md", encoding="utf-8").read(), re.M))
    errores, filas = [], {"publico": [], "interno": []}
    for f, c, cuerpo in articulos():
        nombre = f.split("/conocimiento/")[1]
        errores += [f"{nombre}: falta {k}" for k in OBLIGATORIOS if k not in c]
        if c.get("estado") not in ESTADOS:
            errores.append(f"{nombre}: estado inválido {c.get('estado')}")
        if c.get("id") != nombre[:-3].replace("/", "."):
            errores.append(f"{nombre}: el id no coincide con la ruta")
        errores += [f"{nombre}: fuente sin referencia {k}" for k in c.get("fuentes", []) if k not in claves]
        errores += [f"{nombre}: caso inexistente {k}" for k in c.get("casos", []) if k not in casos]
        datos = c.get("datos") or {}
        errores += [f"{nombre}: dato con valor propio {k}" for k, v in datos.items() if not REFERENCIA.match(str(v))]
        texto = cuerpo.split("\n## Respaldo")[0]
        marcas = set(re.findall(r"\{(\w+)\}", texto))
        errores += [f"{nombre}: marcador sin dato {m}" for m in marcas - set(datos)]
        errores += [f"{nombre}: dato sin usar {m}" for m in set(datos) - marcas]
        if "\n## Respaldo" not in cuerpo:
            errores.append(f"{nombre}: falta la tabla de respaldo")
        if c.get("audiencia") == "publico":
            prosa = re.sub(r"^\s*\d+\.\s", "", re.sub(r"\{\w+\}", "", texto), flags=re.M)
            errores += [f"{nombre}: cifra en la prosa pública ({n})" for n in re.findall(r"\d+", prosa)]
        filas[c["audiencia"]].append(
            f"| [`{c['id']}`]({nombre}) | {c['titulo']} | {c['protocolo']} | {c['criticidad']} | "
            f"{c['estado']} |")
    return errores, filas


def indice(filas):
    cabeza = open(f"{RAIZ}/conocimiento/README.md", encoding="utf-8").read().split("## Públicos")[0]
    tabla = "| Id | Título | Protocolo | Criticidad | Estado |\n|---|---|---|---|---|\n"
    texto = (cabeza + "## Públicos (el cliente y el asistente)\n\n" + tabla + "\n".join(filas["publico"]) +
             "\n\n## Internos (asesores, supervisores y observadores)\n\n" + tabla + "\n".join(filas["interno"]) + "\n")
    open(f"{RAIZ}/conocimiento/README.md", "w", encoding="utf-8").write(texto)


if __name__ == "__main__":
    errores, filas = verificar()
    indice(filas)
    print("\n".join(errores) or f"conocimiento OK: {sum(map(len, filas.values()))} artículos")
    sys.exit(1 if errores else 0)
