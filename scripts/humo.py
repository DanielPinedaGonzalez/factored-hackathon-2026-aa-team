"""Prueba de humo determinista en producción (DESPLIEGUE §4.7), sin gastar cupo del modelo: autentica una identidad
de demo, lista sus movimientos y confirma que otra identidad no los ve. Uso: DEMO_CODIGO=... python scripts/humo.py URL_API"""
import os
import sys

import httpx

api = sys.argv[1].rstrip("/")
h = {"X-Demo-Codigo": os.environ.get("DEMO_CODIGO", "")}


def token(documento: str) -> str:
    d = httpx.post(f"{api}/identidad/desafio", json={"documento": documento}, headers=h, timeout=60).json()
    codigo = httpx.get(f"{api}/demo/buzon/{documento}", headers=h, timeout=60).json()[0]["mensaje"]
    return httpx.post(f"{api}/identidad/verificar", json={"desafio_id": d["desafio_id"], "codigo": codigo}, headers=h,
                      timeout=60).json()["token"]


a, b = token("DEMO-1001"), token("DEMO-1002")
movs_a = httpx.get(f"{api}/movimientos", headers={**h, "Authorization": f"Bearer {a}"}, timeout=60).json()
movs_b = httpx.get(f"{api}/movimientos", headers={**h, "Authorization": f"Bearer {b}"}, timeout=60).json()
refs_a, refs_b = {m["ref"] for m in movs_a}, {m["ref"] for m in movs_b}
assert movs_a and not (refs_a & refs_b), "RLS en producción: una identidad ve movimientos de otra"
print("humo OK:", len(movs_a), "movimientos; sin cruce entre identidades")
