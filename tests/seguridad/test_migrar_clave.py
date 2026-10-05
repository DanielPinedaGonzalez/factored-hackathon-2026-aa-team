"""Una base remota no puede quedar con la clave de desarrollo del rol de ejecución (scripts/migrar.py)."""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
REMOTA = "postgresql://migraciones:x@ep-prueba.us-east-2.aws.neon.tech/aa_team?sslmode=require"


def _migrar(**entorno):
    env = {**os.environ, "DATABASE_URL_ADMIN": REMOTA, **entorno}
    env.pop("APP_API_PASSWORD", None) if "APP_API_PASSWORD" not in entorno else None
    return subprocess.run([sys.executable, "scripts/migrar.py"], cwd=RAIZ, env=env, capture_output=True, text=True, timeout=60)


def test_una_base_remota_sin_clave_para_app_api_se_rechaza_antes_de_conectar():
    r = _migrar()
    assert r.returncode == 1 and "falta APP_API_PASSWORD" in r.stdout


def test_el_workflow_de_despliegue_pasa_la_clave_a_las_migraciones():
    flujo = (RAIZ / ".github" / "workflows" / "despliegue.yml").read_text(encoding="utf-8")
    assert "APP_API_PASSWORD" in flujo.split("Migraciones contra Neon", 1)[1].split("4. Desplegar", 1)[0]


def test_una_base_local_con_clave_se_rechaza_porque_los_roles_son_del_cluster():
    """Fijar la clave de app_api desde una base local la cambia para todas las bases del clúster y las deja sin conexión."""
    r = _migrar(DATABASE_URL_ADMIN="postgresql://aa_admin:x@127.0.0.1:5433/aa_team", APP_API_PASSWORD="otra-clave")
    assert r.returncode == 1 and "todo el clúster" in r.stdout
