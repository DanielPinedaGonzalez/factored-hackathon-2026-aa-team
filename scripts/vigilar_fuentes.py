"""Vigilancia de las fuentes (GOBERNANZA §11.6): guarda la huella del contenido de cada URL de la bibliografía y, si una
fuente cambió, marca los artículos que la citan. Un artículo de criticidad alta con una fuente cambiada deja de
servirse hasta que alguien la revise (`conocimiento.vigente`). Una fuente que no responde no cuenta como cambiada: se
informa aparte.

Uso:
  python scripts/vigilar_fuentes.py                 corre la vigilancia (semanal, en GitHub Actions); sale con 1 si algo cambió
  python scripts/vigilar_fuentes.py --revisado CLAVE  la fuente se revisó: sale de la lista y su huella nueva queda como base
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
REGISTRO = RAIZ / "docs" / "bibliografia" / "referencias.yaml"
HUELLAS = RAIZ / "artefactos" / "huellas_fuentes.json"
CAMBIADAS = RAIZ / "artefactos" / "fuentes_cambiadas.json"


def descargar(url: str) -> str:
    pedido = urllib.request.Request(url, headers={"User-Agent": "aa-team-vigilancia-de-fuentes"})
    with urllib.request.urlopen(pedido, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def huella(contenido: str) -> str:
    """El texto visible, sin etiquetas, scripts ni espacios de más: un cambio de diseño de la página no cuenta."""
    texto = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", contenido)
    texto = html.unescape(re.sub(r"(?s)<[^>]+>", " ", texto))
    return hashlib.sha256(re.sub(r"\s+", " ", texto).strip().encode()).hexdigest()[:16]


def articulos_por_fuente() -> dict[str, list[str]]:
    salida: dict[str, list[str]] = {}
    for f in sorted((RAIZ / "conocimiento").glob("*/*.md")):
        if f.name == "README.md":
            continue
        cab = yaml.safe_load(f.read_text(encoding="utf-8").split("---\n", 2)[1])
        for clave in cab.get("fuentes") or []:
            salida.setdefault(clave, []).append(cab["id"])
    return salida


def _leer(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def vigilar(descarga=descargar) -> dict:
    refs = [r for r in yaml.safe_load(REGISTRO.read_text(encoding="utf-8")) if r.get("url")]
    huellas, cambiadas = _leer(HUELLAS), _leer(CAMBIADAS)
    citan = articulos_por_fuente()
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    nuevas, sin_respuesta, primeras = [], [], []
    for r in refs:
        try:
            h = huella(descarga(r["url"]))
        except Exception as e:                      # la fuente no respondió: se informa, no se da por cambiada
            sin_respuesta.append({"clave": r["clave"], "razon": f"{type(e).__name__}: {e}"[:160]})
            continue
        previa = huellas.get(r["clave"])
        if previa is None:
            primeras.append(r["clave"])
        elif previa["huella"] != h and r["clave"] not in cambiadas:
            cambiadas[r["clave"]] = {"url": r["url"], "detectado": ahora, "huella_anterior": previa["huella"],
                                     "huella_nueva": h, "articulos": citan.get(r["clave"], [])}
            nuevas.append(r["clave"])
        if previa is None or r["clave"] not in cambiadas:
            huellas[r["clave"]] = {"huella": h, "visto": ahora}
    HUELLAS.write_text(json.dumps(huellas, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    CAMBIADAS.write_text(json.dumps(cambiadas, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"cambiadas_nuevas": nuevas, "pendientes_de_revision": sorted(cambiadas), "sin_respuesta": sin_respuesta,
            "huella_inicial": primeras}


def revisado(clave: str) -> None:
    cambiadas, huellas = _leer(CAMBIADAS), _leer(HUELLAS)
    c = cambiadas.pop(clave)
    huellas[clave] = {"huella": c["huella_nueva"], "visto": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    HUELLAS.write_text(json.dumps(huellas, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    CAMBIADAS.write_text(json.dumps(cambiadas, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--revisado":
        revisado(sys.argv[2])
        sys.exit(0)
    informe = vigilar()
    print(json.dumps(informe, ensure_ascii=False, indent=1))
    sys.exit(1 if informe["cambiadas_nuevas"] else 0)
