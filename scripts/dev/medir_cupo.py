"""Mide el cupo real de cada modelo candidato con una llamada mínima, leyendo las cabeceras de límite (02_PLAN §9).
El resultado define el tamaño de la evaluación y el espaciado del guardián. Uso: python scripts/dev/medir_cupo.py"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
for linea in (RAIZ / ".env").read_text().splitlines():
    if "=" in linea and not linea.startswith("#"):
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

CANDIDATOS = [("groq", "openai/gpt-oss-120b"), ("groq", "openai/gpt-oss-20b"), ("groq", "llama-3.3-70b-versatile"),
              ("groq", "qwen/qwen3-32b")]
salida = []
for proveedor, modelo in CANDIDATOS:
    r = httpx.post("https://api.groq.com/openai/v1/chat/completions", timeout=30,
                   headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                   json={"model": modelo, "max_tokens": 5, "messages": [{"role": "user", "content": "Responde solo: ok"}]})
    h = {k: v for k, v in r.headers.items() if k.startswith("x-ratelimit")}
    salida.append({"proveedor": proveedor, "modelo": modelo, "http": r.status_code, **h})
    print(modelo, r.status_code, h)
    time.sleep(3)
(RAIZ / "artefactos" / "cupo_medido.json").write_text(json.dumps(
    {"medido": datetime.now(timezone.utc).isoformat(timespec="seconds"), "modelos": salida}, indent=1))
