"""Escaneo de llaves antes de cada commit y en Actions (INV-SECRETOS). Sale con error si encuentra una."""
import re
import subprocess
import sys
from pathlib import Path

PATRON = re.compile(r"(gsk_[A-Za-z0-9]{20,}|sk-or-v1-[a-f0-9]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|postgres(?:ql)?://[^:\s]+:[^@\s]{8,}@[^\s]*neon)")


def escanear(raiz: Path, archivos: list[str]) -> list[str]:
    """Devuelve `archivo: inicio…` por cada coincidencia con un patrón de llave."""
    hallados = []
    for a in archivos:
        try:
            texto = (raiz / a).read_text(encoding="utf-8", errors="ignore")
        except (IsADirectoryError, FileNotFoundError):
            continue
        hallados += [f"{a}: {m.group(0)[:12]}…" for m in PATRON.finditer(texto)]
    return hallados


if __name__ == "__main__":
    archivos = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], capture_output=True, text=True).stdout.split("\n")
    hallados = escanear(Path("."), [a for a in archivos if a])
    if hallados:
        print("LLAVES ENCONTRADAS:\n" + "\n".join(hallados))
        sys.exit(1)
    print("sin llaves")
