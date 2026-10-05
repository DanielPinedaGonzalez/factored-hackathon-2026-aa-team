"""Aplica las migraciones pendientes de `migraciones/` en orden (DESPLIEGUE §3). Fuente única del esquema.

Cada migración queda registrada con su checksum; si una ya aplicada cambió de contenido, el proceso aborta.
Uso: DATABASE_URL_ADMIN=postgresql://... python scripts/migrar.py
En una base que no es local exige APP_API_PASSWORD: la migración 001 crea el rol de ejecución `app_api` con la clave de desarrollo,
y esa clave no puede quedar en una base pública. Con APP_API_PASSWORD se cambia al terminar (la misma que va en DATABASE_URL de la API).
"""
import hashlib
import os
import sys
from pathlib import Path

import psycopg
import psycopg.conninfo
from psycopg import sql

RAIZ = Path(__file__).resolve().parents[1]
URL = os.environ.get("DATABASE_URL_ADMIN", "postgresql://aa_admin:aa_admin_local@127.0.0.1:5433/aa_team")


def es_local(url: str) -> bool:
    return psycopg.conninfo.conninfo_to_dict(url).get("host", "") in ("127.0.0.1", "localhost", "::1", "")


def main() -> int:
    clave = os.environ.get("APP_API_PASSWORD")
    if not es_local(URL) and not clave:
        print("ABORTA: esta base no es local y falta APP_API_PASSWORD (el rol app_api quedaría con la clave de desarrollo)")
        return 1
    if es_local(URL) and clave:
        # Los roles de PostgreSQL son del clúster, no de una base: aquí cambiaría la clave de app_api para TODAS las bases locales
        # (las pruebas, la evaluación y la demo) y las dejaría sin conexión.
        print("ABORTA: APP_API_PASSWORD en una base local cambiaría la clave de app_api para todo el clúster; solo se usa con una base remota")
        return 1
    with psycopg.connect(URL, autocommit=True) as c:
        c.execute("CREATE TABLE IF NOT EXISTS public.migraciones_aplicadas (nombre text PRIMARY KEY, aplicada timestamptz DEFAULT now())")
        c.execute("ALTER TABLE public.migraciones_aplicadas ADD COLUMN IF NOT EXISTS checksum text")
        hechas = dict(c.execute("SELECT nombre, checksum FROM public.migraciones_aplicadas").fetchall())
        version = c.execute("SHOW server_version_num").fetchone()[0]
        if int(version) < 160015:
            print(f"PostgreSQL {version} < 16.15 (INV-RLS)")
            return 1
        for f in sorted((RAIZ / "migraciones").glob("*.sql")):
            suma = hashlib.sha256(f.read_bytes()).hexdigest()
            if f.name in hechas:
                if hechas[f.name] is None:
                    c.execute("UPDATE public.migraciones_aplicadas SET checksum = %s WHERE nombre = %s", (suma, f.name))
                elif hechas[f.name] != suma:
                    print(f"ABORTA: {f.name} ya se aplicó y cambió de contenido (las migraciones son solo aditivas)")
                    return 1
                continue
            with c.transaction():
                c.execute(f.read_text(encoding="utf-8"))
                c.execute("INSERT INTO public.migraciones_aplicadas (nombre, checksum) VALUES (%s, %s)", (f.name, suma))
            print("aplicada", f.name)
        if clave:                     # el rol de ejecución nunca conserva la clave de desarrollo en una base remota
            c.execute(sql.SQL("ALTER ROLE app_api PASSWORD {}").format(sql.Literal(clave)))
            print("clave de app_api fijada desde APP_API_PASSWORD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
