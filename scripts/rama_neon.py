"""Punto de restauración en Neon antes de migrar (DESPLIEGUE §4.2): crea una rama con la fecha y el commit y conserva
las 5 más recientes (el plan gratuito admite 10). Uso: NEON_API_KEY=... NEON_PROYECTO=... python scripts/rama_neon.py COMMIT"""
import os
import sys
from datetime import datetime, timezone

import httpx

API = "https://console.neon.tech/api/v2"
h = {"Authorization": f"Bearer {os.environ['NEON_API_KEY']}", "Accept": "application/json"}
proyecto = os.environ["NEON_PROYECTO"]
ramas = httpx.get(f"{API}/projects/{proyecto}/branches", headers=h, timeout=30).json()["branches"]
puntos = sorted([r for r in ramas if r["name"].startswith("restauracion-")], key=lambda r: r["created_at"])
while len(puntos) >= 5:
    vieja = puntos.pop(0)
    httpx.delete(f"{API}/projects/{proyecto}/branches/{vieja['id']}", headers=h, timeout=30).raise_for_status()
    print("borrada", vieja["name"])
nombre = f"restauracion-{datetime.now(timezone.utc):%Y%m%d-%H%M}-{sys.argv[1]}"
httpx.post(f"{API}/projects/{proyecto}/branches", headers=h, json={"branch": {"name": nombre}}, timeout=30).raise_for_status()
print("creada", nombre)
