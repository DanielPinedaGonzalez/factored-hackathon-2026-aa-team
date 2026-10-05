"""La huella de lo que se probó: qué sistema exacto produjo una corrida (docs/REPORTE_EVALUACION.md, "Reproducibilidad").

Dos corridas con la misma huella del sistema son repeticiones: lo que cambie entre ellas es el azar del modelo. Si la
huella cambia, el sistema cambió y el reporte dice qué componente. La huella sale del contenido de los archivos, no de
git: una corrida con cambios sin registrar tiene una huella distinta de la del commit.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Lo que define al sistema probado. Los casos y los datos se registran aparte: no son el sistema.
COMPONENTES = {
    "prompts": ["prompts/*.md"],
    "catalogo": ["contratos/catalogo.yaml"],
    "politica": ["politica/*.yaml"],
    "config": ["config/*.yaml"],
    "codigo": ["servicio/**/*.py", "contratos/*.py"],
}
APARTE = {"casos": ["evaluacion/ground_truth_cases.yaml"], "datos": ["evaluacion/manifest_casos.json"]}


def _hash(patrones: list[str]) -> str:
    h = hashlib.sha256()
    for archivo in sorted({a for pt in patrones for a in RAIZ.glob(pt) if a.is_file() and "__pycache__" not in a.parts}):
        h.update(str(archivo.relative_to(RAIZ)).encode())
        h.update(archivo.read_bytes())
    return h.hexdigest()[:12]


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, cwd=RAIZ).stdout.strip()
    except OSError:
        return ""


def huella() -> dict:
    from servicio.llm.cliente import TEMPERATURA_BASE, TEMPERATURAS_SISTEMA, modelos_del_sistema
    componentes = {n: _hash(p) for n, p in COMPONENTES.items()}
    return {"sistema": hashlib.sha256("".join(componentes[n] for n in COMPONENTES).encode()).hexdigest()[:12],
            "componentes": componentes, "aparte": {n: _hash(p) for n, p in APARTE.items()},
            "modelos": modelos_del_sistema(), "temperaturas": {t: TEMPERATURAS_SISTEMA.get(t, TEMPERATURA_BASE) for t in modelos_del_sistema()},
            "commit": _git("rev-parse", "--short", "HEAD") or None, "cambios_sin_registrar": bool(_git("status", "--porcelain"))}


def que_cambio(a: dict, b: dict) -> list[str]:
    """Qué componentes difieren entre dos huellas (vacío si es el mismo sistema)."""
    ca, cb = a.get("componentes", {}), b.get("componentes", {})
    return [n for n in COMPONENTES if ca.get(n) != cb.get(n)] + (["modelos"] if a.get("modelos") != b.get("modelos") else [])
