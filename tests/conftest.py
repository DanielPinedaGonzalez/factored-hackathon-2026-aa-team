"""Las pruebas corren en su propia base (`aa_team_pruebas`, `make base-pruebas`), nunca en la de la demo: preparan y
limpian tablas enteras, y en la base de la demo borrarían los casos de la operación en vivo. Lo que escriben queda
además con origen 'pruebas'."""
import os

PRUEBAS = "127.0.0.1:5433/aa_team_pruebas"
os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL_PRUEBAS", f"postgresql://app_api:app_api_local@{PRUEBAS}")
os.environ["DATABASE_URL_ADMIN"] = os.environ.get("DATABASE_URL_ADMIN_PRUEBAS", f"postgresql://aa_admin:aa_admin_local@{PRUEBAS}")
os.environ["REGISTRO_ORIGEN"] = "pruebas"
for _url in (os.environ["DATABASE_URL"], os.environ["DATABASE_URL_ADMIN"]):
    if not _url.rstrip("/").endswith("_pruebas"):
        raise RuntimeError(f"las pruebas solo corren en una base *_pruebas: {_url.rsplit('@', 1)[-1]}")
