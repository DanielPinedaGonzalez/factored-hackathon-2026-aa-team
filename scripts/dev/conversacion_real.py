"""Una conversación con el modelo real (llave gratuita), espaciada por el guardián. Solo al cerrar una pieza.

Uso: python scripts/dev/conversacion_real.py --documento DEMO-1001 --turnos '["texto", "identidad", "sí"]'
"""
import argparse
import json
import os
import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
for linea in (RAIZ / ".env").read_text().splitlines():
    if "=" in linea and not linea.startswith("#"):
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from servicio.llm.cliente import ProveedorOpenAI  # noqa: E402
from servicio.orquestador.orquestador import Entrada, procesar  # noqa: E402
from servicio.recursos.guardian import Guardian  # noqa: E402
from tests.apoyo import limpiar_cliente, token_de  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--documento")
ap.add_argument("--turnos", required=True)
ap.add_argument("--modelo", default="openai/gpt-oss-120b")
ap.add_argument("--llave", default="GROQ_API_KEY")
a = ap.parse_args()
modelo = ProveedorOpenAI("groq", a.modelo, os.environ[a.llave], Guardian(espacio_min_s=8.0, espera_max_s=60))
token = None
if a.documento:
    _, cid = token_de(a.documento)
    limpiar_cliente(cid)
conv = "real_" + secrets.token_hex(4)
for t in json.loads(a.turnos):
    if t == "identidad":
        token, _ = token_de(a.documento)
        e = Entrada(evento={"tipo": "identidad_verificada"})
    elif isinstance(t, dict):
        e = Entrada(evento=t)
    else:
        e = Entrada(texto=t)
    s = procesar(conv, e, token, modelo)
    print(json.dumps({"entrada": t, "nodo": s.nodo, "texto": s.texto, "ui": [u["tipo"] for u in s.ui],
                      "sin_modelo": s.sin_modelo, "traspaso": s.traspaso}, ensure_ascii=False, default=str), flush=True)
print("conversacion", conv)
