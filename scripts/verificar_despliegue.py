"""Verifica que producción corre el commit que se subió y que su salud es buena (DESPLIEGUE §4.5).
Uso: python scripts/verificar_despliegue.py URL_API COMMIT"""
import sys
import time

import httpx

api, commit = sys.argv[1].rstrip("/"), sys.argv[2]
limite = time.time() + 900
while time.time() < limite:
    try:
        v = httpx.get(f"{api}/version", timeout=60).json()
        if v.get("commit", "").startswith(commit):
            s = httpx.get(f"{api}/health", timeout=60).json()
            print(s)
            sys.exit(0 if s.get("ok") and s.get("rol_sin_bypass") and int(s.get("postgres", 0)) >= 160015 else 1)
    except httpx.HTTPError as e:
        print("esperando:", type(e).__name__)
    time.sleep(20)
print("producción no llegó al commit", commit)
sys.exit(1)
