"""Verifica la coherencia de los planos: referencias `DOC §x`, artículos citados, voseo, nombres internos y citas de auditorías.

Uso: python scripts/verificar_planos.py   (sale con error si algo no cumple)
Complementa a verificar_conocimiento.py y generar_bibliografia.py --verificar.
"""
import glob
import os
import re
import sys

RAIZ = __file__.rsplit("/scripts/", 1)[0]
DOCS = {os.path.basename(f): open(f, encoding="utf-8").read() for f in glob.glob(f"{RAIZ}/docs/*.md")}
ALIAS = {k[:-3]: k for k in DOCS}
ALIAS.update({"PLAN": "02_PLAN.md", "Plan": "02_PLAN.md", "plan": "02_PLAN.md", "Diag": "01_DIAGNOSTICO.md",
              "DIAGNÓSTICO": "01_DIAGNOSTICO.md", "GOBERNANZA": "GOBERNANZA_DATOS_IA.md"})


def secciones(texto):
    hs = set()
    for linea in texto.splitlines():
        m = re.match(r"#+\s+(P?\d+[a-z]?(?:\.\d+)*[a-z]?)[.\s]", linea)
        if m:
            hs.add(m.group(1))
        m = re.match(r"#+\s+(\d+)-(\d+)", linea)
        if m:
            hs.update(str(k) for k in range(int(m.group(1)), int(m.group(2)) + 1))
        m = re.match(r"\*\*(\d+\.\d+\.\d+)", linea)
        if m:
            hs.add(m.group(1))
    return hs


def verificar():
    h = {k: secciones(v) for k, v in DOCS.items()}
    errores = []
    archivos = glob.glob(f"{RAIZ}/docs/*.md") + [f"{RAIZ}/CLAUDE.md", f"{RAIZ}/PENDIENTES.md"]
    archivos += glob.glob(f"{RAIZ}/conocimiento/*.md") + glob.glob(f"{RAIZ}/conocimiento/*/*.md")
    for f in (f for f in archivos if os.path.exists(f)):      # en el export público no están CLAUDE.md ni privado/
        nombre, texto = f.split(RAIZ + "/")[1], open(f, encoding="utf-8").read()
        for m in re.finditer(r"`?(?:docs/)?([A-Za-zÓ0-9_]+)(?:\.md)?`?\s*§\s*(P?\d+[a-z]?(?:\.\d+)*[a-z]?)", texto):
            destino, sec = ALIAS.get(m.group(1)), m.group(2).rstrip(".")
            if destino and sec not in h[destino]:
                errores.append(f"{nombre}: sección inexistente {m.group(0)}")
        for a in re.findall(r"`((?:publico|interno)\.[a-z-]+)`", texto):
            if not os.path.exists(f"{RAIZ}/conocimiento/{a.replace('.', '/', 1)}.md"):
                errores.append(f"{nombre}: artículo inexistente {a}")
        errores += [f"{nombre}: voseo '{w}'" for w in re.findall(r"\b(tenés|sos|querés|podés|vos|contá|mirá)\b", texto)]
        publico = nombre.startswith(("docs/", "conocimiento/"))
        if publico and re.search(r"JoIA|Valzarsa|Veridiko|Verídiko|joai", texto):
            errores.append(f"{nombre}: nombre interno en un documento público")
        if publico and re.search(r"(?<![A-Za-z0-9_-])(?:H|G|AT)-\d{1,2}(?![0-9])|auditor[ií]a (?:externa|de cierre)", texto):
            errores.append(f"{nombre}: cita de una auditoría (privada) en un documento público")
    return errores


if __name__ == "__main__":
    errores = verificar()
    print("\n".join(errores) or "planos OK")
    sys.exit(1 if errores else 0)
