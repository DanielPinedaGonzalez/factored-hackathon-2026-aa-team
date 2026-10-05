"""Export limpio para el repositorio público (CLAUDE.md §1, PENDIENTES "Entrega pública").

Copia a una carpeta nueva lo que es público, con historia nueva (un solo commit), sin lo interno ni lo del organizador, y
la revisa antes de dar el resultado por bueno: escaneo de llaves, verificación de los planos y comprobación de que nada
excluido se coló. No toca este repositorio.

Uso: python scripts/exportar_publico.py [--destino ../export_publico] [--sin-commit]
Después, desde la carpeta de destino:  gh repo create factored-hackathon-2026-aa-team --public --source=. --push
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
from escanear_llaves import escanear  # noqa: E402

# Lo que nunca sale: lo interno (privado/, CLAUDE.md), los secretos y los datos del organizador o derivados de ellos.
EXCLUIDOS = ("privado/", "CLAUDE.md", "PENDIENTES.md", ".env", "evaluacion/manifest_casos.json", "evaluacion/corridas/", ".claude/",
             ".pytest_cache/", "__pycache__/", ".venv/", "data/", "scratch/", "apps/web/hackathon.jpg")        # el logo sobre fondo blanco no se usa
SUFIJOS_PROHIBIDOS = (".parquet", ".csv", ".pdf", ".png", ".zip", ".sqlite")
TOPE_MB = 5
PERMITIDOS = {"docs/presentacion/presentacion.pdf"}           # las diapositivas de la entrega
_MARCO_INTERNO = "LE" + "TOS"            # armado por partes: este archivo también se publica y no debe contener el nombre
INTERNOS = re.compile(r"JoIA|Valzarsa|Veridiko|Verídiko|joai|\b" + _MARCO_INTERNO + r"\b")        # nombres internos: no van en nada público
DEFINEN_EL_PATRON = {"scripts/exportar_publico.py", "scripts/verificar_planos.py"}


def _texto_de_pdf(ruta: Path) -> str:
    """El texto de un PDF (las diapositivas): un nombre interno dentro de un PDF no lo ve una búsqueda en texto plano."""
    r = subprocess.run(["pdftotext", str(ruta), "-"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"no se pudo leer el PDF {ruta.name} (¿falta pdftotext?): {r.stderr.strip()}")
    return r.stdout


def archivos_publicos() -> list[str]:
    salida = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], capture_output=True, text=True,
                            cwd=RAIZ, check=True).stdout.split("\n")
    return sorted(a for a in salida if a and (RAIZ / a).is_file() and not any(a == e.rstrip("/") or a.startswith(e) or f"/{e}" in f"/{a}"
                                                                           for e in EXCLUIDOS)
                  and (a in PERMITIDOS or not a.endswith(SUFIJOS_PROHIBIDOS)) and not Path(a).name.startswith(".env"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", type=Path, default=RAIZ.parent / "export_publico")
    ap.add_argument("--sin-commit", action="store_true")
    a = ap.parse_args()
    destino = a.destino.resolve()
    if destino.exists() and any(destino.iterdir()):
        sys.exit(f"{destino} ya existe y no está vacío: bórralo o elige otro destino")
    destino.mkdir(parents=True, exist_ok=True)

    archivos = archivos_publicos()
    for f in archivos:
        (destino / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RAIZ / f, destino / f)
    problemas: list[str] = []

    # 1. Nada excluido se coló (nombres) y nada pesado.
    for f in (str(p.relative_to(destino)) for p in destino.rglob("*") if p.is_file()):
        if any(f == e.rstrip("/") or f.startswith(e) for e in EXCLUIDOS) or (f.endswith(SUFIJOS_PROHIBIDOS) and f not in PERMITIDOS):
            problemas.append(f"se coló un archivo excluido: {f}")
        if (destino / f).stat().st_size > TOPE_MB * 1024 * 1024:
            problemas.append(f"pesa más de {TOPE_MB} MB: {f}")
    # 2. Nombres internos en cualquier archivo de texto.
    for f in archivos:
        if f in DEFINEN_EL_PATRON:
            continue
        try:
            texto = _texto_de_pdf(destino / f) if f.endswith(".pdf") else (destino / f).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if INTERNOS.search(texto):
            problemas.append(f"nombre interno en un archivo público: {f}")
    # 3. Llaves.
    problemas += [f"llave: {h}" for h in escanear(destino, archivos)]
    # 4. Los planos: coherencia y nada interno en lo público.
    r = subprocess.run([sys.executable, "scripts/verificar_planos.py"], cwd=destino, capture_output=True, text=True)
    if r.returncode != 0:
        problemas.append("verificar_planos falló en el export:\n" + (r.stdout + r.stderr)[-600:])
    if problemas:
        print("EL EXPORT NO ESTÁ LIMPIO:\n  " + "\n  ".join(problemas))
        return 1

    if not a.sin_commit:
        git = lambda *args: subprocess.run(["git", *args], cwd=destino, check=True, capture_output=True, text=True).stdout.strip()
        git("init", "-q", "-b", "main")
        git("add", "-A")
        git("-c", "user.name=AA TEAM", "-c", "user.email=hackathon@aa-team.invalid", "commit", "-q", "-m",
            "AA TEAM · Factored AI & Data Hackathon 2026\n\nAsistente de atención bancaria para \"no reconozco este cargo\": "
            "el modelo interpreta, el código decide.\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>")
    tam = sum((destino / f).stat().st_size for f in archivos) / 1024 / 1024
    print(f"export limpio en {destino}: {len(archivos)} archivos, {tam:.1f} MB, sin llaves, planos OK"
          + ("" if a.sin_commit else ", una sola historia (1 commit)"))
    print("siguiente paso, desde esa carpeta:  gh repo create factored-hackathon-2026-aa-team --public --source=. --push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
