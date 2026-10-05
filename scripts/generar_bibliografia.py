"""Genera docs/BIBLIOGRAFIA.md desde docs/bibliografia/referencias.yaml y verifica las citas.

Uso: python scripts/generar_bibliografia.py [--verificar]
Con --verificar falla si una cita en el texto de docs/ o conocimiento/ no está en el registro,
o si una clave del registro no se cita en ninguna parte.
"""
import glob
import re
import sys
import unicodedata

import yaml

RAIZ = __file__.rsplit("/scripts/", 1)[0]
REGISTRO = f"{RAIZ}/docs/bibliografia/referencias.yaml"
SALIDA = f"{RAIZ}/docs/BIBLIOGRAFIA.md"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def _orden(ref):
    texto = unicodedata.normalize("NFKD", ref["apa"]).encode("ascii", "ignore").decode().lower()
    return texto


def _fecha(f):
    return f"{f.day} de {MESES[f.month - 1]} de {f.year}"


def referencias():
    return yaml.safe_load(open(REGISTRO, encoding="utf-8"))


def generar():
    refs = sorted(referencias(), key=_orden)
    lineas = ["# BIBLIOGRAFÍA — referencias en formato APA 7", "",
              "**Diseño de arquitectura:** Daniel Pineda González",
              "**Qué responde:** de dónde sale cada afirmación. Se genera desde `docs/bibliografia/referencias.yaml` con "
              "`scripts/generar_bibliografia.py`; no se edita a mano. Cada documento y cada artículo de `conocimiento/` "
              "cita en el texto con el formato (Autor, año); las páginas que cambian llevan su fecha de consulta.",
              "", "## Referencias", ""]
    for r in refs:
        ref = r["apa"]
        if r.get("url"):
            ref += (f" Recuperado el {_fecha(r['consultado'])}, de {r['url']}" if r.get("consultado")
                    else f" {r['url']}")
        lineas.append(f"- {ref}")
    open(SALIDA, "w", encoding="utf-8").write("\n".join(lineas) + "\n")


def verificar():
    citas = {r["cita"] for r in referencias()}
    usadas, errores = set(), []
    archivos = [f for f in glob.glob(f"{RAIZ}/docs/*.md") if not f.endswith("BIBLIOGRAFIA.md")]
    archivos += glob.glob(f"{RAIZ}/conocimiento/*/*.md")
    for f in archivos:
        texto = open(f, encoding="utf-8").read()
        for grupo in re.findall(r"[(\[]([^()\[\]]*?(?:\d{4}|s\. f\.)(?:-[a-z])?[^()\[\]]*?)[)\]]", texto):
            for c in [x.strip() for x in grupo.split(";")]:
                m = re.match(r"^(.+?), ((?:(?:\d{4}|s\. f\.)(?:-[a-z])?)(?:, (?:\d{4}|s\. f\.)(?:-[a-z])?)*)$", c)
                if not m:
                    continue
                for anio in m.group(2).split(", "):
                    k = f"{m.group(1)}, {anio}"
                    (usadas.add(k) if k in citas else errores.append(f"{f.split(RAIZ)[1]}: cita sin referencia: {k}"))
    errores += [f"referencia sin citar: {c}" for c in sorted(citas - usadas)]
    print("\n".join(errores) or f"bibliografía OK: {len(usadas)} referencias citadas")
    return not errores


if __name__ == "__main__":
    generar()
    if "--verificar" in sys.argv and not verificar():
        sys.exit(1)
