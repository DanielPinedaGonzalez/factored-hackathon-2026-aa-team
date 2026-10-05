"""Carga los artículos de conocimiento/ en la base (rol de migraciones). Uso: python scripts/cargar_conocimiento.py"""
import os
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from servicio.conocimiento.conocimiento import cargar_en_base  # noqa: E402

URL = os.environ.get("DATABASE_URL_ADMIN", "postgresql://aa_admin:aa_admin_local@127.0.0.1:5433/aa_team")
with psycopg.connect(URL) as c:
    print("artículos cargados:", cargar_en_base(c))
