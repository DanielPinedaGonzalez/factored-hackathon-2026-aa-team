"""Corre la evaluación con el MISMO sistema y el MISMO modelo, pero llegando a Groq a través de OpenRouter.

Para cuando el cupo gratuito diario de Groq se agota. No cambia el código del sistema (por eso no cambia su huella): intercepta
la llamada HTTP del cliente y la reenvía a OpenRouter con el proveedor fijado en Groq y sin alternativas, de modo que el modelo y
el backend son los mismos que en las corridas con llave de Groq. Qué hace además:
  - el cuerpo de la petición es el mismo que el del camino de Groq (modelo, temperatura, esfuerzo de razonamiento, tokens);
  - comprueba en cada respuesta que quien contestó fue Groq y no otro proveedor; si no, se detiene;
  - suma el costo que informa OpenRouter y se detiene al llegar al tope en dólares (`--tope-usd`);
  - deja anotado en cada corrida guardada que se hizo por esta vía y cuánto costó.
Las llamadas se espacian como en el camino normal (`ESPACIO_LLAMADAS_S`).

Uso: python scripts/dev/correr_via_openrouter.py --archivo-llave RUTA --variable NOMBRE [--tope-usd 0.60]  -- ARGS_DEL_CORREDOR
  p. ej.: ... --archivo-llave ~/otro/.env --variable OPENROUTER_API_KEY -- --conjunto final --modelo groq
La llave se lee del archivo en este proceso; no se imprime ni se copia a ningún lado.
"""
import argparse
import json
import os
import sys
import threading
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"
URL_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
CORRIDAS = RAIZ / "evaluacion" / "corridas"

gasto = {"usd": 0.0, "llamadas": 0, "proveedores": {}}
cerrojo = threading.Lock()


def leer_llave(archivo: Path, variable: str) -> str:
    for linea in archivo.expanduser().read_text(errors="ignore").splitlines():
        if linea.startswith(variable + "="):
            return linea.split("=", 1)[1].strip().strip("\"'")
    sys.exit(f"{variable} no está en {archivo}")


def instalar(llave: str, tope_usd: float) -> None:
    original = httpx.post

    def post(url, **kw):
        if url != URL_GROQ:
            return original(url, **kw)
        cuerpo = dict(kw["json"])
        esfuerzo = cuerpo.pop("reasoning_effort", None)
        if esfuerzo:
            cuerpo["reasoning"] = {"effort": esfuerzo, "exclude": True}
        cuerpo["provider"] = {"order": ["Groq"], "allow_fallbacks": False, "data_collection": "allow"}
        cuerpo["usage"] = {"include": True}
        cabeceras = {"Authorization": f"Bearer {llave}", "X-Title": "AA TEAM evaluacion"}
        r = original(URL_OPENROUTER, json=cuerpo, headers=cabeceras, timeout=kw.get("timeout", 60))
        if r.status_code != 200:                         # deja a la vista por qué rechazó OpenRouter (el cuerpo no lleva la llave)
            print(f"\n[openrouter {r.status_code}] {r.text[:240]!r}", flush=True)
        if r.status_code == 200:
            try:
                d = r.json()
                proveedor = d.get("provider")
                with cerrojo:
                    gasto["llamadas"] += 1
                    gasto["usd"] += float((d.get("usage") or {}).get("cost") or 0)
                    gasto["proveedores"][proveedor] = gasto["proveedores"].get(proveedor, 0) + 1
                    excedido = gasto["usd"] >= tope_usd
                if proveedor != "Groq":
                    print(f"\nSE DETIENE: contestó {proveedor!r} y no Groq: ya no sería el mismo backend", flush=True)
                    raise SystemExit(4)
                if excedido:
                    print(f"\nSE DETIENE: tope de gasto alcanzado ({gasto['usd']:.4f} USD de {tope_usd:.2f})", flush=True)
                    raise SystemExit(3)
            except (ValueError, KeyError):
                pass
        return r

    httpx.post = post


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archivo-llave", type=Path, required=True)
    ap.add_argument("--variable", required=True)
    ap.add_argument("--tope-usd", type=float, default=0.60)
    ap.add_argument("corredor", nargs=argparse.REMAINDER, help="argumentos de evaluacion.corredor, después de --")
    a = ap.parse_args()
    args = [x for x in a.corredor if x != "--"]
    llave = leer_llave(a.archivo_llave, a.variable)
    # Las "llaves de Groq" del pool son aquí solo identificadores (tres entradas con su propio espaciado); la autenticación es la de OpenRouter.
    for i, n in enumerate(("GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3"), 1):
        os.environ[n] = f"via-openrouter-{i}"
    os.environ.setdefault("ESPACIO_LLAMADAS_S", "12")
    instalar(llave, a.tope_usd)
    antes = {f.name for f in CORRIDAS.glob("*.json")}
    sys.argv = ["evaluacion.corredor", *args]
    from evaluacion import corredor
    codigo = 0
    try:
        corredor.main()
    except SystemExit as e:
        codigo = int(e.code or 0)
    for f in CORRIDAS.glob("*.json"):                                    # anota la vía en cada corrida nueva
        if f.name not in antes:
            d = json.loads(f.read_text())
            d.setdefault("versiones", {})["via"] = {"ruta": "OpenRouter con proveedor fijado en Groq (sin alternativas)",
                                                    "costo_usd": round(gasto["usd"], 4), "llamadas": gasto["llamadas"],
                                                    "proveedores_que_contestaron": gasto["proveedores"]}
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1, default=str))
    print(f"\ncosto de esta ejecución: {gasto['usd']:.4f} USD en {gasto['llamadas']} llamadas · contestaron: {gasto['proveedores']}")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
