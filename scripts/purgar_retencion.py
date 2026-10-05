"""Purga por retención (MODELO_DATOS §5): aplica los plazos de `config/retencion.yaml` con la función de la base, que
vacía el contenido vencido sin borrar los hechos de los casos y deja un evento con los conteos.

Uso: DATABASE_URL_ADMIN=... python scripts/purgar_retencion.py   (en producción, el trabajo semanal de Actions)
"""
import json
import os
from pathlib import Path

import psycopg
import yaml

RAIZ = Path(__file__).resolve().parents[1]
URL = os.environ.get("DATABASE_URL_ADMIN", "postgresql://aa_admin:aa_admin_local@127.0.0.1:5433/aa_team")


def purgar(url: str = URL) -> dict:
    r = yaml.safe_load((RAIZ / "config" / "retencion.yaml").read_text(encoding="utf-8"))
    with psycopg.connect(url, autocommit=True) as c:
        return c.execute("select operacion.purgar_por_retencion(%s, %s, %s)",
                         (r["conversaciones_dias"], r["adjuntos_sin_reclamo_dias"], r["registro_dias"])).fetchone()[0]


if __name__ == "__main__":
    print(json.dumps(purgar(), ensure_ascii=False))
